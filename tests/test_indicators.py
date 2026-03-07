"""Tests for dynamic indicator generation (T028)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.indicator_agents import (
    research_agent,
    consultant_agent,
    review_agent,
    _rule_based_research,
    _rule_based_consultant,
    _rule_based_review,
)


# ---- Unit Tests ----

def test_research_agent_returns_findings():
    result = research_agent()
    assert "findings" in result
    assert len(result["findings"]) > 0
    for f in result["findings"]:
        assert "title" in f
        assert "category" in f
        assert "summary" in f


def test_research_agent_with_topic():
    result = research_agent("伦理")
    assert "findings" in result
    assert len(result["findings"]) > 0


def test_consultant_agent_generates_proposals():
    findings = _rule_based_research()
    proposals = consultant_agent(findings)
    assert isinstance(proposals, list)
    assert len(proposals) > 0
    for p in proposals:
        assert "title" in p
        assert "dimension" in p
        assert "description" in p


def test_review_agent_reviews_proposals():
    findings = _rule_based_research()
    proposals = _rule_based_consultant(findings)
    reviews = review_agent(proposals)
    assert isinstance(reviews, list)
    assert len(reviews) == len(proposals)
    for r in reviews:
        assert "approved" in r
        assert "confidence_score" in r
        assert 0 <= r["confidence_score"] <= 1


def test_review_agent_validates_dimensions():
    bad_proposals = [{"title": "Test", "dimension": "不存在", "description": "abc"}]
    reviews = _rule_based_review(bad_proposals)
    assert reviews[0]["approved"] is False
    assert any("维度" in issue for issue in reviews[0]["issues"])


def test_full_pipeline():
    """End-to-end three-agent pipeline test."""
    findings = research_agent()
    proposals = consultant_agent(findings)
    reviews = review_agent(proposals)

    assert len(findings["findings"]) > 0
    assert len(proposals) > 0
    assert len(reviews) > 0
    approved = sum(1 for r in reviews if r["approved"])
    assert approved > 0  # At least some proposals should pass


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
        await conn.execute(text("TRUNCATE TABLE indicator_proposals CASCADE"))
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
async def test_generate_proposals_endpoint():
    async with get_client() as client:
        token = await register_user(client, "admin")
        resp = await client.post(
            "/api/v1/indicators/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["proposals_generated"] > 0
    assert data["proposals_approved"] > 0
    assert "research_summary" in data


@pytest.mark.asyncio
async def test_generate_with_topic():
    async with get_client() as client:
        token = await register_user(client, "admin")
        resp = await client.post(
            "/api/v1/indicators/generate?topic=伦理",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["proposals_generated"] > 0


@pytest.mark.asyncio
async def test_list_proposals():
    async with get_client() as client:
        token = await register_user(client, "admin")
        # Generate first
        await client.post("/api/v1/indicators/generate",
                         headers={"Authorization": f"Bearer {token}"})

        resp = await client.get("/api/v1/indicators",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_approve_proposal():
    async with get_client() as client:
        token = await register_user(client, "admin")
        await client.post("/api/v1/indicators/generate",
                         headers={"Authorization": f"Bearer {token}"})

        proposals = (await client.get("/api/v1/indicators",
                                      headers={"Authorization": f"Bearer {token}"})).json()
        pid = proposals[0]["id"]

        resp = await client.post(f"/api/v1/indicators/{pid}/approve",
                                headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_proposal():
    async with get_client() as client:
        token = await register_user(client, "admin")
        await client.post("/api/v1/indicators/generate",
                         headers={"Authorization": f"Bearer {token}"})

        proposals = (await client.get("/api/v1/indicators",
                                      headers={"Authorization": f"Bearer {token}"})).json()
        pid = proposals[0]["id"]

        resp = await client.post(f"/api/v1/indicators/{pid}/reject",
                                headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_list_proposals_filter_status():
    async with get_client() as client:
        token = await register_user(client, "admin")
        await client.post("/api/v1/indicators/generate",
                         headers={"Authorization": f"Bearer {token}"})

        resp = await client.get("/api/v1/indicators?status=reviewed",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["status"] == "reviewed" for p in data)
