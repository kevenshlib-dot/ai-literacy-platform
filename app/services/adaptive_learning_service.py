"""Adaptive learning engine - generates personalized learning paths."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.learning_path import (
    LearningPath, LearningStep,
    LearningPathStatus, LearningStepType, LearningStepStatus,
)
from app.models.score import Score
from app.models.answer import AnswerSheet
from app.models.course import Course, CourseStatus

# Five-dimension framework
DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]


async def analyze_user_weakness(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Analyze user's dimension scores to find weaknesses.

    Returns a dict with dimension scores, weaknesses, and strengths.
    """
    # Get all scores for user via answer_sheets
    result = await db.execute(
        select(Score)
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.user_id == user_id)
        .order_by(Score.scored_at.desc())
    )
    scores = list(result.scalars().all())

    if not scores:
        return {
            "dimension_scores": {d: 0.0 for d in DIMENSIONS},
            "weaknesses": DIMENSIONS[:],
            "strengths": [],
            "total_assessments": 0,
        }

    # Aggregate dimension scores
    dim_totals = {d: [] for d in DIMENSIONS}
    for score in scores:
        if score.dimension_scores:
            for dim, val in score.dimension_scores.items():
                if dim in dim_totals:
                    dim_totals[dim].append(val if isinstance(val, (int, float)) else 0)

    dim_averages = {}
    for dim in DIMENSIONS:
        vals = dim_totals[dim]
        dim_averages[dim] = sum(vals) / len(vals) if vals else 0.0

    # Classify weaknesses (below 60%) and strengths (above 80%)
    weaknesses = [d for d, v in dim_averages.items() if v < 60]
    strengths = [d for d, v in dim_averages.items() if v >= 80]

    return {
        "dimension_scores": dim_averages,
        "weaknesses": weaknesses if weaknesses else [min(dim_averages, key=dim_averages.get)],
        "strengths": strengths,
        "total_assessments": len(scores),
    }


async def generate_learning_path(
    db: AsyncSession,
    user_id: uuid.UUID,
    focus_dimensions: Optional[list[str]] = None,
) -> LearningPath:
    """Generate a personalized learning path based on user weaknesses.

    Steps:
    1. Analyze user's weakness dimensions
    2. Find relevant published courses
    3. Build ordered learning steps (course → practice → assessment)
    """
    analysis = await analyze_user_weakness(db, user_id)
    target_dims = focus_dimensions or analysis["weaknesses"]

    # Find courses matching target dimensions
    courses_by_dim = {}
    for dim in target_dims:
        result = await db.execute(
            select(Course)
            .where(Course.status == CourseStatus.PUBLISHED, Course.dimension == dim)
            .order_by(Course.difficulty.asc())
            .limit(3)
        )
        courses_by_dim[dim] = list(result.scalars().all())

    # Build learning path
    path = LearningPath(
        user_id=user_id,
        title=_generate_path_title(target_dims),
        description=_generate_path_description(analysis, target_dims),
        weakness_dimensions=analysis["weaknesses"],
        target_dimensions=target_dims,
    )
    db.add(path)
    await db.flush()

    # Create steps
    order = 1
    for dim in target_dims:
        courses = courses_by_dim.get(dim, [])

        # Course steps
        for course in courses:
            step = LearningStep(
                path_id=path.id,
                order_num=order,
                step_type=LearningStepType.COURSE,
                title=f"学习: {course.title}",
                description=f"完成课程《{course.title}》提升{dim}能力",
                dimension=dim,
                resource_id=course.id,
            )
            db.add(step)
            order += 1

        # Practice step
        practice = LearningStep(
            path_id=path.id,
            order_num=order,
            step_type=LearningStepType.PRACTICE,
            title=f"练习: {dim}",
            description=f"通过练习巩固{dim}相关知识",
            dimension=dim,
        )
        db.add(practice)
        order += 1

        # Assessment step
        assessment = LearningStep(
            path_id=path.id,
            order_num=order,
            step_type=LearningStepType.ASSESSMENT,
            title=f"测评: {dim}",
            description=f"检验{dim}学习成果",
            dimension=dim,
        )
        db.add(assessment)
        order += 1

    # If no courses found for any dimension, add generic steps
    if order == 1:
        for dim in target_dims:
            step = LearningStep(
                path_id=path.id,
                order_num=order,
                step_type=LearningStepType.PRACTICE,
                title=f"自主学习: {dim}",
                description=f"暂无相关课程，建议自主学习{dim}知识",
                dimension=dim,
            )
            db.add(step)
            order += 1

    await db.flush()

    # Reload with steps
    result = await db.execute(
        select(LearningPath)
        .options(selectinload(LearningPath.steps))
        .where(LearningPath.id == path.id)
    )
    return result.scalar_one()


async def get_learning_path(
    db: AsyncSession,
    path_id: uuid.UUID,
) -> Optional[LearningPath]:
    """Get a learning path with its steps."""
    result = await db.execute(
        select(LearningPath)
        .options(selectinload(LearningPath.steps))
        .where(LearningPath.id == path_id)
    )
    return result.scalar_one_or_none()


async def list_user_paths(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[LearningPath]:
    """List all learning paths for a user."""
    result = await db.execute(
        select(LearningPath)
        .options(selectinload(LearningPath.steps))
        .where(LearningPath.user_id == user_id)
        .order_by(LearningPath.created_at.desc())
    )
    return list(result.scalars().all())


async def update_step_status(
    db: AsyncSession,
    step_id: uuid.UUID,
    status: str,
    score: Optional[float] = None,
) -> Optional[LearningStep]:
    """Update a learning step's status and recalculate path progress."""
    step = (await db.execute(
        select(LearningStep).where(LearningStep.id == step_id)
    )).scalar_one_or_none()

    if not step:
        return None

    step.status = status
    if score is not None:
        step.score = score
    if status == LearningStepStatus.COMPLETED:
        step.completed_at = datetime.now(timezone.utc)

    # Recalculate path progress
    path = (await db.execute(
        select(LearningPath)
        .options(selectinload(LearningPath.steps))
        .where(LearningPath.id == step.path_id)
    )).scalar_one()

    total_steps = len(path.steps)
    completed = sum(
        1 for s in path.steps
        if s.status in (LearningStepStatus.COMPLETED, LearningStepStatus.SKIPPED)
    )
    path.progress_percent = round((completed / total_steps) * 100, 1) if total_steps > 0 else 0

    if completed == total_steps:
        path.status = LearningPathStatus.COMPLETED

    await db.flush()
    return step


async def get_next_step(
    db: AsyncSession,
    path_id: uuid.UUID,
) -> Optional[dict]:
    """Get the next pending step in a learning path."""
    result = await db.execute(
        select(LearningStep)
        .where(
            LearningStep.path_id == path_id,
            LearningStep.status == LearningStepStatus.PENDING,
        )
        .order_by(LearningStep.order_num.asc())
        .limit(1)
    )
    step = result.scalar_one_or_none()
    if not step:
        return None

    return {
        "id": str(step.id),
        "order_num": step.order_num,
        "step_type": step.step_type.value if hasattr(step.step_type, 'value') else step.step_type,
        "title": step.title,
        "description": step.description,
        "dimension": step.dimension,
        "resource_id": str(step.resource_id) if step.resource_id else None,
    }


async def get_recommendations(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """Get adaptive course recommendations for a user."""
    analysis = await analyze_user_weakness(db, user_id)
    recommendations = []

    for dim in analysis["weaknesses"]:
        score = analysis["dimension_scores"].get(dim, 0)

        # Find courses for this weakness dimension
        result = await db.execute(
            select(Course)
            .where(Course.status == CourseStatus.PUBLISHED, Course.dimension == dim)
            .order_by(Course.difficulty.asc())
            .limit(2)
        )
        courses = list(result.scalars().all())

        priority = "high" if score < 40 else "medium"

        rec = {
            "dimension": dim,
            "current_score": round(score, 1),
            "priority": priority,
            "reason": f"{dim}得分较低({score:.0f}%)，建议重点学习",
            "courses": [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "difficulty": c.difficulty,
                }
                for c in courses
            ],
        }
        recommendations.append(rec)

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 2))

    return recommendations


async def get_courses_for_dimensions(
    db: AsyncSession,
    dimensions: list[str],
    *,
    limit_per_dimension: int = 2,
) -> dict[str, list[Course]]:
    """Return published courses grouped by target dimension."""
    courses_by_dim: dict[str, list[Course]] = {}
    for dim in dimensions:
        result = await db.execute(
            select(Course)
            .where(Course.status == CourseStatus.PUBLISHED, Course.dimension == dim)
            .order_by(Course.difficulty.asc(), Course.created_at.asc())
            .limit(limit_per_dimension)
        )
        courses_by_dim[dim] = list(result.scalars().all())
    return courses_by_dim


def _generate_path_title(dimensions: list[str]) -> str:
    """Generate a human-readable path title."""
    if len(dimensions) == 1:
        return f"{dimensions[0]}提升学习路径"
    elif len(dimensions) <= 3:
        return f"{'、'.join(dimensions)}综合提升路径"
    else:
        return "AI素养全面提升学习路径"


def _generate_path_description(analysis: dict, target_dims: list[str]) -> str:
    """Generate path description."""
    parts = []
    for dim in target_dims:
        score = analysis["dimension_scores"].get(dim, 0)
        parts.append(f"{dim}(当前{score:.0f}%)")
    return f"针对以下薄弱维度制定的个性化学习路径: {'、'.join(parts)}"
