"""Indicator management endpoints - dynamic indicator generation."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services.indicator_service import (
    generate_indicator_proposals,
    list_proposals,
    approve_proposal,
    reject_proposal,
)

router = APIRouter(prefix="/indicators", tags=["指标管理"])


@router.post("/generate")
async def generate_proposals(
    topic: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Run three-agent pipeline to generate indicator update proposals."""
    result = await generate_indicator_proposals(db, topic)
    await db.commit()
    return result


@router.get("")
async def get_proposals(
    status: Optional[str] = Query(None),
    dimension: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """List indicator proposals."""
    return await list_proposals(db, status, dimension)


@router.post("/{proposal_id}/approve")
async def approve(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Approve an indicator proposal (human confirmation)."""
    try:
        result = await approve_proposal(db, proposal_id, current_user.id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{proposal_id}/reject")
async def reject(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Reject an indicator proposal."""
    try:
        result = await reject_proposal(db, proposal_id, current_user.id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
