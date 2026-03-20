"""Tests for assessment-training closed loop (T034)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.closed_loop_service import (
    _calculate_comparison,
    _calculate_trend,
    _determine_journey_status,
    _generate_loop_recommendations,
)


# ---- Unit Tests ----

def test_calculate_trend_insufficient():
    assert _calculate_trend([]) == "insufficient_data"


def test_calculate_trend_improving():
    assert _calculate_trend([{"score": 50}, {"score": 80}]) == "improving"


def test_calculate_trend_declining():
    assert _calculate_trend([{"score": 80}, {"score": 50}]) == "declining"


def test_calculate_trend_stable():
    assert _calculate_trend([{"score": 70}, {"score": 72}]) == "stable"


def test_determine_journey_not_started():
    assert _determine_journey_status([], []) == "not_started"


def test_recommendations_no_change():
    changes = [{"dimension": "AI基础知识", "pre_score": 80, "post_score": 85, "change": 5, "improved": True}]
    recs = _generate_loop_recommendations(changes)
    assert len(recs) >= 1
    # All good, should get low priority
    assert recs[0]["priority"] == "low"


def test_recommendations_declined():
    changes = [{"dimension": "AI伦理安全", "pre_score": 70, "post_score": 60, "change": -10, "improved": False}]
    recs = _generate_loop_recommendations(changes)
    assert any(r["priority"] == "high" for r in recs)


# ---- Integration Tests ----

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
        await conn.execute(text("DROP TABLE IF EXISTS sandbox_attempts CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS sandbox_sessions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS learning_steps CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS learning_paths CASCADE"))
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
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


@pytest.mark.asyncio
async def test_journey_no_data():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/closed-loop/journey",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["assessment_count"] == 0
    assert data["journey_status"] == "not_started"


@pytest.mark.asyncio
async def test_comparison_no_data():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/closed-loop/comparison",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_comparison"] is False


@pytest.mark.asyncio
async def test_stats_empty():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/closed-loop/stats",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assessments"] == 0
    assert data["total_learning_paths"] == 0
    assert data["total_practices"] == 0


@pytest.mark.asyncio
async def test_stats_with_learning_path():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Generate a learning path
        await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI基础知识"],
        }, headers=headers)

        resp = await client.get("/api/v1/closed-loop/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_learning_paths"] >= 1


@pytest.mark.asyncio
async def test_stats_with_sandbox():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Create sandbox session
        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "闭环测试",
            "task_prompt": "测试任务",
        }, headers=headers)
        sid = session.json()["id"]
        await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "测试输入",
        }, headers=headers)
        await client.post(f"/api/v1/sandbox/sessions/{sid}/complete", headers=headers)

        resp = await client.get("/api/v1/closed-loop/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_practices"] >= 1
    assert data["completed_practices"] >= 1


@pytest.mark.asyncio
async def test_platform_stats_admin():
    async with get_client() as client:
        token = await register_user(client, "admin")
        resp = await client.get("/api/v1/closed-loop/stats/platform",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_assessments" in data
    assert "loop_completion_rate" in data


@pytest.mark.asyncio
async def test_platform_stats_non_admin():
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.get("/api/v1/closed-loop/stats/platform",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_journey_with_training():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Generate learning path
        path_resp = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI伦理安全"],
        }, headers=headers)
        path_id = path_resp.json()["id"]
        steps = path_resp.json()["steps"]

        # Complete all steps
        for step in steps:
            await client.put(f"/api/v1/learning/steps/{step['id']}", json={
                "status": "completed",
            }, headers=headers)

        resp = await client.get("/api/v1/closed-loop/journey", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["training_summary"]["completed_paths"] >= 1
    assert data["training_summary"]["total_steps_completed"] > 0
