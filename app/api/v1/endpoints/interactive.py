"""Interactive scenario session API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.interactive import (
    StartInteractiveRequest,
    InteractiveResponseRequest,
    InteractiveSessionResponse,
    InteractiveSessionDetailResponse,
    InteractiveTurnResponse,
    InteractiveTurnResultResponse,
)
from app.services import interactive_service
from app.services import process_scoring_service

router = APIRouter(prefix="/interactive", tags=["情境交互"])


@router.post("", response_model=InteractiveSessionDetailResponse)
async def start_session(
    body: StartInteractiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Start a new interactive scenario session."""
    session = await interactive_service.start_interactive_session(
        db=db,
        user_id=current_user.id,
        scenario=body.scenario,
        role_description=body.role_description,
        dimension=body.dimension,
        difficulty=body.difficulty,
        max_turns=body.max_turns,
        answer_sheet_id=body.answer_sheet_id,
        question_id=body.question_id,
    )
    await db.commit()

    # Reload with turns
    session = await interactive_service.get_session_with_turns(db, session.id)
    return _to_detail_response(session)


@router.get("", response_model=list[InteractiveSessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List user's interactive sessions."""
    sessions = await interactive_service.list_user_interactive_sessions(
        db, current_user.id
    )
    return [_to_response(s) for s in sessions]


@router.get("/{session_id}", response_model=InteractiveSessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get interactive session with all turns."""
    session = await interactive_service.get_session_with_turns(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此会话")
    return _to_detail_response(session)


@router.post("/{session_id}/respond", response_model=InteractiveTurnResultResponse)
async def submit_response(
    session_id: UUID,
    body: InteractiveResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit a response in an interactive session."""
    try:
        result = await interactive_service.submit_interactive_response(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            user_message=body.message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return InteractiveTurnResultResponse(**result)


@router.get("/{session_id}/process-score")
async def get_process_score(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get process-based scoring for a completed interactive session (T021)."""
    try:
        result = await process_scoring_service.score_interactive_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


@router.post("/{session_id}/end", response_model=InteractiveSessionDetailResponse)
async def end_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Manually end an interactive session."""
    try:
        session = await interactive_service.end_session(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()

    # Reload
    session = await interactive_service.get_session_with_turns(db, session.id)
    return _to_detail_response(session)


def _to_response(session) -> InteractiveSessionResponse:
    return InteractiveSessionResponse(
        id=session.id,
        scenario=session.scenario,
        role_description=session.role_description,
        dimension=session.dimension,
        status=session.status.value if hasattr(session.status, 'value') else session.status,
        current_difficulty=session.current_difficulty,
        max_turns=session.max_turns,
        created_at=session.created_at,
        completed_at=session.completed_at,
        final_summary=session.final_summary,
    )


def _to_detail_response(session) -> InteractiveSessionDetailResponse:
    resp = _to_response(session).model_dump()
    resp["turns"] = [
        InteractiveTurnResponse(
            id=t.id,
            turn_number=t.turn_number,
            role=t.role,
            content=t.content,
            ai_analysis=t.ai_analysis,
            created_at=t.created_at,
        )
        for t in (session.turns or [])
    ]
    return InteractiveSessionDetailResponse(**resp)
