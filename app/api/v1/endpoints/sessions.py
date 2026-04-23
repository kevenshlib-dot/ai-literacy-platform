"""Exam session API endpoints - for examinees taking exams."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.answer import (
    StartExamResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    MarkQuestionRequest,
    SubmitExamResponse,
    AnswerSheetResponse,
    AnswerSheetWithScoreResponse,
    AnswerSheetDetailResponse,
    AnswerResponse,
    ExamSessionResponse,
    RandomTestRequest,
)
from app.services import answer_service
from app.models.exam import Exam, ExamQuestion
from app.models.answer import AnswerSheet, Answer, AnswerSheetStatus
from app.models.score import Score, ScoreDetail
from sqlalchemy import select, outerjoin, delete

router = APIRouter(prefix="/sessions", tags=["考试会话"])


@router.post("/random-test", response_model=StartExamResponse)
async def start_random_test(
    body: RandomTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a random test exam and start a session immediately."""
    from app.services import exam_service

    try:
        exam = await exam_service.create_random_test(
            db,
            user_id=current_user.id,
            count=body.count,
            difficulty_mode=body.difficulty_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Start session, then close the exam so it won't appear in published list
    sheet, resumed = await answer_service.start_exam(db, exam.id, current_user.id)
    eqs = await exam_service.get_exam_questions(db, exam.id)
    await exam_service.close_exam(db, exam.id)

    await db.commit()
    return StartExamResponse(
        answer_sheet_id=sheet.id,
        exam_id=exam.id,
        exam_title=exam.title,
        time_limit_minutes=exam.time_limit_minutes,
        total_questions=len(eqs),
        start_time=sheet.start_time,
        resumed=resumed,
    )


@router.post("/start/{exam_id}", response_model=StartExamResponse)
async def start_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Start an exam session."""
    try:
        sheet, resumed = await answer_service.start_exam(db, exam_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get exam info
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one()
    from app.services.exam_service import get_exam_questions
    eqs = await get_exam_questions(db, exam_id)

    await db.commit()
    return StartExamResponse(
        answer_sheet_id=sheet.id,
        exam_id=exam_id,
        exam_title=exam.title,
        time_limit_minutes=exam.time_limit_minutes,
        total_questions=len(eqs),
        start_time=sheet.start_time,
        resumed=resumed,
    )


@router.get("/{sheet_id}", response_model=ExamSessionResponse)
async def get_session(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get exam session with questions and current answers."""
    try:
        data = await answer_service.get_exam_session_data(db, sheet_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@router.post("/{sheet_id}/answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    sheet_id: UUID,
    body: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit or update an answer for a question."""
    try:
        answer = await answer_service.submit_answer(
            db=db,
            sheet_id=sheet_id,
            question_id=body.question_id,
            answer_content=body.answer_content,
            user_id=current_user.id,
            time_spent_seconds=body.time_spent_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return SubmitAnswerResponse(
        id=answer.id,
        question_id=answer.question_id,
        answer_content=answer.answer_content,
        is_marked=answer.is_marked,
        answered_at=answer.answered_at,
    )


@router.post("/{sheet_id}/mark", response_model=SubmitAnswerResponse)
async def mark_question(
    sheet_id: UUID,
    body: MarkQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mark/unmark a question for later review."""
    try:
        answer = await answer_service.mark_question(
            db, sheet_id, body.question_id, body.is_marked, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return SubmitAnswerResponse(
        id=answer.id,
        question_id=answer.question_id,
        answer_content=answer.answer_content or "",
        is_marked=answer.is_marked,
        answered_at=answer.answered_at,
    )


@router.post("/{sheet_id}/submit", response_model=SubmitExamResponse)
async def submit_exam(
    sheet_id: UUID,
    auto_score: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit the exam (finish the session) and auto-score."""
    try:
        sheet = await answer_service.submit_exam(db, sheet_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_answered = len([a for a in sheet.answers if a.answer_content])
    # Count total questions
    from app.services.exam_service import get_exam_questions
    eqs = await get_exam_questions(db, sheet.exam_id)
    answer_sheet_id = sheet.id
    response_status = sheet.status.value
    submit_time = sheet.submit_time
    duration_seconds = sheet.duration_seconds

    # Persist the submitted sheet first so scoring failures don't undo the submission.
    await db.commit()

    logger = logging.getLogger(__name__)
    if auto_score:
        try:
            from app.services import score_service
            await score_service.score_answer_sheet(db, answer_sheet_id)
            await db.commit()
            response_status = AnswerSheetStatus.SCORED.value
            logger.info(f"Auto-scored answer sheet {answer_sheet_id}")
        except Exception as e:
            await db.rollback()
            logger.warning(f"Auto-scoring failed for sheet {answer_sheet_id}: {e}")

    return SubmitExamResponse(
        answer_sheet_id=answer_sheet_id,
        status=response_status,
        submit_time=submit_time,
        duration_seconds=duration_seconds,
        total_answered=total_answered,
        total_questions=len(eqs),
    )


@router.delete("/random-test/{sheet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_random_test(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Clean up all data from a random test session (scores not retained)."""
    sheet = (await db.execute(
        select(AnswerSheet).where(
            AnswerSheet.id == sheet_id,
            AnswerSheet.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="答题卡不存在")

    exam_id = sheet.exam_id

    # Delete score details → score
    score = (await db.execute(
        select(Score).where(Score.answer_sheet_id == sheet_id)
    )).scalar_one_or_none()
    if score:
        await db.execute(delete(ScoreDetail).where(ScoreDetail.score_id == score.id))
        await db.delete(score)

    # Delete answers → answer sheet
    await db.execute(delete(Answer).where(Answer.answer_sheet_id == sheet_id))
    await db.delete(sheet)

    # Delete exam questions → exam
    await db.execute(delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id))
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if exam:
        await db.delete(exam)

    await db.commit()


@router.get("", response_model=list[AnswerSheetWithScoreResponse])
async def list_my_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List current user's exam sessions with exam title and score data."""
    result = await db.execute(
        select(AnswerSheet, Exam.title, Score)
        .join(Exam, AnswerSheet.exam_id == Exam.id)
        .outerjoin(Score, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.user_id == current_user.id)
        .where(AnswerSheet.is_deleted == False)
        .where(~Exam.title.startswith("随机测试"))
        .order_by(AnswerSheet.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    return [
        AnswerSheetWithScoreResponse(
            id=sheet.id,
            exam_id=sheet.exam_id,
            user_id=sheet.user_id,
            status=sheet.status.value if hasattr(sheet.status, 'value') else sheet.status,
            start_time=sheet.start_time,
            submit_time=sheet.submit_time,
            duration_seconds=sheet.duration_seconds,
            created_at=sheet.created_at,
            exam_title=exam_title,
            total_score=score.total_score if score else None,
            max_score=score.max_score if score else None,
            level=score.level if score else None,
            percentile_rank=score.percentile_rank if score else None,
            score_id=score.id if score else None,
            scored_at=score.scored_at if score else None,
        )
        for sheet, exam_title, score in rows
    ]


@router.get("/{sheet_id}/detail", response_model=AnswerSheetDetailResponse)
async def get_session_detail(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get answer sheet with all answers."""
    sheet = await answer_service.get_answer_sheet(db, sheet_id, load_answers=True)
    if not sheet or sheet.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="答题卡不存在")

    return AnswerSheetDetailResponse(
        id=sheet.id,
        exam_id=sheet.exam_id,
        user_id=sheet.user_id,
        status=sheet.status.value if hasattr(sheet.status, 'value') else sheet.status,
        start_time=sheet.start_time,
        submit_time=sheet.submit_time,
        duration_seconds=sheet.duration_seconds,
        created_at=sheet.created_at,
        answers=[
            AnswerResponse(
                id=a.id,
                question_id=a.question_id,
                answer_content=a.answer_content,
                is_marked=a.is_marked,
                time_spent_seconds=a.time_spent_seconds,
                answered_at=a.answered_at,
            )
            for a in sheet.answers
        ],
    )
