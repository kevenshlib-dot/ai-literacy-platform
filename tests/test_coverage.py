"""Tests for coverage analysis (T027)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.coverage_service import (
    _coverage_level,
    _identify_gaps,
    _build_heatmap,
    FIVE_DIMENSIONS,
)


# ---- Unit Tests ----

def test_coverage_level():
    assert _coverage_level(100) == "充足"
    assert _coverage_level(80) == "充足"
    assert _coverage_level(60) == "适中"
    assert _coverage_level(30) == "不足"
    assert _coverage_level(5) == "缺失"


def test_identify_gaps():
    heatmap = {
        "AI基础知识": {"coverage_score": 90, "level": "充足", "material_count": 10, "question_count": 20},
        "AI伦理安全": {"coverage_score": 10, "level": "缺失", "material_count": 1, "question_count": 2},
        "AI技术应用": {"coverage_score": 40, "level": "不足", "material_count": 3, "question_count": 5},
    }
    gaps = _identify_gaps(heatmap)
    assert len(gaps) == 2
    assert gaps[0]["dimension"] == "AI伦理安全"  # Lowest score first
    assert gaps[0]["priority"] == "高"
    assert gaps[1]["dimension"] == "AI技术应用"
    assert gaps[1]["priority"] == "中"


def test_build_heatmap_empty():
    mat = {dim: {"materials": 0, "knowledge_units": 0} for dim in FIVE_DIMENSIONS}
    q = {dim: {"total": 0, "by_difficulty": {}} for dim in FIVE_DIMENSIONS}
    heatmap = _build_heatmap(mat, q)
    assert len(heatmap) == 5
    for dim in FIVE_DIMENSIONS:
        assert heatmap[dim]["coverage_score"] == 0
        assert heatmap[dim]["level"] == "缺失"


def test_build_heatmap_full():
    mat = {dim: {"materials": 10, "knowledge_units": 5} for dim in FIVE_DIMENSIONS}
    q = {dim: {"total": 20, "by_difficulty": {}} for dim in FIVE_DIMENSIONS}
    heatmap = _build_heatmap(mat, q)
    for dim in FIVE_DIMENSIONS:
        assert heatmap[dim]["coverage_score"] == 100
        assert heatmap[dim]["level"] == "充足"


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
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE knowledge_units CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
        await conn.execute(text("TRUNCATE TABLE review_records CASCADE"))
        await conn.execute(text("TRUNCATE TABLE questions CASCADE"))
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="organizer"):
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
async def test_coverage_analysis_empty():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get(
            "/api/v1/materials/coverage",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "dimensions" in data
    assert len(data["dimensions"]) == 5
    assert "heatmap" in data
    assert "gaps" in data
    assert "summary" in data
    assert data["summary"]["total_dimensions"] == 5


@pytest.mark.asyncio
async def test_coverage_with_questions():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Create questions in different dimensions
        for dim in ["AI基础知识", "AI伦理安全"]:
            for i in range(3):
                await client.post("/api/v1/questions", json={
                    "question_type": "single_choice",
                    "stem": f"{dim}题目{i+1}",
                    "correct_answer": "A",
                    "options": {"A": "a", "B": "b"},
                    "dimension": dim,
                }, headers=headers)

        resp = await client.get("/api/v1/materials/coverage", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    heatmap = data["heatmap"]
    assert heatmap["AI基础知识"]["question_count"] >= 3
    assert heatmap["AI伦理安全"]["question_count"] >= 3


@pytest.mark.asyncio
async def test_dimension_detail():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            "/api/v1/materials/coverage/AI基础知识",
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dimension"] == "AI基础知识"
    assert "sub_topic_coverage" in data
    assert "difficulty_distribution" in data


@pytest.mark.asyncio
async def test_dimension_detail_invalid():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get(
            "/api/v1/materials/coverage/不存在的维度",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_gaps_detection():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get(
            "/api/v1/materials/coverage",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = resp.json()
    # All dimensions should have gaps since no data
    assert len(data["gaps"]) == 5
    for gap in data["gaps"]:
        assert "dimension" in gap
        assert "priority" in gap
        assert "suggestion" in gap
