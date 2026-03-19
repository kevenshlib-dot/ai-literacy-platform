"""Exam management API endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_role
from app.models.user import User
from app.schemas.exam import (
    ExamCreate,
    ExamUpdate,
    ExamResponse,
    ExamDetailResponse,
    ExamCompositionResponse,
    ExamCompositionItemResponse,
    ExamCompositionUpdateRequest,
    ExamQuestionSummaryResponse,
    ExamListResponse,
    ExamQuestionResponse,
    ManualAssembleRequest,
    AutoAssembleRequest,
    AssembleResponse,
    IntentAssembleRequest,
    IntentParseResponse,
    IntentAssembleResponse,
)
from app.services import exam_service
from app.agents.intent_agent import parse_intent_via_llm

router = APIRouter(prefix="/exams", tags=["考试管理"])


def _to_response(exam) -> ExamResponse:
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        status=exam.status.value if hasattr(exam.status, 'value') else exam.status,
        total_score=exam.total_score,
        time_limit_minutes=exam.time_limit_minutes,
        params=exam.params,
        usage_count=exam.usage_count,
        avg_score=exam.avg_score,
        created_by=exam.created_by,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
    )


def _eq_to_response(eq) -> ExamQuestionResponse:
    return ExamQuestionResponse(
        id=eq.id,
        question_id=eq.question_id,
        order_num=eq.order_num,
        score=eq.score,
    )


def _question_summary_to_response(question) -> ExamQuestionSummaryResponse:
    return ExamQuestionSummaryResponse(
        id=question.id,
        question_type=question.question_type.value if hasattr(question.question_type, "value") else question.question_type,
        stem=question.stem,
        options=question.options,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        difficulty=question.difficulty,
        dimension=question.dimension,
        status=question.status.value if hasattr(question.status, "value") else question.status,
    )


def _composition_item_to_response(eq, question) -> ExamCompositionItemResponse:
    return ExamCompositionItemResponse(
        id=eq.id,
        question_id=eq.question_id,
        order_num=eq.order_num,
        score=eq.score,
        question=_question_summary_to_response(question),
    )


# ---- Fixed-path routes first ----

@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Create a new exam."""
    exam = await exam_service.create_exam(
        db=db,
        title=body.title,
        created_by=current_user.id,
        description=body.description,
        time_limit_minutes=body.time_limit_minutes,
        total_score=body.total_score,
    )
    await db.commit()
    return _to_response(exam)


@router.get("", response_model=ExamListResponse)
async def list_exams(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = None,
    is_random_test: Optional[bool] = Query(None),
    archive: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List exams with filters."""
    items, total = await exam_service.list_exams(
        db=db, skip=skip, limit=limit, status=status_filter, keyword=keyword,
        is_random_test=is_random_test, archive=archive,
    )
    return ExamListResponse(
        total=total,
        items=[_to_response(e) for e in items],
    )


@router.get("/stats")
async def exam_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await exam_service.get_exam_stats(db)


@router.post("/intent/parse", response_model=IntentParseResponse)
async def parse_intent(
    body: IntentAssembleRequest,
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Parse natural language description into assembly parameters (preview only)."""
    parsed = parse_intent_via_llm(body.description)
    return IntentParseResponse(**parsed)


@router.post("/intent/assemble", response_model=IntentAssembleResponse)
async def intent_assemble(
    body: IntentAssembleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Parse natural language and auto-create + assemble an exam in one step."""
    parsed = parse_intent_via_llm(body.description)

    # Create exam
    exam = await exam_service.create_exam(
        db=db,
        title=parsed["title"],
        created_by=current_user.id,
        description=parsed.get("description"),
        time_limit_minutes=parsed.get("time_limit_minutes"),
    )

    # Auto-assemble
    try:
        eqs = await exam_service.auto_assemble(
            db=db,
            exam_id=exam.id,
            type_distribution=parsed["type_distribution"],
            difficulty_target=parsed["difficulty"],
            difficulty_tolerance=1,
            dimensions=parsed.get("dimensions"),
            score_per_question=parsed.get("score_per_question", 5.0),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    total_score = sum(eq.score for eq in eqs)
    return IntentAssembleResponse(
        parsed_params=IntentParseResponse(**parsed),
        exam=_to_response(exam),
        assembly=AssembleResponse(
            exam_id=exam.id,
            total_questions=len(eqs),
            total_score=total_score,
            questions=[_eq_to_response(eq) for eq in eqs],
        ),
    )


# ---- Dynamic path routes ----


@router.get("/{exam_id}/analysis")
async def analyze_exam_questions(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Analyze all questions in an exam (CTT/IRT metrics + Cronbach's alpha)."""
    from app.services.question_analysis_service import analyze_exam_questions as _analyze
    result = await _analyze(db, exam_id)
    await db.commit()
    return result


@router.get("/{exam_id}/composition", response_model=ExamCompositionResponse)
async def get_exam_composition(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    exam = await exam_service.get_exam_by_id(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")
    rows = await exam_service.get_exam_composition(db, exam_id)
    return ExamCompositionResponse(
        exam=_to_response(exam),
        items=[_composition_item_to_response(eq, question) for eq, question in rows],
    )


@router.put("/{exam_id}/composition", response_model=ExamCompositionResponse)
async def save_exam_composition(
    exam_id: UUID,
    body: ExamCompositionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    try:
        exam, rows = await exam_service.save_exam_composition(
            db=db,
            exam_id=exam_id,
            items=[item.model_dump() for item in body.items],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ExamCompositionResponse(
        exam=_to_response(exam),
        items=[_composition_item_to_response(eq, question) for eq, question in rows],
    )


@router.get("/{exam_id}", response_model=ExamDetailResponse)
async def get_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    exam = await exam_service.get_exam_by_id(db, exam_id, load_questions=True)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")
    resp = _to_response(exam).model_dump()
    resp["questions"] = [_eq_to_response(eq) for eq in exam.questions]
    return ExamDetailResponse(**resp)


@router.put("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: UUID,
    body: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    exam = await exam_service.update_exam(
        db, exam_id, **body.model_dump(exclude_unset=True)
    )
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")
    await db.commit()
    return _to_response(exam)


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    deleted = await exam_service.delete_exam(db, exam_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="试卷不存在")
    await db.commit()


@router.post("/{exam_id}/publish", response_model=ExamResponse)
async def publish_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Publish an exam (must have questions)."""
    try:
        exam = await exam_service.publish_exam(db, exam_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")
    await db.commit()
    return _to_response(exam)


@router.post("/{exam_id}/close", response_model=ExamResponse)
async def close_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Close an exam."""
    exam = await exam_service.close_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")
    await db.commit()
    return _to_response(exam)


@router.post("/{exam_id}/reactivate", response_model=ExamResponse)
async def reactivate_exam(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Reactivate a closed exam back to published status (admin only)."""
    exam = await exam_service.get_exam_by_id(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")

    from app.models.exam import ExamStatus
    if exam.status != ExamStatus.CLOSED:
        raise HTTPException(status_code=400, detail="只有已关闭的试卷才能重新激活")

    exam.status = ExamStatus.PUBLISHED
    await db.commit()
    return _to_response(exam)


@router.get("/{exam_id}/questions", response_model=list[ExamQuestionResponse])
async def get_exam_questions(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get questions in an exam."""
    eqs = await exam_service.get_exam_questions(db, exam_id)
    return [_eq_to_response(eq) for eq in eqs]


@router.post("/{exam_id}/assemble/manual", response_model=AssembleResponse)
async def manual_assemble(
    exam_id: UUID,
    body: ManualAssembleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Manually assign questions to an exam."""
    try:
        eqs = await exam_service.manual_assemble(
            db, exam_id,
            [q.model_dump() for q in body.questions],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()

    total_score = sum(eq.score for eq in eqs)
    return AssembleResponse(
        exam_id=exam_id,
        total_questions=len(eqs),
        total_score=total_score,
        questions=[_eq_to_response(eq) for eq in eqs],
    )


@router.post("/{exam_id}/assemble/auto", response_model=AssembleResponse)
async def auto_assemble(
    exam_id: UUID,
    body: AutoAssembleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Auto-assemble an exam using strategy constraints."""
    try:
        eqs = await exam_service.auto_assemble(
            db=db,
            exam_id=exam_id,
            type_distribution=body.type_distribution,
            difficulty_target=body.difficulty_target,
            difficulty_tolerance=body.difficulty_tolerance,
            dimensions=body.dimensions,
            score_per_question=body.score_per_question,
            exclude_question_ids=body.exclude_question_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()

    total_score = sum(eq.score for eq in eqs)
    return AssembleResponse(
        exam_id=exam_id,
        total_questions=len(eqs),
        total_score=total_score,
        questions=[_eq_to_response(eq) for eq in eqs],
    )
