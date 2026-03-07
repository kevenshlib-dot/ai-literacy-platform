"""Organization service - multi-tenant management."""
import re
import uuid
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User


async def create_organization(
    db: AsyncSession,
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    logo_url: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    config: Optional[dict] = None,
    max_users: int = 100,
) -> Organization:
    """Create a new organization."""
    if not slug:
        slug = _generate_slug(name)

    # Check uniqueness
    existing = (await db.execute(
        select(Organization).where(
            (Organization.name == name) | (Organization.slug == slug)
        )
    )).scalar_one_or_none()
    if existing:
        raise ValueError("机构名称或标识已存在")

    org = Organization(
        name=name,
        slug=slug,
        description=description,
        logo_url=logo_url,
        contact_email=contact_email,
        contact_phone=contact_phone,
        config=config or {},
        max_users=max_users,
    )
    db.add(org)
    await db.flush()
    return org


async def get_organization(db: AsyncSession, org_id: uuid.UUID) -> Optional[Organization]:
    """Get organization by ID."""
    return (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()


async def get_organization_by_slug(db: AsyncSession, slug: str) -> Optional[Organization]:
    """Get organization by slug."""
    return (await db.execute(
        select(Organization).where(Organization.slug == slug)
    )).scalar_one_or_none()


async def list_organizations(db: AsyncSession) -> list[Organization]:
    """List all organizations."""
    result = await db.execute(
        select(Organization).order_by(Organization.created_at.desc())
    )
    return list(result.scalars().all())


async def update_organization(
    db: AsyncSession,
    org_id: uuid.UUID,
    **kwargs,
) -> Optional[Organization]:
    """Update organization details."""
    org = await get_organization(db, org_id)
    if not org:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(org, key):
            setattr(org, key, value)

    await db.flush()
    return org


async def update_org_config(
    db: AsyncSession,
    org_id: uuid.UUID,
    config_updates: dict,
) -> Optional[dict]:
    """Update organization config (merge with existing)."""
    org = await get_organization(db, org_id)
    if not org:
        return None

    current_config = org.config or {}
    current_config.update(config_updates)
    org.config = current_config
    await db.flush()
    return org.config


async def add_user_to_org(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Add a user to an organization."""
    org = await get_organization(db, org_id)
    if not org:
        raise ValueError("机构不存在")

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise ValueError("用户不存在")

    # Check max users
    member_count = (await db.execute(
        select(func.count(User.id)).where(User.org_id == org_id)
    )).scalar() or 0

    if member_count >= org.max_users:
        raise ValueError(f"机构成员已达上限({org.max_users}人)")

    user.org_id = org_id
    user.organization = org.name
    await db.flush()

    return {"user_id": str(user_id), "org_id": str(org_id), "org_name": org.name}


async def remove_user_from_org(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    """Remove a user from their organization."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        return False

    user.org_id = None
    await db.flush()
    return True


async def get_org_members(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[dict]:
    """List members of an organization."""
    result = await db.execute(
        select(User).where(User.org_id == org_id).order_by(User.created_at)
    )
    users = list(result.scalars().all())

    return [
        {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "role_id": str(u.role_id),
            "is_active": u.is_active,
        }
        for u in users
    ]


async def get_org_stats(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """Get organization statistics."""
    member_count = (await db.execute(
        select(func.count(User.id)).where(User.org_id == org_id)
    )).scalar() or 0

    org = await get_organization(db, org_id)
    if not org:
        raise ValueError("机构不存在")

    return {
        "org_id": str(org_id),
        "name": org.name,
        "member_count": member_count,
        "max_users": org.max_users,
        "is_active": org.is_active,
    }


def _generate_slug(name: str) -> str:
    """Generate URL-safe slug from org name."""
    slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', name.lower()).strip('-')
    return slug[:100]
