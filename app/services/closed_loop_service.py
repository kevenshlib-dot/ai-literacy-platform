"""Assessment-Training Closed Loop service.

Implements the full cycle:
1. Pre-assessment → identify weaknesses
2. Generate learning path → training
3. Post-assessment → measure improvement
4. Comparison report
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.score import Score
from app.models.answer import AnswerSheet
from app.models.learning_path import LearningPath, LearningPathStatus
from app.models.sandbox import SandboxSession, SandboxSessionStatus
from app.services.adaptive_learning_service import DIMENSIONS, analyze_user_weakness


async def get_user_journey(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Get a comprehensive view of the user's assessment-training journey.

    Returns pre/post scores, learning progress, and improvement metrics.
    """
    # Get all scores chronologically
    result = await db.execute(
        select(Score)
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.user_id == user_id)
        .order_by(Score.scored_at.asc())
    )
    scores = list(result.scalars().all())

    # Get learning paths
    result = await db.execute(
        select(LearningPath)
        .options(selectinload(LearningPath.steps))
        .where(LearningPath.user_id == user_id)
        .order_by(LearningPath.created_at.desc())
    )
    paths = list(result.scalars().all())

    # Get sandbox sessions
    result = await db.execute(
        select(SandboxSession)
        .where(SandboxSession.user_id == user_id)
        .order_by(SandboxSession.created_at.desc())
    )
    sandbox_sessions = list(result.scalars().all())

    # Calculate pre/post comparison if enough data
    comparison = _calculate_comparison(scores)

    # Training summary
    training = _training_summary(paths, sandbox_sessions)

    return {
        "user_id": str(user_id),
        "assessment_count": len(scores),
        "comparison": comparison,
        "training_summary": training,
        "dimension_progress": _dimension_progress(scores),
        "journey_status": _determine_journey_status(scores, paths),
    }


async def get_comparison_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    pre_score_id: Optional[uuid.UUID] = None,
    post_score_id: Optional[uuid.UUID] = None,
) -> dict:
    """Generate a before/after comparison report.

    If specific score IDs aren't provided, uses earliest and latest scores.
    """
    if pre_score_id and post_score_id:
        pre = (await db.execute(
            select(Score).where(Score.id == pre_score_id)
        )).scalar_one_or_none()
        post = (await db.execute(
            select(Score).where(Score.id == post_score_id)
        )).scalar_one_or_none()
    else:
        # Auto-select earliest and latest
        result = await db.execute(
            select(Score)
            .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
            .where(AnswerSheet.user_id == user_id)
            .order_by(Score.scored_at.asc())
        )
        all_scores = list(result.scalars().all())
        if len(all_scores) < 2:
            return {
                "has_comparison": False,
                "message": "需要至少两次测评才能生成对比报告",
                "assessment_count": len(all_scores),
            }
        pre = all_scores[0]
        post = all_scores[-1]

    if not pre or not post:
        return {"has_comparison": False, "message": "未找到指定的测评记录"}

    pre_dims = pre.dimension_scores or {}
    post_dims = post.dimension_scores or {}

    dimension_changes = []
    for dim in DIMENSIONS:
        pre_val = pre_dims.get(dim, 0)
        post_val = post_dims.get(dim, 0)
        change = post_val - pre_val if isinstance(post_val, (int, float)) and isinstance(pre_val, (int, float)) else 0
        dimension_changes.append({
            "dimension": dim,
            "pre_score": pre_val,
            "post_score": post_val,
            "change": round(change, 1),
            "improved": change > 0,
        })

    pre_total = pre.total_score or 0
    post_total = post.total_score or 0
    total_change = post_total - pre_total

    return {
        "has_comparison": True,
        "pre_assessment": {
            "score_id": str(pre.id),
            "total_score": pre_total,
            "max_score": pre.max_score,
            "scored_at": pre.scored_at.isoformat() if pre.scored_at else None,
        },
        "post_assessment": {
            "score_id": str(post.id),
            "total_score": post_total,
            "max_score": post.max_score,
            "scored_at": post.scored_at.isoformat() if post.scored_at else None,
        },
        "total_change": round(total_change, 1),
        "improvement_percent": round((total_change / pre_total * 100), 1) if pre_total > 0 else 0,
        "dimension_changes": dimension_changes,
        "improved_dimensions": [d for d in dimension_changes if d["improved"]],
        "declined_dimensions": [d for d in dimension_changes if d["change"] < 0],
        "recommendations": _generate_loop_recommendations(dimension_changes),
    }


async def get_closed_loop_stats(
    db: AsyncSession,
    user_id: Optional[uuid.UUID] = None,
) -> dict:
    """Get platform-wide or user-specific closed-loop statistics."""
    # Count users with multiple assessments
    if user_id:
        user_filter = AnswerSheet.user_id == user_id
    else:
        user_filter = True

    # Total assessments
    total_assessments = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(user_filter)
    )).scalar() or 0

    # Learning paths
    path_filter = LearningPath.user_id == user_id if user_id else True
    total_paths = (await db.execute(
        select(func.count(LearningPath.id)).where(path_filter)
    )).scalar() or 0

    completed_paths = (await db.execute(
        select(func.count(LearningPath.id)).where(
            path_filter,
            LearningPath.status == LearningPathStatus.COMPLETED,
        )
    )).scalar() or 0

    # Sandbox sessions
    sandbox_filter = SandboxSession.user_id == user_id if user_id else True
    total_practices = (await db.execute(
        select(func.count(SandboxSession.id)).where(sandbox_filter)
    )).scalar() or 0

    completed_practices = (await db.execute(
        select(func.count(SandboxSession.id)).where(
            sandbox_filter,
            SandboxSession.status == SandboxSessionStatus.COMPLETED,
        )
    )).scalar() or 0

    return {
        "total_assessments": total_assessments,
        "total_learning_paths": total_paths,
        "completed_learning_paths": completed_paths,
        "total_practices": total_practices,
        "completed_practices": completed_practices,
        "loop_completion_rate": round(
            (completed_paths / total_paths * 100) if total_paths > 0 else 0, 1
        ),
    }


def _calculate_comparison(scores: list) -> dict:
    """Calculate before/after comparison from score list."""
    if len(scores) < 2:
        return {
            "has_data": False,
            "message": "需要至少两次测评数据",
        }

    first = scores[0]
    latest = scores[-1]

    first_total = first.total_score or 0
    latest_total = latest.total_score or 0

    return {
        "has_data": True,
        "first_score": first_total,
        "latest_score": latest_total,
        "change": round(latest_total - first_total, 1),
        "improvement_percent": round(
            ((latest_total - first_total) / first_total * 100) if first_total > 0 else 0, 1
        ),
    }


def _training_summary(paths: list, sandbox_sessions: list) -> dict:
    """Summarize training activity."""
    completed_paths = sum(
        1 for p in paths if p.status == LearningPathStatus.COMPLETED
    )
    total_steps_completed = sum(
        sum(1 for s in p.steps if s.status in ("completed", "skipped"))
        for p in paths if p.steps
    )
    completed_sandbox = sum(
        1 for s in sandbox_sessions if s.status == SandboxSessionStatus.COMPLETED
    )

    return {
        "total_paths": len(paths),
        "completed_paths": completed_paths,
        "total_steps_completed": total_steps_completed,
        "total_sandbox_sessions": len(sandbox_sessions),
        "completed_sandbox_sessions": completed_sandbox,
    }


def _dimension_progress(scores: list) -> list[dict]:
    """Track dimension score progress over time."""
    progress = {dim: [] for dim in DIMENSIONS}

    for score in scores:
        if score.dimension_scores:
            for dim, val in score.dimension_scores.items():
                if dim in progress and isinstance(val, (int, float)):
                    progress[dim].append({
                        "score": val,
                        "date": score.scored_at.isoformat() if score.scored_at else None,
                    })

    return [
        {
            "dimension": dim,
            "data_points": vals,
            "trend": _calculate_trend(vals),
        }
        for dim, vals in progress.items()
    ]


def _calculate_trend(data_points: list[dict]) -> str:
    """Calculate trend direction."""
    if len(data_points) < 2:
        return "insufficient_data"
    first = data_points[0]["score"]
    last = data_points[-1]["score"]
    diff = last - first
    if diff > 5:
        return "improving"
    elif diff < -5:
        return "declining"
    return "stable"


def _determine_journey_status(scores: list, paths: list) -> str:
    """Determine where the user is in their learning journey."""
    if not scores:
        return "not_started"
    if len(scores) == 1 and not paths:
        return "pre_assessed"
    if paths and not any(p.status == LearningPathStatus.COMPLETED for p in paths):
        return "training"
    if any(p.status == LearningPathStatus.COMPLETED for p in paths) and len(scores) >= 2:
        return "post_assessed"
    if paths:
        return "training"
    return "pre_assessed"


def _generate_loop_recommendations(dimension_changes: list[dict]) -> list[dict]:
    """Generate recommendations based on comparison results."""
    recommendations = []

    improved = [d for d in dimension_changes if d["improved"]]
    declined = [d for d in dimension_changes if d["change"] < 0]
    stagnant = [d for d in dimension_changes if d["change"] == 0 and d["pre_score"] < 60]

    if declined:
        for d in declined:
            recommendations.append({
                "priority": "high",
                "dimension": d["dimension"],
                "suggestion": f"{d['dimension']}成绩下降了{abs(d['change']):.1f}分，建议重新学习相关课程并加强练习",
            })

    if stagnant:
        for d in stagnant:
            recommendations.append({
                "priority": "medium",
                "dimension": d["dimension"],
                "suggestion": f"{d['dimension']}成绩未有提升(当前{d['post_score']:.0f}分)，建议尝试不同的学习方法",
            })

    if improved:
        for d in improved:
            if d["post_score"] < 60:
                recommendations.append({
                    "priority": "medium",
                    "dimension": d["dimension"],
                    "suggestion": f"{d['dimension']}虽有进步(+{d['change']:.1f})，但仍需继续提升",
                })

    if not recommendations:
        recommendations.append({
            "priority": "low",
            "dimension": "总体",
            "suggestion": "各维度表现良好，建议保持学习节奏",
        })

    return recommendations
