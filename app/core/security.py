from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
    issued_at: Optional[datetime] = None,
) -> str:
    token_issued_at = issued_at or datetime.now(timezone.utc)
    if expires_delta:
        expire = token_issued_at + expires_delta
    else:
        expire = token_issued_at + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "iat": token_issued_at, "sub": str(subject)}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def get_token_issued_at(payload: dict) -> datetime | None:
    issued_at = payload.get("iat")
    if issued_at is None:
        return None
    if isinstance(issued_at, (int, float)):
        return datetime.fromtimestamp(issued_at, tz=timezone.utc)
    if isinstance(issued_at, datetime):
        if issued_at.tzinfo is None:
            return issued_at.replace(tzinfo=timezone.utc)
        return issued_at.astimezone(timezone.utc)
    raise JWTError("Invalid iat claim")
