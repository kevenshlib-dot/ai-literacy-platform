"""Tests for practice sandbox (T033)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.sandbox_service import (
    _evaluate_attempt,
    _calculate_improvement,
    _generate_feedback_summary,
    PRACTICE_TASKS,
)


# ---- Unit Tests ----

def test_evaluate_short_input():
    result = _evaluate_attempt("prompt_engineering", "测试", "短", 1)
    assert result["score"] < 50


def test_evaluate_good_input():
    result = _evaluate_attempt(
        "prompt_engineering", "摘要任务",
        "请作为专业编辑，对以下文本进行摘要。要求：1)保留关键信息 2)限制在100字以内 3)避免主观评价。例如给定一篇科技新闻...",
        1,
    )
    assert result["score"] > 60


def test_evaluate_returns_feedback():
    result = _evaluate_attempt("prompt_engineering", "任务", "你是一个AI助手，请帮我分析数据", 1)
    assert "feedback" in result
    assert "ai_response" in result


def test_practice_tasks_structure():
    assert len(PRACTICE_TASKS) > 0
    for stype, tasks in PRACTICE_TASKS.items():
        for task in tasks:
            assert "title" in task
            assert "task_prompt" in task


def test_calculate_improvement_empty():
    assert _calculate_improvement([]) == 0.0


def test_generate_feedback_summary_empty():
    assert "未完成" in _generate_feedback_summary([])


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
async def test_list_practice_tasks():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/sandbox/tasks",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0


@pytest.mark.asyncio
async def test_list_tasks_filter_type():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.get("/api/v1/sandbox/tasks?sandbox_type=prompt_engineering",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(t["sandbox_type"] == "prompt_engineering" for t in data)


@pytest.mark.asyncio
async def test_create_sandbox_session():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "提示词练习",
            "task_prompt": "设计一个文本摘要的提示词",
            "dimension": "AI技术应用",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sandbox_type"] == "prompt_engineering"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_submit_attempt():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "练习1",
            "task_prompt": "设计摘要提示词",
        }, headers=headers)
        sid = session.json()["id"]

        resp = await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "请作为专业编辑，对给定文本进行摘要，要求保留关键信息，限制在100字以内",
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["attempt_number"] == 1
    assert data["score"] is not None
    assert data["feedback"] is not None
    assert data["ai_output"] is not None


@pytest.mark.asyncio
async def test_multiple_attempts():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "多次尝试",
            "task_prompt": "优化提示词",
        }, headers=headers)
        sid = session.json()["id"]

        # First attempt
        r1 = await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "短提示",
        }, headers=headers)
        # Second attempt
        r2 = await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "请作为专业分析师，基于以下文本进行深入分析，要求步骤清晰，格式规范",
        }, headers=headers)

    assert r1.json()["attempt_number"] == 1
    assert r2.json()["attempt_number"] == 2


@pytest.mark.asyncio
async def test_complete_session():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "ai_tool_simulation",
            "title": "AI工具练习",
            "task_prompt": "使用AI分类工具",
        }, headers=headers)
        sid = session.json()["id"]

        await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "分析这组图片的分类结果",
        }, headers=headers)

        resp = await client.post(f"/api/v1/sandbox/sessions/{sid}/complete", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["evaluation"] is not None
    assert "total_attempts" in data["evaluation"]


@pytest.mark.asyncio
async def test_get_session_detail():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "code_generation",
            "title": "代码生成",
            "task_prompt": "生成代码",
        }, headers=headers)
        sid = session.json()["id"]

        resp = await client.get(f"/api/v1/sandbox/sessions/{sid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


@pytest.mark.asyncio
async def test_list_sessions():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "练习A",
            "task_prompt": "任务A",
        }, headers=headers)

        resp = await client.get("/api/v1/sandbox/sessions", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_practice_stats():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Create and complete a session
        session = await client.post("/api/v1/sandbox/sessions", json={
            "sandbox_type": "prompt_engineering",
            "title": "统计测试",
            "task_prompt": "测试任务",
        }, headers=headers)
        sid = session.json()["id"]
        await client.post(f"/api/v1/sandbox/sessions/{sid}/attempt", json={
            "user_input": "测试内容",
        }, headers=headers)
        await client.post(f"/api/v1/sandbox/sessions/{sid}/complete", headers=headers)

        resp = await client.get("/api/v1/sandbox/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] >= 1
    assert data["completed_sessions"] >= 1
    assert "by_type" in data
