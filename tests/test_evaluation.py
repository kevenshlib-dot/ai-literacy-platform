"""Tests for evaluation levels and motivational feedback (T023)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.evaluation_service import get_level_from_ratio


# ---- Unit Tests ----

def test_level_excellent():
    assert get_level_from_ratio(0.95) == "优秀"
    assert get_level_from_ratio(0.90) == "优秀"


def test_level_good():
    assert get_level_from_ratio(0.85) == "良好"
    assert get_level_from_ratio(0.80) == "良好"


def test_level_pass():
    assert get_level_from_ratio(0.65) == "合格"
    assert get_level_from_ratio(0.60) == "合格"


def test_level_needs_improvement():
    assert get_level_from_ratio(0.50) == "待提升"
    assert get_level_from_ratio(0.0) == "待提升"


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
        await conn.execute(text("TRUNCATE TABLE score_details CASCADE"))
        await conn.execute(text("TRUNCATE TABLE scores CASCADE"))
        await conn.execute(text("TRUNCATE TABLE answers CASCADE"))
        await conn.execute(text("TRUNCATE TABLE answer_sheets CASCADE"))
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


async def create_scored_exam(client, org_token, ex_token, answers):
    """Create exam, take it, grade it. Returns score_id."""
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, (correct, _) in enumerate(answers):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"评价题{i+1}？",
            "correct_answer": correct,
            "options": {"A": "选A", "B": "选B", "C": "选C", "D": "选D"},
            "difficulty": 3,
            "dimension": f"维度{i % 2 + 1}",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)

    exam_resp = await client.post("/api/v1/exams", json={"title": "评价测试"}, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [{"question_id": qids[i], "order_num": i+1, "score": 10}
                      for i in range(len(qids))]
    }, headers=org_headers)
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    for i, (_, answer) in enumerate(answers):
        if answer is not None:
            await client.post(f"/api/v1/sessions/{sid}/answer", json={
                "question_id": qids[i], "answer_content": answer,
            }, headers=ex_headers)

    await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)
    grade = await client.post(f"/api/v1/scores/grade/{sid}", headers=org_headers)
    return grade.json()["score_id"]


@pytest.mark.asyncio
async def test_evaluation_feedback_excellent():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"), ("B", "B"), ("C", "C"),  # All correct = 100%
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/evaluation",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "优秀"
    assert data["motivational_message"]
    assert "next_level" not in data or data["next_level"] is None


@pytest.mark.asyncio
async def test_evaluation_feedback_needs_improvement():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "B"), ("B", "C"), ("C", "A"),  # All wrong = 0%
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/evaluation",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "待提升"
    assert data["next_level"] is not None
    assert data["next_level"]["next_level"] == "合格"
    assert data["next_level"]["points_needed"] > 0


@pytest.mark.asyncio
async def test_evaluation_has_excellence_ratio():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"), ("B", "B"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/evaluation",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    assert "excellence_ratio" in data
    assert "优秀" in data["excellence_ratio"]
    assert "total" in data["excellence_ratio"]


@pytest.mark.asyncio
async def test_evaluation_has_ranking():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/evaluation",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    assert "ranking" in data
    assert data["ranking"]["rank"] == 1
    assert data["ranking"]["total"] >= 1


@pytest.mark.asyncio
async def test_evaluation_training_recommendations():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        # Partial score to trigger recommendations
        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"), ("B", "C"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/evaluation",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    assert "training_recommendations" in data
    assert len(data["training_recommendations"]) > 0
    for rec in data["training_recommendations"]:
        assert "dimension" in rec
        assert "suggested_action" in rec
        assert "priority" in rec
