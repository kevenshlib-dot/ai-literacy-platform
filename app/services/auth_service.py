import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_app_now() -> datetime:
    return utc_now().astimezone(ZoneInfo(settings.APP_TIMEZONE))


def get_end_of_app_day(now: datetime | None = None) -> datetime:
    local_now = (now or utc_now()).astimezone(ZoneInfo(settings.APP_TIMEZONE))
    next_day = (local_now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_day - timedelta(microseconds=1)).astimezone(timezone.utc)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_refresh_cookie_max_age(expires_at: datetime, now: datetime | None = None) -> int:
    delta = expires_at - (now or utc_now())
    return max(int(delta.total_seconds()), 0)


def get_access_token_issue_time(user: User, now: datetime | None = None) -> datetime:
    issued_at = (now or utc_now()).replace(microsecond=0)
    if user.token_invalid_before and issued_at <= user.token_invalid_before:
        issued_at = user.token_invalid_before + timedelta(seconds=1)
    return issued_at


def invalidate_user_tokens(user: User, at: datetime | None = None) -> datetime:
    invalid_before = (at or utc_now()).replace(microsecond=0)
    user.token_invalid_before = invalid_before
    return invalid_before


async def create_auth_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    expires_at: datetime | None = None,
) -> tuple[AuthSession, str]:
    refresh_token = generate_refresh_token()
    session = AuthSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=expires_at or get_end_of_app_day(),
        last_used_at=utc_now(),
    )
    db.add(session)
    await db.flush()
    return session, refresh_token


async def get_auth_session_by_refresh_token(
    db: AsyncSession,
    refresh_token: str,
) -> AuthSession | None:
    result = await db.execute(
        select(AuthSession)
        .options(selectinload(AuthSession.user).selectinload(User.role))
        .where(AuthSession.refresh_token_hash == hash_refresh_token(refresh_token))
    )
    return result.scalar_one_or_none()


async def rotate_auth_session(
    db: AsyncSession,
    session: AuthSession,
) -> tuple[AuthSession, str]:
    refresh_token = generate_refresh_token()
    session.refresh_token_hash = hash_refresh_token(refresh_token)
    session.expires_at = get_end_of_app_day()
    session.last_used_at = utc_now()
    await db.flush()
    return session, refresh_token


async def revoke_auth_session(
    db: AsyncSession,
    session: AuthSession,
    at: datetime | None = None,
) -> None:
    if session.revoked_at is None:
        session.revoked_at = at or utc_now()
        await db.flush()


async def revoke_user_auth_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    at: datetime | None = None,
) -> None:
    revoked_at = at or utc_now()
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
    await db.flush()


def is_auth_session_usable(session: AuthSession, now: datetime | None = None) -> bool:
    current_time = now or utc_now()
    return session.revoked_at is None and session.expires_at > current_time
