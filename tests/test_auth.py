import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles


async def override_get_db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
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
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Truncate users table to ensure clean state per test
    async with engine.begin() as conn:
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        pass
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---- Registration Tests ----

@pytest.mark.asyncio
async def test_register_success():
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
    assert "access_token" in data
    assert data["user"]["username"] == "testuser1"
    assert data["user"]["role"] == "examinee"


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


# ---- Login Tests ----

@pytest.mark.asyncio
async def test_login_success():
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
    assert "access_token" in data
    assert data["user"]["username"] == "loginuser"


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


# ---- Token / Me Tests ----

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
    assert resp.status_code == 401  # Missing credentials


# ---- RBAC Tests ----

@pytest.mark.asyncio
async def test_admin_endpoint_with_admin_role():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "adminuser",
            "email": "admin@example.com",
            "password": "password123",
            "role": "admin",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_endpoint_with_examinee_role_forbidden():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "examuser",
            "email": "exam@example.com",
            "password": "password123",
            "role": "examinee",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_organizer_endpoint_with_organizer_role():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "orguser",
            "email": "org@example.com",
            "password": "password123",
            "role": "organizer",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/organizer/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_organizer_endpoint_with_examinee_forbidden():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "exam2user",
            "email": "exam2@example.com",
            "password": "password123",
            "role": "examinee",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/organizer/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reviewer_endpoint_with_reviewer_role():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "revuser",
            "email": "rev@example.com",
            "password": "password123",
            "role": "reviewer",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/reviewer/tasks",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reviewer_endpoint_with_organizer_forbidden():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "org2user",
            "email": "org2@example.com",
            "password": "password123",
            "role": "organizer",
        })
        token = reg.json()["access_token"]
        resp = await client.get(
            "/api/v1/users/reviewer/tasks",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


# ---- Password Reset Test ----

@pytest.mark.asyncio
async def test_reset_password():
    async with get_client() as client:
        reg = await client.post("/api/v1/auth/register", json={
            "username": "resetuser",
            "email": "reset@example.com",
            "password": "oldpass123",
        })
        token = reg.json()["access_token"]
        resp = await client.post(
            "/api/v1/users/me/reset-password",
            json={"old_password": "oldpass123", "new_password": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # Verify old password no longer works
        resp2 = await client.post("/api/v1/auth/login", json={
            "username": "resetuser",
            "password": "oldpass123",
        })
        assert resp2.status_code == 401

        # Verify new password works
        resp3 = await client.post("/api/v1/auth/login", json={
            "username": "resetuser",
            "password": "newpass456",
        })
        assert resp3.status_code == 200
