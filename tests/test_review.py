"""Tests for question review workflow (T010)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.review_agent import ai_review_question, _rule_based_review


# ---- Unit Tests for Review Agent ----

def test_rule_based_review_good_question():
    """Well-formed question gets high scores."""
    result = _rule_based_review(
        stem="人工智能的英文缩写是什么？",
        options={"A": "AI", "B": "BI", "C": "CI", "D": "DI"},
        correct_answer="A",
        explanation="AI = Artificial Intelligence",
        question_type="single_choice",
        difficulty=2,
        dimension="AI基础认知",
    )
    assert result["overall_score"] >= 3.5
    assert result["recommendation"] == "approve"
    assert "scores" in result


def test_rule_based_review_poor_question():
    """Short stem with missing options gets low scores."""
    result = _rule_based_review(
        stem="AI",
        options=None,
        correct_answer="X",
        explanation=None,
        question_type="single_choice",
        difficulty=3,
        dimension=None,
    )
    assert result["overall_score"] < 3.5
    assert result["recommendation"] in ("revise", "reject")


def test_rule_based_review_true_false():
    result = _rule_based_review(
        stem="人工智能是计算机科学的一个分支。",
        options={"A": "正确", "B": "错误"},
        correct_answer="A",
        explanation="正确描述",
        question_type="true_false",
        difficulty=1,
        dimension="AI基础",
    )
    assert result["recommendation"] == "approve"


def test_ai_review_uses_fallback():
    """When LLM not configured, uses rule-based review."""
    result = ai_review_question(
        stem="深度学习使用多层神经网络进行特征提取？",
        options={"A": "正确", "B": "错误"},
        correct_answer="A",
        explanation="深度学习的核心特征",
        question_type="true_false",
        difficulty=3,
        dimension="AI技术",
    )
    assert "scores" in result
    assert "recommendation" in result
    assert "overall_score" in result


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


async def create_question(client, token, stem="测试题目"):
    resp = await client.post("/api/v1/questions", json={
        "question_type": "single_choice",
        "stem": stem,
        "correct_answer": "A",
        "options": {"A": "正确选项", "B": "错误选项B", "C": "错误选项C", "D": "错误选项D"},
        "difficulty": 3,
        "dimension": "AI基础认知",
        "explanation": "A是正确答案，因为...",
    }, headers={"Authorization": f"Bearer {token}"})
    return resp.json()["id"]


# ---- AI Check Tests ----

@pytest.mark.asyncio
async def test_ai_check_question():
    """AI quality check returns scores and recommendation."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        qid = await create_question(client, org_token, "人工智能的英文缩写是什么？")

        resp = await client.post(
            f"/api/v1/questions/{qid}/ai-check",
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert "overall_score" in data
    assert "recommendation" in data
    assert data["recommendation"] in ("approve", "revise", "reject")


@pytest.mark.asyncio
async def test_ai_check_not_found():
    async with get_client() as client:
        rev_token = await register_user(client, "reviewer")
        resp = await client.post(
            "/api/v1/questions/00000000-0000-0000-0000-000000000000/ai-check",
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 404


# ---- Review History Tests ----

@pytest.mark.asyncio
async def test_review_history():
    """Review actions create audit records."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        qid = await create_question(client, org_token)

        # Submit for review
        await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers={"Authorization": f"Bearer {org_token}"},
        )

        # AI check
        await client.post(
            f"/api/v1/questions/{qid}/ai-check",
            headers={"Authorization": f"Bearer {rev_token}"},
        )

        # Approve
        await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve", "comment": "通过"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )

        # Get history
        resp = await client.get(
            f"/api/v1/questions/{qid}/review-history",
            headers={"Authorization": f"Bearer {org_token}"},
        )
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 2  # ai_check + approve
    actions = [r["action"] for r in history]
    assert "ai_check" in actions
    assert "approve" in actions


# ---- Pending Reviews Queue ----

@pytest.mark.asyncio
async def test_pending_reviews_queue():
    """Reviewer can see pending questions."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        # Create and submit 3 questions
        qids = []
        for i in range(3):
            qid = await create_question(client, org_token, f"待审核题目{i+1}？")
            qids.append(qid)
            await client.post(
                f"/api/v1/questions/{qid}/submit",
                headers={"Authorization": f"Bearer {org_token}"},
            )

        # Check pending queue
        resp = await client.get(
            "/api/v1/questions/review/pending",
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    for item in data["items"]:
        assert item["status"] == "pending_review"


# ---- Batch Operations ----

@pytest.mark.asyncio
async def test_batch_submit():
    """Batch submit multiple questions for review."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {org_token}"}

        qids = []
        for i in range(3):
            qid = await create_question(client, org_token, f"批量提交{i+1}？")
            qids.append(qid)

        resp = await client.post(
            "/api/v1/questions/batch/submit",
            json={"question_ids": qids},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    for item in data["items"]:
        assert item["status"] == "pending_review"


@pytest.mark.asyncio
async def test_batch_approve():
    """Batch approve multiple questions."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        # Create and submit
        qids = []
        for i in range(3):
            qid = await create_question(client, org_token, f"批量审核{i+1}？")
            qids.append(qid)

        await client.post(
            "/api/v1/questions/batch/submit",
            json={"question_ids": qids},
            headers={"Authorization": f"Bearer {org_token}"},
        )

        # Batch approve
        resp = await client.post(
            "/api/v1/questions/batch/review",
            json={
                "question_ids": qids,
                "action": "approve",
                "comment": "批量通过",
            },
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    for item in data["items"]:
        assert item["status"] == "approved"


@pytest.mark.asyncio
async def test_batch_reject():
    """Batch reject multiple questions."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        qids = []
        for i in range(2):
            qid = await create_question(client, org_token, f"批量拒绝{i+1}？")
            qids.append(qid)

        await client.post(
            "/api/v1/questions/batch/submit",
            json={"question_ids": qids},
            headers={"Authorization": f"Bearer {org_token}"},
        )

        resp = await client.post(
            "/api/v1/questions/batch/review",
            json={
                "question_ids": qids,
                "action": "reject",
                "comment": "质量不合格",
            },
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["status"] == "rejected"
        assert item["review_comment"] == "质量不合格"


# ---- RBAC Tests ----

@pytest.mark.asyncio
async def test_examinee_cannot_access_pending_reviews():
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.get(
            "/api/v1/questions/review/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_examinee_cannot_ai_check():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        qid = await create_question(client, org_token)

        resp = await client.post(
            f"/api/v1/questions/{qid}/ai-check",
            headers={"Authorization": f"Bearer {ex_token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_organizer_cannot_batch_review():
    """Organizers can submit but not review."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")

        qid = await create_question(client, org_token)

        resp = await client.post(
            "/api/v1/questions/batch/review",
            json={
                "question_ids": [qid],
                "action": "approve",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
    assert resp.status_code == 403
