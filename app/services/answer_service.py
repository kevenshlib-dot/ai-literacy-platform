"""Answer service - handles exam sessions, answering, and submission."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.answer import AnswerSheet, Answer, AnswerSheetStatus
from app.models.exam import Exam, ExamQuestion, ExamStatus
from app.models.question import Question


async def start_exam(
    db: AsyncSession,
    exam_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AnswerSheet:
    """Start an exam session for a user."""
    # Verify exam exists and is published
    exam = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = exam.scalar_one_or_none()
    if not exam:
        raise ValueError("试卷不存在")
    if exam.status != ExamStatus.PUBLISHED:
        raise ValueError("试卷未发布，无法开始考试")

    # Check if user already has an active session
    existing = await db.execute(
        select(AnswerSheet).where(
            and_(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.user_id == user_id,
                AnswerSheet.status == AnswerSheetStatus.IN_PROGRESS,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("您已有进行中的考试会话")

    sheet = AnswerSheet(
        exam_id=exam_id,
        user_id=user_id,
        status=AnswerSheetStatus.IN_PROGRESS,
    )
    db.add(sheet)
    await db.flush()
    return sheet


async def get_answer_sheet(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    load_answers: bool = False,
) -> Optional[AnswerSheet]:
    stmt = select(AnswerSheet).where(AnswerSheet.id == sheet_id)
    if load_answers:
        stmt = stmt.options(selectinload(AnswerSheet.answers))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_session(
    db: AsyncSession,
    exam_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[AnswerSheet]:
    """Get user's active exam session."""
    result = await db.execute(
        select(AnswerSheet).where(
            and_(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.user_id == user_id,
                AnswerSheet.status == AnswerSheetStatus.IN_PROGRESS,
            )
        ).options(selectinload(AnswerSheet.answers))
    )
    return result.scalar_one_or_none()


async def submit_answer(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    question_id: uuid.UUID,
    answer_content: str,
    user_id: uuid.UUID,
    time_spent_seconds: Optional[int] = None,
) -> Answer:
    """Submit or update an answer for a question."""
    sheet = await get_answer_sheet(db, sheet_id)
    if not sheet:
        raise ValueError("答题卡不存在")
    if sheet.user_id != user_id:
        raise ValueError("无权访问此答题卡")
    if sheet.status != AnswerSheetStatus.IN_PROGRESS:
        raise ValueError("考试已提交，无法修改答案")

    # Check if answer already exists
    existing = await db.execute(
        select(Answer).where(
            and_(
                Answer.answer_sheet_id == sheet_id,
                Answer.question_id == question_id,
            )
        )
    )
    answer = existing.scalar_one_or_none()

    if answer:
        answer.answer_content = answer_content
        answer.time_spent_seconds = time_spent_seconds
        answer.answered_at = datetime.now(timezone.utc)
    else:
        answer = Answer(
            answer_sheet_id=sheet_id,
            question_id=question_id,
            answer_content=answer_content,
            time_spent_seconds=time_spent_seconds,
            answered_at=datetime.now(timezone.utc),
        )
        db.add(answer)

    await db.flush()
    return answer


async def mark_question(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    question_id: uuid.UUID,
    is_marked: bool,
    user_id: uuid.UUID,
) -> Answer:
    """Mark/unmark a question for review."""
    sheet = await get_answer_sheet(db, sheet_id)
    if not sheet or sheet.user_id != user_id:
        raise ValueError("无权访问此答题卡")

    existing = await db.execute(
        select(Answer).where(
            and_(
                Answer.answer_sheet_id == sheet_id,
                Answer.question_id == question_id,
            )
        )
    )
    answer = existing.scalar_one_or_none()
    if not answer:
        answer = Answer(
            answer_sheet_id=sheet_id,
            question_id=question_id,
            is_marked=is_marked,
        )
        db.add(answer)
    else:
        answer.is_marked = is_marked

    await db.flush()
    return answer


async def submit_exam(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AnswerSheet:
    """Submit the exam (finish the session)."""
    sheet = await get_answer_sheet(db, sheet_id, load_answers=True)
    if not sheet:
        raise ValueError("答题卡不存在")
    if sheet.user_id != user_id:
        raise ValueError("无权操作此答题卡")
    if sheet.status != AnswerSheetStatus.IN_PROGRESS:
        raise ValueError("考试已提交")

    now = datetime.now(timezone.utc)
    sheet.status = AnswerSheetStatus.SUBMITTED
    sheet.submit_time = now
    sheet.duration_seconds = int((now - sheet.start_time).total_seconds())
    await db.flush()
    return sheet


async def get_exam_session_data(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Get full exam session data including questions (without answers)."""
    sheet = await get_answer_sheet(db, sheet_id, load_answers=True)
    if not sheet or sheet.user_id != user_id:
        raise ValueError("无权访问此答题卡")

    # Get exam info
    exam = (await db.execute(select(Exam).where(Exam.id == sheet.exam_id))).scalar_one()

    # Get exam questions with question details
    eq_result = await db.execute(
        select(ExamQuestion, Question)
        .join(Question, ExamQuestion.question_id == Question.id)
        .where(ExamQuestion.exam_id == sheet.exam_id)
        .order_by(ExamQuestion.order_num)
    )

    questions = []
    for eq, q in eq_result.all():
        # Use question_type_override from exam_question if set, otherwise fall back to original
        orig_type = q.question_type.value if hasattr(q.question_type, 'value') else q.question_type
        effective_type = eq.question_type_override or orig_type

        # Smart type detection: fix mismatches between declared type and actual content
        options = q.options or {}
        opt_keys = list(options.keys()) if isinstance(options, dict) else []

        # If options have T/F keys → true_false regardless of declared type
        if len(opt_keys) == 2 and "T" in opt_keys and "F" in opt_keys:
            effective_type = "true_false"
        # If declared as short_answer but has A/B/C/D options → single_choice
        elif effective_type == "short_answer" and len(opt_keys) >= 2 and all(k.isalpha() and len(k) == 1 for k in opt_keys):
            effective_type = "single_choice"

        # Ensure true_false questions always have standard T/F options
        if effective_type == "true_false":
            if not options or not isinstance(options, dict) or len(options) == 0:
                options = {"T": "正确", "F": "错误"}

        questions.append({
            "question_id": str(q.id),
            "order_num": eq.order_num,
            "score": eq.score,
            "question_type": effective_type,
            "stem": q.stem,
            "options": options,
            "difficulty": q.difficulty,
        })

    # Build answers map
    answers_map = {}
    for ans in sheet.answers:
        answers_map[str(ans.question_id)] = ans.answer_content

    return {
        "answer_sheet_id": str(sheet.id),
        "exam_title": exam.title,
        "time_limit_minutes": exam.time_limit_minutes,
        "start_time": sheet.start_time,
        "questions": questions,
        "answers": answers_map,
    }


async def list_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[AnswerSheet], int]:
    """List exam sessions for a user."""
    total = (await db.execute(
        select(func.count(AnswerSheet.id))
        .where(AnswerSheet.user_id == user_id)
    )).scalar()

    result = await db.execute(
        select(AnswerSheet)
        .where(AnswerSheet.user_id == user_id)
        .order_by(AnswerSheet.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total
