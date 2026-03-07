"""Adaptive learning endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services import adaptive_learning_service

router = APIRouter(prefix="/learning", tags=["自适应学习"])


class GeneratePathRequest(BaseModel):
    focus_dimensions: Optional[list[str]] = None


class UpdateStepRequest(BaseModel):
    status: str
    score: Optional[float] = None


def _path_response(path):
    return {
        "id": str(path.id),
        "user_id": str(path.user_id),
        "title": path.title,
        "description": path.description,
        "status": path.status.value if hasattr(path.status, 'value') else path.status,
        "weakness_dimensions": path.weakness_dimensions,
        "target_dimensions": path.target_dimensions,
        "progress_percent": path.progress_percent,
        "created_at": path.created_at.isoformat() if path.created_at else None,
        "steps": [_step_response(s) for s in path.steps] if path.steps else [],
    }


def _step_response(step):
    return {
        "id": str(step.id),
        "order_num": step.order_num,
        "step_type": step.step_type.value if hasattr(step.step_type, 'value') else step.step_type,
        "title": step.title,
        "description": step.description,
        "dimension": step.dimension,
        "resource_id": str(step.resource_id) if step.resource_id else None,
        "status": step.status.value if hasattr(step.status, 'value') else step.status,
        "score": step.score,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
    }


@router.get("/analysis")
async def get_weakness_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze current user's dimension weaknesses."""
    return await adaptive_learning_service.analyze_user_weakness(db, current_user.id)


@router.post("/paths")
async def generate_path(
    req: GeneratePathRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a personalized learning path."""
    path = await adaptive_learning_service.generate_learning_path(
        db, current_user.id, req.focus_dimensions,
    )
    await db.commit()
    return _path_response(path)


@router.get("/paths")
async def list_paths(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's learning paths."""
    paths = await adaptive_learning_service.list_user_paths(db, current_user.id)
    return [_path_response(p) for p in paths]


@router.get("/paths/{path_id}")
async def get_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get learning path detail."""
    path = await adaptive_learning_service.get_learning_path(db, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="学习路径不存在")
    return _path_response(path)


@router.get("/paths/{path_id}/next")
async def get_next(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the next step to work on."""
    step = await adaptive_learning_service.get_next_step(db, path_id)
    if not step:
        return {"message": "所有步骤已完成", "completed": True}
    return step


@router.put("/steps/{step_id}")
async def update_step(
    step_id: uuid.UUID,
    req: UpdateStepRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a learning step status."""
    step = await adaptive_learning_service.update_step_status(
        db, step_id, req.status, req.score,
    )
    if not step:
        raise HTTPException(status_code=404, detail="学习步骤不存在")
    await db.commit()
    return _step_response(step)


@router.get("/recommendations")
async def get_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personalized course recommendations."""
    return await adaptive_learning_service.get_recommendations(db, current_user.id)
