import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash, verify_password
from app.models.user import User, Role, RoleEnum


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_or_create_role(db: AsyncSession, role_name: str) -> Role:
    try:
        role_enum = RoleEnum(role_name)
    except ValueError:
        role_enum = RoleEnum.EXAMINEE

    result = await db.execute(select(Role).where(Role.name == role_enum))
    role = result.scalar_one_or_none()
    if not role:
        role = Role(name=role_enum, description=role_enum.value)
        db.add(role)
        await db.flush()
    return role


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    role_name: str = "examinee",
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    organization: Optional[str] = None,
    is_active: bool = True,
) -> User:
    role = await get_or_create_role(db, role_name)
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        phone=phone,
        organization=organization,
        role_id=role.id,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, ["role"])
    return user


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def update_password(
    db: AsyncSession, user: User, new_password: str
) -> User:
    user.hashed_password = get_password_hash(new_password)
    await db.flush()
    return user


async def soft_delete_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Soft-delete a user by setting is_deleted=True and deactivating."""
    user = await get_user_by_id(db, user_id)
    if not user or user.is_deleted:
        return None
    user.is_deleted = True
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def restore_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Restore a soft-deleted user."""
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_deleted:
        return None
    user.is_deleted = False
    user.is_active = True
    user.deleted_at = None
    await db.flush()
    return user


async def list_deleted_users(
    db: AsyncSession,
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[User], int]:
    """List soft-deleted users for archive view."""
    query = select(User).options(selectinload(User.role)).where(User.is_deleted == True)
    count_q = select(func.count(User.id)).where(User.is_deleted == True)

    if role:
        query = query.join(Role).where(Role.name == role)
        count_q = count_q.join(Role).where(Role.name == role)
    if keyword:
        kw_cond = (
            User.username.ilike(f"%{keyword}%")
            | User.email.ilike(f"%{keyword}%")
            | User.full_name.ilike(f"%{keyword}%")
        )
        query = query.where(kw_cond)
        count_q = count_q.where(kw_cond)

    query = query.order_by(User.deleted_at.desc())
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(skip).limit(limit))
    users = list(result.scalars().all())
    return users, total


async def init_roles(db: AsyncSession) -> None:
    for role_enum in RoleEnum:
        result = await db.execute(select(Role).where(Role.name == role_enum))
        if not result.scalar_one_or_none():
            db.add(Role(name=role_enum, description=role_enum.value))
    await db.flush()
