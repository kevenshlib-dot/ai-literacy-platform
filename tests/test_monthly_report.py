"""Tests for monthly report generation (T029)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.monthly_report_service import (
    _calculate_health_score,
    _generate_recommendations,
)


# ---- Unit Tests ----

def test_health_score_empty():
    assert _calculate_health_score(0, 0, 0) == 0.0


def test_health_score_good():
    score = _calculate_health_score(100, 80, 5)
    assert score > 70


def test_health_score_bad():
    score = _calculate_health_score(100, 10, 50)
    assert score < 30


def test_recommendations_no_tests():
    recs = _generate_recommendations(
        {"total_sessions": 0, "completion_rate": 0},
        {"total_scores": 0, "avg_score_ratio": 0},
        {"total_questions": 5, "low_discrimination_count": 0, "health_score": 30},
        {"total_materials": 2},
    )
    assert len(recs) > 0
    categories = [r["category"] for r in recs]
    assert "测试量" in categories
    assert "题库规模" in categories


def test_recommendations_all_good():
    recs = _generate_recommendations(
        {"total_sessions": 100, "completion_rate": 0.95},
        {"total_scores": 90, "avg_score_ratio": 0.75},
        {"total_questions": 200, "low_discrimination_count": 0, "health_score": 90},
        {"total_materials": 50},
    )
    assert len(recs) >= 1
    assert recs[0]["category"] == "总体"


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
        await conn.execute(text("DROP TABLE IF EXISTS reports CASCADE"))
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE reports CASCADE"))
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="admin"):
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
async def test_generate_monthly_report():
    async with get_client() as client:
        token = await register_user(client, "admin")
        resp = await client.post(
            "/api/v1/reports/monthly?year=2026&month=3",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["period"] == "2026-03"
    assert "test_statistics" in data
    assert "scoring_statistics" in data
    assert "question_bank_health" in data
    assert "material_statistics" in data
    assert "user_statistics" in data
    assert "recommendations" in data
    assert "report_id" in data


@pytest.mark.asyncio
async def test_list_reports():
    async with get_client() as client:
        token = await register_user(client, "admin")
        # Generate a report first
        await client.post("/api/v1/reports/monthly?year=2026&month=2",
                         headers={"Authorization": f"Bearer {token}"})

        resp = await client.get("/api/v1/reports",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["report_type"] == "monthly"


@pytest.mark.asyncio
async def test_get_report_detail():
    async with get_client() as client:
        token = await register_user(client, "admin")
        gen_resp = await client.post("/api/v1/reports/monthly?year=2026&month=1",
                                     headers={"Authorization": f"Bearer {token}"})
        report_id = gen_resp.json()["report_id"]

        resp = await client.get(f"/api/v1/reports/{report_id}",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == report_id
    assert data["content"] is not None


@pytest.mark.asyncio
async def test_report_recommendations():
    async with get_client() as client:
        token = await register_user(client, "admin")
        resp = await client.post("/api/v1/reports/monthly?year=2026&month=3",
                                headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert len(data["recommendations"]) > 0
    for rec in data["recommendations"]:
        assert "category" in rec
        assert "priority" in rec
        assert "suggestion" in rec
