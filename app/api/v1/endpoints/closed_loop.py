"""Assessment-Training Closed Loop endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services import closed_loop_service

router = APIRouter(prefix="/closed-loop", tags=["测评培训闭环"])


@router.get("/journey")
async def get_journey(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's assessment-training journey overview."""
    return await closed_loop_service.get_user_journey(db, current_user.id)


@router.get("/comparison")
async def get_comparison(
    pre_score_id: Optional[uuid.UUID] = Query(None),
    post_score_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get before/after comparison report."""
    return await closed_loop_service.get_comparison_report(
        db, current_user.id, pre_score_id, post_score_id,
    )


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get closed-loop statistics for the current user."""
    return await closed_loop_service.get_closed_loop_stats(db, current_user.id)


@router.get("/stats/platform")
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get platform-wide closed-loop statistics (admin only)."""
    return await closed_loop_service.get_closed_loop_stats(db)
