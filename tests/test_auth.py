import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.auth_session import AuthSession
from app.services.auth_service import get_access_token_issue_time, utc_now
from app.services.user_service import create_user, init_roles


def make_engine():
    return create_async_engine(settings.DATABASE_URL, echo=False)


async def override_get_db():
    engine = make_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()

    yield
    await engine.dispose()


def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def create_direct_token(
    *,
    role: str = "examinee",
    is_active: bool = True,
    password: str = "password123",
) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    engine = make_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        user = await create_user(
            session,
            username=f"{role}_{suffix}",
            email=f"{role}_{suffix}@example.com",
            password=password,
            role_name=role,
            is_active=is_active,
        )
        await session.commit()
        await session.refresh(user, ["role"])
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.name.value},
            issued_at=get_access_token_issue_time(user),
        )
        user_id = str(user.id)
    await engine.dispose()
    return user_id, token


async def expire_refresh_sessions(user_id: str) -> None:
    engine = make_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == uuid.UUID(user_id))
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_examinee_auto_login_sets_refresh_cookie():
    async with get_client() as client:
        resp = await client.post("/api/v1/auth/register", json={
            "username": "testuser1",
            "email": "test1@example.com",
            "password": "password123",
            "full_name": "Test User",
            "role": "examinee",
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["username"] == "testuser1"
    assert data["user"]["role"] == "examinee"
    assert resp.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    assert "httponly" in resp.headers["set-cookie"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_username():
    async with get_client() as client:
        await client.post("/api/v1/auth/register", json={
            "username": "dupuser",
            "email": "dup1@example.com",
            "password": "password123",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "username": "dupuser",
            "email": "dup2@example.com",
            "password": "password123",
        })

    assert resp.status_code == 400
    assert "用户名已存在" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_admin_is_forbidden():
    async with get_client() as client:
        resp = await client.post("/api/v1/auth/register", json={
            "username": "adminuser",
            "email": "admin@example.com",
            "password": "password123",
            "role": "admin",
        })

    assert resp.status_code == 400
    assert resp.json()["detail"] == "不允许注册管理员角色"


@pytest.mark.asyncio
async def test_register_approval_roles_do_not_receive_token():
    async with get_client() as client:
        resp = await client.post("/api/v1/auth/register", json={
            "username": "pendingorg",
            "email": "pendingorg@example.com",
            "password": "password123",
            "role": "organizer",
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["needs_approval"] is True
    assert data["access_token"] is None


@pytest.mark.asyncio
async def test_pending_user_login_is_forbidden():
    async with get_client() as client:
        await client.post("/api/v1/auth/register", json={
            "username": "pendingreviewer",
            "email": "pendingreviewer@example.com",
            "password": "password123",
            "role": "reviewer",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "pendingreviewer",
            "password": "password123",
        })

    assert resp.status_code == 403
    assert "待审批" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_success_sets_refresh_cookie():
    async with get_client() as client:
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "password123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "loginuser",
            "password": "password123",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["username"] == "loginuser"
    assert resp.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)


@pytest.mark.asyncio
async def test_login_wrong_password():
    async with get_client() as client:
        await client.post("/api/v1/auth/register", json={
            "username": "wrongpwuser",
            "email": "wrongpw@example.com",
            "password": "password123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "wrongpwuser",
            "password": "wrongpassword",
        })

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "meuser",
            "email": "me@example.com",
            "password": "password123",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["username"] == "meuser"


@pytest.mark.asyncio
async def test_get_me_without_token():
    async with get_client() as client:
        resp = await client.get("/api/v1/users/me")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_cookie_and_returns_new_access_token():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "refreshuser",
            "email": "refresh@example.com",
            "password": "password123",
        })
        old_refresh_token = reg.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)

        resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    assert client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) != old_refresh_token

    async with get_client() as rogue_client:
        rogue_resp = await rogue_client.post(
            "/api/v1/auth/refresh",
            cookies={settings.AUTH_REFRESH_COOKIE_NAME: old_refresh_token},
        )

    assert rogue_resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_requires_cookie():
    async with get_client() as client:
        resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_fails_when_session_expired():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "expiredrefresh",
            "email": "expiredrefresh@example.com",
            "password": "password123",
        })
        user_id = str(reg.json()["user"]["id"])

        await expire_refresh_sessions(user_id)
        resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session():
    async with get_client() as client:
        await client.post("/api/v1/auth/register", json={
            "username": "logoutuser",
            "email": "logout@example.com",
            "password": "password123",
        })

        logout_resp = await client.post("/api/v1/auth/logout")
        refresh_resp = await client.post("/api/v1/auth/refresh")

    assert logout_resp.status_code == 200
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_role_based_dashboards_use_current_user_role():
    _, admin_token = await create_direct_token(role="admin")
    _, organizer_token = await create_direct_token(role="organizer")
    _, reviewer_token = await create_direct_token(role="reviewer")
    _, examinee_token = await create_direct_token(role="examinee")

    async with get_client() as client:
        admin_resp = await client.get(
            "/api/v1/users/admin/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        organizer_resp = await client.get(
            "/api/v1/users/organizer/stats",
            headers={"Authorization": f"Bearer {organizer_token}"},
        )
        reviewer_resp = await client.get(
            "/api/v1/users/reviewer/tasks",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        forbidden_resp = await client.get(
            "/api/v1/users/admin/dashboard",
            headers={"Authorization": f"Bearer {examinee_token}"},
        )

    assert admin_resp.status_code == 200
    assert organizer_resp.status_code == 200
    assert reviewer_resp.status_code == 200
    assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_reset_password_invalidates_existing_access_and_refresh_tokens():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "resetuser",
            "email": "reset@example.com",
            "password": "oldpass123",
        })
        token = reg.json()["access_token"]

        reset_resp = await client.post(
            "/api/v1/users/me/reset-password",
            json={"old_password": "oldpass123", "new_password": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        old_token_resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        refresh_resp = await client.post("/api/v1/auth/refresh")
        old_login_resp = await client.post("/api/v1/auth/login", json={
            "username": "resetuser",
            "password": "oldpass123",
        })
        new_login_resp = await client.post("/api/v1/auth/login", json={
            "username": "resetuser",
            "password": "newpass456",
        })

    assert reset_resp.status_code == 200
    assert old_token_resp.status_code == 401
    assert refresh_resp.status_code == 401
    assert old_login_resp.status_code == 401
    assert new_login_resp.status_code == 200
