"""Tests for intent recognition intelligent assembly (T018)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.intent_agent import _rule_based_parse


# ---- Unit Tests for Intent Parser ----

def test_parse_question_count():
    result = _rule_based_parse("出20道题")
    assert result["total_questions"] == 20


def test_parse_difficulty_beginner():
    result = _rule_based_parse("给新员工出一份入门测试")
    assert result["difficulty"] == 1


def test_parse_difficulty_advanced():
    result = _rule_based_parse("出一份高级测试")
    assert result["difficulty"] == 4


def test_parse_time_limit():
    result = _rule_based_parse("限时30分钟的考试")
    assert result["time_limit_minutes"] == 30


def test_parse_dimensions():
    result = _rule_based_parse("关于AI伦理和AI安全的测试")
    assert "AI伦理" in result["dimensions"]
    assert "AI安全" in result["dimensions"]


def test_parse_question_types():
    result = _rule_based_parse("10道单选题和5道判断题")
    assert result["type_distribution"]["single_choice"] == 10
    assert result["type_distribution"]["true_false"] == 5


def test_parse_full_description():
    result = _rule_based_parse("给新员工出一份20道入门AI基础测试，限时30分钟")
    assert result["total_questions"] == 20
    assert result["difficulty"] == 1
    assert result["time_limit_minutes"] == 30
    assert "AI基础" in (result["dimensions"] or [])
    assert result["title"]  # Should generate a title


def test_parse_score_per_question():
    result = _rule_based_parse("每题10分的考试")
    assert result["score_per_question"] == 10.0


def test_parse_default_type():
    """When no type specified, default to single_choice."""
    result = _rule_based_parse("出10道题")
    assert "single_choice" in result["type_distribution"]
    assert result["type_distribution"]["single_choice"] == 10


def test_parse_minimal_description():
    result = _rule_based_parse("出个测试")
    assert result["total_questions"] == 10  # default
    assert result["difficulty"] == 3  # default
    assert "single_choice" in result["type_distribution"]


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
        await conn.execute(text("TRUNCATE TABLE exam_questions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE exams CASCADE"))
        await conn.execute(text("TRUNCATE TABLE review_records CASCADE"))
        await conn.execute(text("TRUNCATE TABLE questions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))
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


async def create_approved_questions(client, token, count=5, dimension="AI基础"):
    """Create approved questions for assembly."""
    rev_token = await register_user(client, "reviewer")
    qids = []
    for i in range(count):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"智能组卷题目{i+1}？",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错B", "C": "错C", "D": "错D"},
            "difficulty": 2,
            "dimension": dimension,
        }, headers={"Authorization": f"Bearer {token}"})
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit",
                         headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)
    return qids


@pytest.mark.asyncio
async def test_intent_parse_endpoint():
    """Parse endpoint returns structured parameters."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post("/api/v1/exams/intent/parse", json={
            "description": "给新员工出一份20道入门AI基础测试",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_questions"] == 20
    assert data["difficulty"] == 1
    assert "AI基础" in (data["dimensions"] or [])
    assert "single_choice" in data["type_distribution"]


@pytest.mark.asyncio
async def test_intent_assemble_creates_exam():
    """Intent assemble creates exam and assembles questions."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        await create_approved_questions(client, token, count=5, dimension="AI基础")

        resp = await client.post("/api/v1/exams/intent/assemble", json={
            "description": "出3道入门AI基础题",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "parsed_params" in data
    assert "exam" in data
    assert "assembly" in data
    assert data["parsed_params"]["total_questions"] == 3
    assert data["assembly"]["total_questions"] == 3
    assert data["exam"]["status"] == "draft"


@pytest.mark.asyncio
async def test_intent_assemble_with_no_matching_questions():
    """Intent assemble with no matching questions returns 0 assembled."""
    async with get_client() as client:
        token = await register_user(client, "organizer")

        resp = await client.post("/api/v1/exams/intent/assemble", json={
            "description": "出10道高级深度学习题",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["assembly"]["total_questions"] == 0


@pytest.mark.asyncio
async def test_intent_assemble_with_time_limit():
    """Intent parsing correctly extracts time limit."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        await create_approved_questions(client, token, count=5)

        resp = await client.post("/api/v1/exams/intent/assemble", json={
            "description": "出5道题，限时30分钟",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exam"]["time_limit_minutes"] == 30


@pytest.mark.asyncio
async def test_intent_examinee_cannot_use():
    """Examinees cannot use intent assembly."""
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post("/api/v1/exams/intent/parse", json={
            "description": "出10道题",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
