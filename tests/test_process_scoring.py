"""Tests for process-based scoring of SJT sessions (T021)."""
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
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE interactive_turns CASCADE"))
        await conn.execute(text("TRUNCATE TABLE interactive_sessions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="examinee"):
    import uuid
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/register", json={
        "username": f"user_{unique}",
        "email": f"{unique}@test.com",
        "password": "password123",
        "role": role,
    })
    return resp.json()["access_token"]


async def create_completed_session(client, token):
    """Create and complete an interactive session. Returns session_id."""
    headers = {"Authorization": f"Bearer {token}"}

    start = await client.post("/api/v1/interactive", json={
        "scenario": "你是一家公司的AI项目经理，需要决定是否使用AI自动化客户数据分析。",
        "dimension": "AI伦理",
        "difficulty": 3,
        "max_turns": 6,
    }, headers=headers)
    sid = start.json()["id"]

    # Submit responses until completion
    for i in range(5):
        resp = await client.post(f"/api/v1/interactive/{sid}/respond", json={
            "message": f"第{i+1}轮：我认为需要考虑数据隐私和伦理风险，确保AI系统的透明度和公平性。"
                       f"同时分析可能的偏见问题，并建立相应的监控机制。",
        }, headers=headers)
        if resp.json()["is_completed"]:
            break

    # Ensure completed
    session = await client.get(f"/api/v1/interactive/{sid}", headers=headers)
    if session.json()["status"] != "completed":
        await client.post(f"/api/v1/interactive/{sid}/end", headers=headers)

    return sid


@pytest.mark.asyncio
async def test_process_score_completed_session():
    """Process scoring works for completed sessions."""
    async with get_client() as client:
        token = await register_user(client)
        sid = await create_completed_session(client, token)

        resp = await client.get(
            f"/api/v1/interactive/{sid}/process-score",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert "overall_score" in data
    assert "dimension_scores" in data
    assert "prompt_engineering" in data["dimension_scores"]
    assert "critical_thinking" in data["dimension_scores"]
    assert "ethical_decision" in data["dimension_scores"]


@pytest.mark.asyncio
async def test_process_score_has_turn_analyses():
    async with get_client() as client:
        token = await register_user(client)
        sid = await create_completed_session(client, token)

        resp = await client.get(
            f"/api/v1/interactive/{sid}/process-score",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = resp.json()
    assert "turn_analyses" in data
    assert len(data["turn_analyses"]) > 0
    for ta in data["turn_analyses"]:
        assert "turn_number" in ta
        assert "scores" in ta
        assert "prompt_engineering" in ta["scores"]


@pytest.mark.asyncio
async def test_process_score_has_key_decisions():
    async with get_client() as client:
        token = await register_user(client)
        sid = await create_completed_session(client, token)

        resp = await client.get(
            f"/api/v1/interactive/{sid}/process-score",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = resp.json()
    assert "key_decisions" in data
    assert "trend" in data
    assert data["trend"] in ["improving", "stable", "declining"]


@pytest.mark.asyncio
async def test_process_score_has_recommendations():
    async with get_client() as client:
        token = await register_user(client)
        sid = await create_completed_session(client, token)

        resp = await client.get(
            f"/api/v1/interactive/{sid}/process-score",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = resp.json()
    assert "strengths" in data
    assert "weaknesses" in data
    assert "recommendations" in data


@pytest.mark.asyncio
async def test_process_score_active_session_fails():
    """Cannot score an active (incomplete) session."""
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        start = await client.post("/api/v1/interactive", json={
            "scenario": "未完成的场景对话测试。",
            "max_turns": 10,
        }, headers=headers)
        sid = start.json()["id"]

        resp = await client.get(
            f"/api/v1/interactive/{sid}/process-score",
            headers=headers,
        )
    assert resp.status_code == 400
    assert "尚未完成" in resp.json()["detail"]
