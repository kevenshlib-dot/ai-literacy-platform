"""Tests for adaptive learning engine (T032)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.adaptive_learning_service import (
    _generate_path_title,
    _generate_path_description,
    DIMENSIONS,
)


# ---- Unit Tests ----

def test_generate_path_title_single():
    assert "AI基础知识" in _generate_path_title(["AI基础知识"])


def test_generate_path_title_multiple():
    title = _generate_path_title(["AI基础知识", "AI伦理安全"])
    assert "综合提升" in title


def test_generate_path_title_many():
    title = _generate_path_title(DIMENSIONS)
    assert "全面提升" in title


def test_generate_path_description():
    analysis = {"dimension_scores": {"AI基础知识": 40.0, "AI伦理安全": 30.0}}
    desc = _generate_path_description(analysis, ["AI基础知识", "AI伦理安全"])
    assert "AI基础知识" in desc
    assert "40%" in desc


def test_dimensions_count():
    assert len(DIMENSIONS) == 5


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
        await conn.execute(text("DROP TABLE IF EXISTS learning_steps CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS learning_paths CASCADE"))
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE courses CASCADE"))
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


async def create_published_course(client, token, title, dimension):
    """Helper to create and publish a course."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/v1/courses", json={
        "title": title,
        "dimension": dimension,
        "difficulty": 2,
    }, headers=headers)
    cid = resp.json()["id"]
    await client.post(f"/api/v1/courses/{cid}/publish", headers=headers)
    return cid


@pytest.mark.asyncio
async def test_weakness_analysis_no_scores():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/learning/analysis",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assessments"] == 0
    assert len(data["weaknesses"]) > 0


@pytest.mark.asyncio
async def test_generate_learning_path():
    async with get_client() as client:
        # Create organizer for course creation
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}
        await create_published_course(client, org_token, "AI基础入门", "AI基础知识")

        # Create examinee
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI基础知识"],
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["title"] is not None
    assert len(data["steps"]) > 0


@pytest.mark.asyncio
async def test_list_learning_paths():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Generate a path
        await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI伦理安全"],
        }, headers=headers)

        resp = await client.get("/api/v1/learning/paths", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_learning_path_detail():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        gen = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI技术应用"],
        }, headers=headers)
        path_id = gen.json()["id"]

        resp = await client.get(f"/api/v1/learning/paths/{path_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == path_id
    assert "steps" in data


@pytest.mark.asyncio
async def test_get_next_step():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        gen = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI批判思维"],
        }, headers=headers)
        path_id = gen.json()["id"]

        resp = await client.get(f"/api/v1/learning/paths/{path_id}/next", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_num"] == 1


@pytest.mark.asyncio
async def test_update_step_status():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        gen = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI创新实践"],
        }, headers=headers)
        steps = gen.json()["steps"]
        step_id = steps[0]["id"]

        resp = await client.put(f"/api/v1/learning/steps/{step_id}", json={
            "status": "completed",
            "score": 85.0,
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["score"] == 85.0
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_path_progress_calculation():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        gen = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI伦理安全"],
        }, headers=headers)
        path_id = gen.json()["id"]
        steps = gen.json()["steps"]

        # Complete all steps
        for step in steps:
            await client.put(f"/api/v1/learning/steps/{step['id']}", json={
                "status": "completed",
            }, headers=headers)

        # Check path progress
        resp = await client.get(f"/api/v1/learning/paths/{path_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress_percent"] == 100.0
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_recommendations():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/learning/recommendations",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_path_with_published_courses():
    """When published courses exist, they should appear as course steps."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        await create_published_course(client, org_token, "伦理课程A", "AI伦理安全")
        await create_published_course(client, org_token, "伦理课程B", "AI伦理安全")

        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/learning/paths", json={
            "focus_dimensions": ["AI伦理安全"],
        }, headers=headers)
    assert resp.status_code == 200
    steps = resp.json()["steps"]
    course_steps = [s for s in steps if s["step_type"] == "course"]
    assert len(course_steps) >= 2
