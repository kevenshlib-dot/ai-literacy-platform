"""Exam service - handles exam CRUD, assembly strategy, and lifecycle management."""
import math
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exam import Exam, ExamQuestion, ExamStatus
from app.models.question import Question, QuestionType, QuestionStatus


async def create_exam(
    db: AsyncSession,
    title: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
    time_limit_minutes: Optional[int] = None,
    total_score: float = 100.0,
) -> Exam:
    exam = Exam(
        title=title,
        description=description,
        time_limit_minutes=time_limit_minutes,
        total_score=total_score,
        created_by=created_by,
        status=ExamStatus.DRAFT,
    )
    db.add(exam)
    await db.flush()
    return exam


async def get_exam_by_id(
    db: AsyncSession, exam_id: uuid.UUID, load_questions: bool = False
) -> Optional[Exam]:
    stmt = select(Exam).where(Exam.id == exam_id)
    if load_questions:
        stmt = stmt.options(selectinload(Exam.questions))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_exams(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    is_random_test: Optional[bool] = None,
    archive: Optional[bool] = None,
) -> tuple[list[Exam], int]:
    conditions = []
    if archive:
        # Archive mode: closed exams + random test exams
        conditions.append(or_(
            Exam.status == ExamStatus.CLOSED,
            Exam.title.startswith("随机测试"),
        ))
    else:
        if status:
            conditions.append(Exam.status == ExamStatus(status))
        if is_random_test is True:
            conditions.append(Exam.title.startswith("随机测试"))
        elif is_random_test is False:
            conditions.append(~Exam.title.startswith("随机测试"))
    if keyword:
        conditions.append(Exam.title.ilike(f"%{keyword}%"))
    if created_by:
        conditions.append(Exam.created_by == created_by)

    where_clause = and_(*conditions) if conditions else True

    total = (await db.execute(
        select(func.count(Exam.id)).where(where_clause)
    )).scalar()

    items_q = (
        select(Exam)
        .where(where_clause)
        .order_by(Exam.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(items_q)
    return list(result.scalars().all()), total


async def update_exam(
    db: AsyncSession, exam_id: uuid.UUID, **kwargs
) -> Optional[Exam]:
    exam = await get_exam_by_id(db, exam_id)
    if not exam:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(exam, key):
            setattr(exam, key, value)
    await db.flush()
    return exam


async def delete_exam(db: AsyncSession, exam_id: uuid.UUID) -> bool:
    exam = await get_exam_by_id(db, exam_id)
    if not exam:
        return False
    # Delete exam questions first
    await db.execute(
        delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )
    await db.delete(exam)
    await db.flush()
    return True


async def publish_exam(db: AsyncSession, exam_id: uuid.UUID) -> Optional[Exam]:
    exam = await get_exam_by_id(db, exam_id, load_questions=True)
    if not exam:
        return None
    if not exam.questions:
        raise ValueError("试卷没有题目，无法发布")
    exam.status = ExamStatus.PUBLISHED
    await db.flush()
    return exam


async def close_exam(db: AsyncSession, exam_id: uuid.UUID) -> Optional[Exam]:
    exam = await get_exam_by_id(db, exam_id)
    if not exam:
        return None
    exam.status = ExamStatus.CLOSED
    await db.flush()
    return exam


# ---- Assembly ----

async def manual_assemble(
    db: AsyncSession,
    exam_id: uuid.UUID,
    questions: list[dict],
) -> list[ExamQuestion]:
    """Manually add questions to an exam."""
    exam = await get_exam_by_id(db, exam_id)
    if not exam:
        raise ValueError("试卷不存在")
    if exam.status != ExamStatus.DRAFT:
        raise ValueError("只能为草稿状态的试卷添加题目")

    # Clear existing questions
    await db.execute(
        delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )

    exam_questions = []
    total_score = 0.0
    for item in questions:
        eq = ExamQuestion(
            exam_id=exam_id,
            question_id=item["question_id"],
            order_num=item["order_num"],
            score=item.get("score", 5.0),
        )
        db.add(eq)
        exam_questions.append(eq)
        total_score += eq.score

    exam.total_score = total_score
    await db.flush()
    return exam_questions


async def auto_assemble(
    db: AsyncSession,
    exam_id: uuid.UUID,
    type_distribution: dict,
    difficulty_target: int = 3,
    difficulty_tolerance: int = 1,
    dimensions: Optional[list[str]] = None,
    score_per_question: float = 5.0,
    exclude_question_ids: Optional[list[uuid.UUID]] = None,
) -> list[ExamQuestion]:
    """Auto-assemble an exam based on strategy constraints.

    Selects approved questions from the question bank matching the given criteria.
    """
    exam = await get_exam_by_id(db, exam_id)
    if not exam:
        raise ValueError("试卷不存在")
    if exam.status != ExamStatus.DRAFT:
        raise ValueError("只能为草稿状态的试卷组卷")

    # Clear existing questions
    await db.execute(
        delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )

    diff_min = max(1, difficulty_target - difficulty_tolerance)
    diff_max = min(5, difficulty_target + difficulty_tolerance)

    selected_questions = []
    order = 1

    for qtype_str, count in type_distribution.items():
        qtype = QuestionType(qtype_str)

        conditions = [
            Question.status == QuestionStatus.APPROVED,
            Question.question_type == qtype,
            Question.difficulty >= diff_min,
            Question.difficulty <= diff_max,
        ]

        if dimensions:
            conditions.append(Question.dimension.in_(dimensions))

        if exclude_question_ids:
            conditions.append(Question.id.notin_(exclude_question_ids))

        # Exclude already selected
        already_ids = [sq["question_id"] for sq in selected_questions]
        if already_ids:
            conditions.append(Question.id.notin_(already_ids))

        result = await db.execute(
            select(Question)
            .where(and_(*conditions))
            .order_by(func.random())
            .limit(count)
        )
        candidates = list(result.scalars().all())

        for q in candidates:
            selected_questions.append({
                "question_id": q.id,
                "order_num": order,
                "score": score_per_question,
            })
            order += 1

    # Create ExamQuestion records
    exam_questions = []
    total_score = 0.0
    for item in selected_questions:
        eq = ExamQuestion(
            exam_id=exam_id,
            question_id=item["question_id"],
            order_num=item["order_num"],
            score=item["score"],
        )
        db.add(eq)
        exam_questions.append(eq)
        total_score += eq.score

    exam.total_score = total_score
    exam.params = {
        "type_distribution": type_distribution,
        "difficulty_target": difficulty_target,
        "difficulty_tolerance": difficulty_tolerance,
        "dimensions": dimensions,
        "score_per_question": score_per_question,
    }
    await db.flush()

    return exam_questions


async def get_exam_questions(
    db: AsyncSession, exam_id: uuid.UUID
) -> list[ExamQuestion]:
    result = await db.execute(
        select(ExamQuestion)
        .where(ExamQuestion.exam_id == exam_id)
        .order_by(ExamQuestion.order_num)
    )
    return list(result.scalars().all())


async def get_exam_stats(db: AsyncSession) -> dict:
    total = (await db.execute(select(func.count(Exam.id)))).scalar()

    status_q = (
        select(Exam.status, func.count(Exam.id))
        .group_by(Exam.status)
    )
    status_result = await db.execute(status_q)
    by_status = {row[0].value: row[1] for row in status_result.all()}

    return {"total": total, "by_status": by_status}


# ---- Random Test ----

# Difficulty distribution configs per mode.
# Each entry: list of (difficulty_range, proportion)
_DIFFICULTY_MODES = {
    "easy": [
        ((1, 1), 1.0),
    ],
    "real": [
        ((1, 2), 0.6),
        ((3, 3), 0.3),
        ((4, 5), 0.1),
    ],
    "hell": [
        ((3, 3), 0.3),
        ((4, 5), 0.7),
    ],
}


def _distribute(total: int, proportions: list[float]) -> list[int]:
    """Split *total* into integer parts matching *proportions* (sum == total)."""
    raw = [total * p for p in proportions]
    floored = [int(math.floor(v)) for v in raw]
    remainders = [(raw[i] - floored[i], i) for i in range(len(raw))]
    remainders.sort(reverse=True)
    deficit = total - sum(floored)
    for _, idx in remainders[:deficit]:
        floored[idx] += 1
    return floored


async def create_random_test(
    db: AsyncSession,
    user_id: uuid.UUID,
    count: int = 10,
    difficulty_mode: str = "real",
) -> Exam:
    """Create a random-test exam, assemble questions, publish, and return it.

    Question type ratio  single_choice : multiple_choice : true_false = 6 : 2 : 2
    Total score is fixed at 100 and evenly distributed.
    """
    if difficulty_mode not in _DIFFICULTY_MODES:
        raise ValueError(f"未知难度模式: {difficulty_mode}")

    # ── type distribution (6:2:2) ──
    type_counts = _distribute(count, [0.6, 0.2, 0.2])
    types_with_counts: list[tuple[QuestionType, int]] = [
        (QuestionType.SINGLE_CHOICE, type_counts[0]),
        (QuestionType.MULTIPLE_CHOICE, type_counts[1]),
        (QuestionType.TRUE_FALSE, type_counts[2]),
    ]

    diff_config = _DIFFICULTY_MODES[difficulty_mode]
    diff_proportions = [p for _, p in diff_config]
    diff_ranges = [r for r, _ in diff_config]

    # ── select questions ──
    selected_ids: list[uuid.UUID] = []
    order = 1
    selected_items: list[dict] = []

    for qtype, qcount in types_with_counts:
        if qcount == 0:
            continue
        # Split this type's count across difficulty bands
        diff_counts = _distribute(qcount, diff_proportions)

        for (d_min, d_max), d_count in zip(diff_ranges, diff_counts):
            if d_count == 0:
                continue
            conditions = [
                Question.status == QuestionStatus.APPROVED,
                Question.question_type == qtype,
                Question.difficulty >= d_min,
                Question.difficulty <= d_max,
            ]
            if selected_ids:
                conditions.append(Question.id.notin_(selected_ids))

            result = await db.execute(
                select(Question.id)
                .where(and_(*conditions))
                .order_by(func.random())
                .limit(d_count)
            )
            ids = [row[0] for row in result.all()]
            for qid in ids:
                selected_items.append({"question_id": qid, "order_num": order})
                selected_ids.append(qid)
                order += 1

    if not selected_items:
        raise ValueError("题库中没有符合条件的题目，无法生成随机测试")

    actual_count = len(selected_items)

    # ── score distribution: 100 points total, evenly split ──
    base_score = round(100 / actual_count, 2)
    scores = [base_score] * actual_count
    # Fix rounding gap on the last question
    scores[-1] = round(100 - base_score * (actual_count - 1), 2)

    # ── create exam ──
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    exam = Exam(
        title=f"随机测试 - {now_str}",
        description=f"随机测试（{actual_count}题）",
        total_score=100.0,
        created_by=user_id,
        status=ExamStatus.DRAFT,
    )
    db.add(exam)
    await db.flush()

    # ── create exam questions ──
    for item, score in zip(selected_items, scores):
        eq = ExamQuestion(
            exam_id=exam.id,
            question_id=item["question_id"],
            order_num=item["order_num"],
            score=score,
        )
        db.add(eq)

    # Publish immediately & mark as random test
    exam.status = ExamStatus.PUBLISHED
    exam.params = {"is_random_test": True, "difficulty_mode": difficulty_mode}
    await db.flush()

    return exam
