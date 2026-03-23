import os

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def _allow_non_test_schema_ops() -> bool:
    return os.getenv("ALLOW_NON_TEST_SCHEMA_OPS", "").lower() in {"1", "true", "yes"}


def _extract_database_name(bind) -> str | None:
    if bind is None:
        return None

    candidate = bind
    if hasattr(candidate, "sync_engine"):
        candidate = candidate.sync_engine
    if hasattr(candidate, "engine") and getattr(candidate, "url", None) is None:
        candidate = candidate.engine

    url = getattr(candidate, "url", None)
    if url is None:
        return None
    if isinstance(url, str):
        url = make_url(url)
    return url.database


def _is_safe_schema_database(database_name: str | None) -> bool:
    if not database_name:
        return False

    normalized = database_name.lower()
    expected_test_db = (settings.TEST_POSTGRES_DB or "").lower()
    return (
        normalized == expected_test_db
        or normalized.startswith("test_")
        or normalized.endswith("_test")
        or normalized.endswith("_test_db")
        or normalized == ":memory:"
    )


def ensure_safe_schema_operation(bind, operation: str) -> None:
    if _allow_non_test_schema_ops():
        return

    database_name = _extract_database_name(bind)
    if _is_safe_schema_database(database_name):
        return

    raise RuntimeError(
        f"Refusing to run Base.metadata.{operation} against non-test database "
        f"'{database_name or 'unknown'}'. Set ALLOW_NON_TEST_SCHEMA_OPS=true only "
        "for intentional local schema operations."
    )


_original_create_all = Base.metadata.create_all
_original_drop_all = Base.metadata.drop_all


def _guarded_create_all(bind=None, *args, **kwargs):
    ensure_safe_schema_operation(bind, "create_all")
    return _original_create_all(bind=bind, *args, **kwargs)


def _guarded_drop_all(bind=None, *args, **kwargs):
    ensure_safe_schema_operation(bind, "drop_all")
    return _original_drop_all(bind=bind, *args, **kwargs)


Base.metadata.create_all = _guarded_create_all
Base.metadata.drop_all = _guarded_drop_all


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
