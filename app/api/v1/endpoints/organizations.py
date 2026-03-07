"""Organization management endpoints - multi-tenant support."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services.organization_service import (
    create_organization,
    get_organization,
    list_organizations,
    update_organization,
    update_org_config,
    add_user_to_org,
    remove_user_from_org,
    get_org_members,
    get_org_stats,
)

router = APIRouter(prefix="/organizations", tags=["机构管理"])


class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    config: Optional[dict] = None
    max_users: int = Field(100, ge=1, le=10000)


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    max_users: Optional[int] = None
    is_active: Optional[bool] = None


@router.post("")
async def create_org(
    req: OrgCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Create a new organization."""
    try:
        org = await create_organization(
            db,
            name=req.name,
            slug=req.slug,
            description=req.description,
            logo_url=req.logo_url,
            contact_email=req.contact_email,
            contact_phone=req.contact_phone,
            config=req.config,
            max_users=req.max_users,
        )
        await db.commit()
        return {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """List all organizations."""
    orgs = await list_organizations(db)
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "slug": o.slug,
            "is_active": o.is_active,
            "max_users": o.max_users,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orgs
    ]


@router.get("/{org_id}")
async def get_org(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get organization details."""
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="机构不存在")
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "description": org.description,
        "logo_url": org.logo_url,
        "contact_email": org.contact_email,
        "config": org.config,
        "is_active": org.is_active,
        "max_users": org.max_users,
    }


@router.put("/{org_id}")
async def update_org(
    org_id: uuid.UUID,
    req: OrgUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Update organization details."""
    org = await update_organization(db, org_id, **req.model_dump(exclude_none=True))
    if not org:
        raise HTTPException(status_code=404, detail="机构不存在")
    await db.commit()
    return {"id": str(org.id), "name": org.name, "updated": True}


@router.put("/{org_id}/config")
async def update_config(
    org_id: uuid.UUID,
    config: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Update organization config (merges with existing)."""
    result = await update_org_config(db, org_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="机构不存在")
    await db.commit()
    return {"config": result}


@router.post("/{org_id}/members/{user_id}")
async def add_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Add a user to an organization."""
    try:
        result = await add_user_to_org(db, org_id, user_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{org_id}/members/{user_id}")
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Remove a user from an organization."""
    removed = await remove_user_from_org(db, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.commit()
    return {"removed": True}


@router.get("/{org_id}/members")
async def list_members(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List members of an organization."""
    return await get_org_members(db, org_id)


@router.get("/{org_id}/stats")
async def org_stats(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get organization statistics."""
    try:
        return await get_org_stats(db, org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
