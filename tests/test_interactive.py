"""Tests for interactive SJT scenario sessions (T019)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.interactive_agent import _rule_based_response, _rule_based_summary


# ---- Unit Tests ----

def test_rule_based_response_basic():
    result = _rule_based_response(
        scenario="AI在办公中的应用",
        dimension="AI基础",
        difficulty=3,
        conversation_history=[],
        user_message="我认为应该先评估AI工具的适用性。",
    )
    assert "response" in result
    assert "analysis" in result
    assert "difficulty_adjustment" in result
    assert "should_end" in result
    assert isinstance(result["analysis"]["prompt_engineering"], (int, float))


def test_rule_based_response_quality_scoring():
    """Longer, keyword-rich answers should score higher."""
    short = _rule_based_response(
        scenario="test", dimension="AI伦理", difficulty=3,
        conversation_history=[], user_message="不知道",
    )
    detailed = _rule_based_response(
        scenario="test", dimension="AI伦理", difficulty=3,
        conversation_history=[],
        user_message="我认为需要从伦理角度考虑，分析AI决策的公平性和透明度，评估对隐私的风险，并制定相应的安全方案。",
    )
    assert detailed["analysis"]["critical_thinking"] > short["analysis"]["critical_thinking"]


def test_rule_based_response_ends_after_max_turns():
    """Session should end after enough turns."""
    history = [
        {"role": "system", "content": "q1", "ai_analysis": None},
        {"role": "user", "content": "a1", "ai_analysis": None},
        {"role": "system", "content": "q2", "ai_analysis": None},
        {"role": "user", "content": "a2", "ai_analysis": None},
        {"role": "system", "content": "q3", "ai_analysis": None},
        {"role": "user", "content": "a3", "ai_analysis": None},
    ]
    result = _rule_based_response(
        scenario="test", dimension="AI基础", difficulty=3,
        conversation_history=history, user_message="最后的回答",
    )
    assert result["should_end"] is True


def test_rule_based_summary():
    turns = [
        {"role": "system", "content": "请描述场景", "ai_analysis": {
            "prompt_engineering": 7, "critical_thinking": 6, "ethical_decision": 8
        }},
        {"role": "user", "content": "我的回答", "ai_analysis": None},
        {"role": "system", "content": "追问", "ai_analysis": {
            "prompt_engineering": 8, "critical_thinking": 7, "ethical_decision": 9
        }},
    ]
    summary = _rule_based_summary(turns)
    assert "overall_score" in summary
    assert "dimension_scores" in summary
    assert "strengths" in summary
    assert "weaknesses" in summary
    assert summary["overall_score"] > 0


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


@pytest.mark.asyncio
async def test_start_interactive_session():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.post("/api/v1/interactive", json={
            "scenario": "你是一家公司的AI项目负责人，需要决定是否在客服系统中部署AI聊天机器人。",
            "dimension": "AI伦理",
            "difficulty": 2,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"].startswith("你是一家公司")
    assert data["status"] == "active"
    assert len(data["turns"]) == 1  # Opening message
    assert data["turns"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_submit_response():
    async with get_client() as client:
        token = await register_user(client)
        start = await client.post("/api/v1/interactive", json={
            "scenario": "你需要为团队选择一个AI文档工具。",
            "difficulty": 3,
        }, headers={"Authorization": f"Bearer {token}"})
        sid = start.json()["id"]

        resp = await client.post(f"/api/v1/interactive/{sid}/respond", json={
            "message": "我会先考虑数据安全和隐私保护，因为团队文档可能包含敏感信息。然后评估工具的准确性和可靠性。",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ai_response" in data
    assert "analysis" in data
    assert "difficulty" in data
    assert isinstance(data["turn_number"], int)


@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """Complete a multi-turn conversation until auto-completion."""
    async with get_client() as client:
        token = await register_user(client)
        start = await client.post("/api/v1/interactive", json={
            "scenario": "AI工具在教育领域的应用决策。",
            "difficulty": 2,
            "max_turns": 6,
        }, headers={"Authorization": f"Bearer {token}"})
        sid = start.json()["id"]

        completed = False
        for i in range(5):
            resp = await client.post(f"/api/v1/interactive/{sid}/respond", json={
                "message": f"第{i+1}轮回答：我认为需要考虑AI在教育中的伦理风险和公平性问题。",
            }, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            if data["is_completed"]:
                completed = True
                assert data["summary"] is not None
                assert "overall_score" in data["summary"]
                break

    assert completed, "Session should auto-complete within max turns"


@pytest.mark.asyncio
async def test_manual_end_session():
    async with get_client() as client:
        token = await register_user(client)
        start = await client.post("/api/v1/interactive", json={
            "scenario": "企业AI治理决策场景。",
            "max_turns": 10,
        }, headers={"Authorization": f"Bearer {token}"})
        sid = start.json()["id"]

        # Submit one response
        await client.post(f"/api/v1/interactive/{sid}/respond", json={
            "message": "我认为需要建立AI治理框架。",
        }, headers={"Authorization": f"Bearer {token}"})

        # End manually
        resp = await client.post(f"/api/v1/interactive/{sid}/end",
                                headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["final_summary"] is not None


@pytest.mark.asyncio
async def test_cannot_respond_after_ended():
    async with get_client() as client:
        token = await register_user(client)
        start = await client.post("/api/v1/interactive", json={
            "scenario": "测试场景。",
            "max_turns": 10,
        }, headers={"Authorization": f"Bearer {token}"})
        sid = start.json()["id"]

        # End session
        await client.post(f"/api/v1/interactive/{sid}/end",
                         headers={"Authorization": f"Bearer {token}"})

        # Try to respond
        resp = await client.post(f"/api/v1/interactive/{sid}/respond", json={
            "message": "不应该成功",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "已结束" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_sessions():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/interactive", json={
            "scenario": "AI在客服场景中的应用", "difficulty": 1,
        }, headers=headers)
        await client.post("/api/v1/interactive", json={
            "scenario": "AI在教育场景中的决策", "difficulty": 3,
        }, headers=headers)

        resp = await client.get("/api/v1/interactive", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_session_detail():
    async with get_client() as client:
        token = await register_user(client)
        start = await client.post("/api/v1/interactive", json={
            "scenario": "详情测试场景。",
        }, headers={"Authorization": f"Bearer {token}"})
        sid = start.json()["id"]

        resp = await client.get(f"/api/v1/interactive/{sid}",
                               headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sid
    assert len(data["turns"]) >= 1


@pytest.mark.asyncio
async def test_other_user_cannot_access():
    async with get_client() as client:
        token1 = await register_user(client)
        token2 = await register_user(client)

        start = await client.post("/api/v1/interactive", json={
            "scenario": "私有场景。",
        }, headers={"Authorization": f"Bearer {token1}"})
        sid = start.json()["id"]

        resp = await client.get(f"/api/v1/interactive/{sid}",
                               headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 403
