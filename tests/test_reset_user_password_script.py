import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.core.security import verify_password
from app.services.user_service import create_user, get_user_by_username, init_roles
from scripts.reset_user_password import PasswordResetError, reset_password_by_username


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_reset_password_for_existing_user_updates_hash(db_session: AsyncSession):
    user = await create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        password="oldpass123",
        role_name="admin",
    )
    await db_session.commit()

    await reset_password_by_username(db_session, "admin", "newpass456")
    await db_session.commit()

    await db_session.refresh(user)
    assert verify_password("newpass456", user.hashed_password)
    assert not verify_password("oldpass123", user.hashed_password)


@pytest.mark.asyncio
async def test_reset_password_for_missing_user_raises_error(db_session: AsyncSession):
    with pytest.raises(PasswordResetError, match="用户不存在"):
        await reset_password_by_username(db_session, "missing-admin", "newpass456")


@pytest.mark.asyncio
async def test_reset_password_rejects_short_password(db_session: AsyncSession):
    await create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        password="oldpass123",
        role_name="admin",
    )
    await db_session.commit()

    with pytest.raises(PasswordResetError, match="密码长度不能少于6个字符"):
        await reset_password_by_username(db_session, "admin", "123")

    user = await get_user_by_username(db_session, "admin")
    assert user is not None
    assert verify_password("oldpass123", user.hashed_password)
