"""Practice sandbox endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services import sandbox_service

router = APIRouter(prefix="/sandbox", tags=["实践沙箱"])


class CreateSessionRequest(BaseModel):
    sandbox_type: str
    title: str = Field(..., min_length=1, max_length=200)
    task_prompt: str = Field(..., min_length=1)
    description: Optional[str] = None
    dimension: Optional[str] = None
    difficulty: int = Field(3, ge=1, le=5)


class SubmitAttemptRequest(BaseModel):
    user_input: str = Field(..., min_length=1)


def _session_response(s):
    return {
        "id": str(s.id),
        "user_id": str(s.user_id),
        "sandbox_type": s.sandbox_type.value if hasattr(s.sandbox_type, 'value') else s.sandbox_type,
        "title": s.title,
        "description": s.description,
        "task_prompt": s.task_prompt,
        "dimension": s.dimension,
        "difficulty": s.difficulty,
        "status": s.status.value if hasattr(s.status, 'value') else s.status,
        "score": s.score,
        "evaluation": s.evaluation,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "attempts": [_attempt_response(a) for a in s.attempts] if hasattr(s, 'attempts') and s.attempts else [],
    }


def _attempt_response(a):
    return {
        "id": str(a.id),
        "attempt_number": a.attempt_number,
        "user_input": a.user_input,
        "ai_output": a.ai_output,
        "feedback": a.feedback,
        "score": a.score,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/tasks")
async def list_tasks(
    sandbox_type: Optional[str] = Query(None),
    dimension: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """List available practice tasks."""
    return await sandbox_service.list_practice_tasks(sandbox_type, dimension)


@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new sandbox session."""
    session = await sandbox_service.create_session(
        db, user_id=current_user.id,
        sandbox_type=req.sandbox_type,
        title=req.title,
        task_prompt=req.task_prompt,
        description=req.description,
        dimension=req.dimension,
        difficulty=req.difficulty,
    )
    await db.commit()
    s = await sandbox_service.get_session(db, session.id)
    return _session_response(s)


@router.get("/sessions")
async def list_sessions(
    sandbox_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's sandbox sessions."""
    sessions = await sandbox_service.list_user_sessions(db, current_user.id, sandbox_type)
    return [_session_response(s) for s in sessions]


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get practice statistics."""
    return await sandbox_service.get_user_practice_stats(db, current_user.id)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get sandbox session detail."""
    s = await sandbox_service.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _session_response(s)


@router.post("/sessions/{session_id}/attempt")
async def submit_attempt(
    session_id: uuid.UUID,
    req: SubmitAttemptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit an attempt in a sandbox session."""
    try:
        attempt = await sandbox_service.submit_attempt(db, session_id, req.user_input)
        await db.commit()
        return _attempt_response(attempt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete a sandbox session and get final evaluation."""
    try:
        s = await sandbox_service.complete_session(db, session_id)
        await db.commit()
        return _session_response(s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
