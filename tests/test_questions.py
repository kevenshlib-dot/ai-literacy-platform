"""Tests for question generation engine (T009)."""
import io
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.question_agent import generate_questions_via_llm, _template_fallback


# ---- Unit Tests for Question Agent ----

def test_template_fallback_single_choice():
    """Template fallback generates single choice questions."""
    questions = _template_fallback(
        content="人工智能是计算机科学的一个分支，它企图了解智能的实质。",
        question_types=["single_choice"],
        count=2,
        difficulty=3,
    )
    assert len(questions) == 2
    for q in questions:
        assert q["question_type"] == "single_choice"
        assert "stem" in q
        assert "options" in q
        assert "correct_answer" in q
        assert q["correct_answer"] == "A"
        assert "A" in q["options"]
        assert "D" in q["options"]


def test_template_fallback_true_false():
    questions = _template_fallback(
        content="机器学习是AI的核心技术之一。",
        question_types=["true_false"],
        count=1,
        difficulty=2,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "true_false"
    assert questions[0]["correct_answer"] in ("A", "B")


def test_template_fallback_fill_blank():
    questions = _template_fallback(
        content="深度学习使用多层神经网络。",
        question_types=["fill_blank"],
        count=1,
        difficulty=4,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "fill_blank"
    assert questions[0]["options"] is None


def test_template_fallback_short_answer():
    questions = _template_fallback(
        content="自然语言处理是AI的重要应用方向。",
        question_types=["short_answer"],
        count=1,
        difficulty=5,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "short_answer"


def test_template_fallback_mixed_types():
    """Mixed types cycle through the list."""
    questions = _template_fallback(
        content="AI伦理包括公平性、透明性和可解释性。",
        question_types=["single_choice", "true_false", "fill_blank"],
        count=6,
        difficulty=3,
    )
    assert len(questions) == 6
    assert questions[0]["question_type"] == "single_choice"
    assert questions[1]["question_type"] == "true_false"
    assert questions[2]["question_type"] == "fill_blank"
    assert questions[3]["question_type"] == "single_choice"


def test_generate_questions_via_llm_uses_fallback():
    """When LLM API key is not configured, fallback is used."""
    questions = generate_questions_via_llm(
        content="测试内容，用于验证降级机制。",
        question_types=["single_choice"],
        count=2,
        difficulty=3,
    )
    assert len(questions) == 2
    assert questions[0]["question_type"] == "single_choice"


# ---- Integration Tests: Question API ----

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
        await conn.execute(text("TRUNCATE TABLE questions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE knowledge_units CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
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


async def upload_and_parse_material(client, token):
    """Upload a markdown file, parse it, and return material_id and knowledge_unit_id."""
    md_content = "# AI基础认知\n\n" + "人工智能是计算机科学的一个分支。" * 50
    upload = await client.post(
        "/api/v1/materials",
        files={"file": ("ai_basics.md", md_content.encode(), "text/markdown")},
        data={"title": "AI基础教材"},
        headers={"Authorization": f"Bearer {token}"},
    )
    mid = upload.json()["id"]

    # Parse material
    await client.post(
        f"/api/v1/materials/{mid}/parse",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get knowledge units
    ku_resp = await client.get(
        f"/api/v1/materials/{mid}/knowledge-units",
        headers={"Authorization": f"Bearer {token}"},
    )
    ku_data = ku_resp.json()
    ku_id = ku_data["units"][0]["id"]
    return mid, ku_id


# ---- CRUD Tests ----

@pytest.mark.asyncio
async def test_create_question():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/questions",
            json={
                "question_type": "single_choice",
                "stem": "人工智能的英文缩写是？",
                "options": {"A": "AI", "B": "BI", "C": "CI", "D": "DI"},
                "correct_answer": "A",
                "explanation": "AI = Artificial Intelligence",
                "difficulty": 1,
                "dimension": "AI基础认知",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stem"] == "人工智能的英文缩写是？"
    assert data["status"] == "draft"
    assert data["difficulty"] == 1


@pytest.mark.asyncio
async def test_list_questions_empty():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/questions",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_questions_with_filter():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two questions with different types
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "单选题1",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "difficulty": 2,
        }, headers=headers)

        await client.post("/api/v1/questions", json={
            "question_type": "true_false",
            "stem": "判断题1",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错误"},
            "difficulty": 3,
        }, headers=headers)

        # Filter by type
        resp = await client.get(
            "/api/v1/questions?question_type=single_choice",
            headers=headers,
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["question_type"] == "single_choice"

        # Filter by keyword
        resp = await client.get(
            "/api/v1/questions?keyword=判断",
            headers=headers,
        )
        assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_question_by_id():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "测试题目",
            "correct_answer": "B",
            "options": {"A": "错", "B": "对"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/questions/{qid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["stem"] == "测试题目"


@pytest.mark.asyncio
async def test_get_question_not_found():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/questions/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_question():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "原始题干",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "difficulty": 2,
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.put(f"/api/v1/questions/{qid}", json={
            "stem": "更新后的题干",
            "difficulty": 4,
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["stem"] == "更新后的题干"
    assert resp.json()["difficulty"] == 4


@pytest.mark.asyncio
async def test_delete_question():
    async with get_client() as client:
        token = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待删除",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/questions/{qid}", headers=headers)
        assert resp.status_code == 204

        # Verify deleted
        resp2 = await client.get(f"/api/v1/questions/{qid}", headers=headers)
        assert resp2.status_code == 404


# ---- Review Workflow Tests ----

@pytest.mark.asyncio
async def test_submit_and_review_workflow():
    """Test full review workflow: create -> submit -> approve."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        # Create question
        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待审核题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {org_token}"})
        qid = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"

        # Submit for review
        submit_resp = await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "pending_review"

        # Approve
        review_resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve", "comment": "质量良好"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "approved"
        assert review_resp.json()["review_comment"] == "质量良好"


@pytest.mark.asyncio
async def test_reject_question():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "低质量题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {org_token}"})
        qid = create_resp.json()["id"]

        # Submit
        await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers={"Authorization": f"Bearer {org_token}"},
        )

        # Reject
        resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "reject", "comment": "题干不够清晰"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_examinee_cannot_create_question():
    """Examinees should not be able to create questions."""
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "不应该成功",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ---- Generation Tests ----

@pytest.mark.asyncio
async def test_generate_from_knowledge_unit():
    """Generate questions from a parsed knowledge unit."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, ku_id = await upload_and_parse_material(client, token)

        resp = await client.post("/api/v1/questions/generate", json={
            "knowledge_unit_id": ku_id,
            "question_types": ["single_choice", "true_false"],
            "count": 3,
            "difficulty": 2,
        }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 3
    assert len(data["questions"]) == 3
    # Verify questions have source references
    for q in data["questions"]:
        assert q["source_material_id"] == mid
        assert q["source_knowledge_unit_id"] == ku_id


@pytest.mark.asyncio
async def test_batch_generate_from_material():
    """Batch generate questions from all knowledge units of a material."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, _ = await upload_and_parse_material(client, token)

        resp = await client.post(
            f"/api/v1/questions/generate/material/{mid}",
            json={
                "question_types": ["single_choice"],
                "count_per_unit": 1,
                "difficulty": 3,
                "max_units": 3,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] >= 1


@pytest.mark.asyncio
async def test_generate_invalid_knowledge_unit():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post("/api/v1/questions/generate", json={
            "knowledge_unit_id": "00000000-0000-0000-0000-000000000000",
            "question_types": ["single_choice"],
            "count": 1,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


# ---- Stats Test ----

@pytest.mark.asyncio
async def test_question_stats():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        # Create a question
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "统计测试题",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "dimension": "AI基础",
        }, headers=headers)

        resp = await client.get("/api/v1/questions/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "by_status" in data
    assert "by_type" in data
