"""Report management endpoints - monthly reports and analytics."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.models.user import User
from app.services.monthly_report_service import (
    generate_monthly_report,
    list_reports,
    get_report_detail,
)

router = APIRouter(prefix="/reports", tags=["报告管理"])


@router.post("/monthly")
async def create_monthly_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Generate a monthly operations report."""
    result = await generate_monthly_report(db, year, month)
    await db.commit()
    return result


@router.get("")
async def get_reports(
    report_type: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """List all reports."""
    return await list_reports(db, report_type)


@router.get("/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Get a specific report with full content."""
    result = await get_report_detail(db, report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")
    return result
