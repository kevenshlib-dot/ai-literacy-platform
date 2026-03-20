"""Tests for question quality analysis - CTT/IRT (T025)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.question_analysis_service import (
    _estimate_irt_params,
    _quality_level,
    _quality_distribution,
)


# ---- Unit Tests ----

def test_irt_params_easy_question():
    result = _estimate_irt_params(0.9, 0.5)
    assert result["difficulty_b"] < 0  # Easy question = negative b
    assert result["discrimination_a"] > 0
    assert result["guessing_c"] == 0.25


def test_irt_params_hard_question():
    result = _estimate_irt_params(0.1, 0.6)
    assert result["difficulty_b"] > 0  # Hard question = positive b


def test_irt_params_boundary():
    result = _estimate_irt_params(0.0, 0.0)
    assert result["difficulty_b"] == 4.0
    result2 = _estimate_irt_params(1.0, 1.0)
    assert result2["difficulty_b"] == -4.0


def test_quality_level_excellent():
    assert _quality_level(0.5, 0.5) == "优质"
    assert _quality_level(0.6, 0.4) == "优质"


def test_quality_level_acceptable():
    assert _quality_level(0.85, 0.25) == "合格"


def test_quality_level_needs_improvement():
    assert _quality_level(0.95, 0.1) == "待改进"


def test_quality_level_problematic():
    assert _quality_level(0.5, -0.1) == "问题"


def test_quality_distribution():
    analyses = [
        {"quality_level": "优质"},
        {"quality_level": "优质"},
        {"quality_level": "合格"},
        {"quality_level": "待改进"},
    ]
    dist = _quality_distribution(analyses)
    assert dist["优质"] == 2
    assert dist["合格"] == 1
    assert dist["待改进"] == 1
    assert dist["问题"] == 0


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


async def create_scored_exam(client, org_token, answers_list):
    """Create exam, have multiple examinees take it, grade all. Returns exam_id."""
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}

    # Create questions
    qids = []
    for i in range(len(answers_list[0])):
        correct = answers_list[0][i][0]
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"分析题{i+1}？",
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

    # Create exam
    exam_resp = await client.post("/api/v1/exams", json={"title": "分析测试"}, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [{"question_id": qids[i], "order_num": i+1, "score": 10}
                      for i in range(len(qids))]
    }, headers=org_headers)
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    # Multiple examinees take the exam
    for examinee_answers in answers_list:
        ex_token = await register_user(client, "examinee")
        ex_headers = {"Authorization": f"Bearer {ex_token}"}

        start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
        sid = start.json()["answer_sheet_id"]

        for i, (_, answer) in enumerate(examinee_answers):
            if answer is not None:
                await client.post(f"/api/v1/sessions/{sid}/answer", json={
                    "question_id": qids[i], "answer_content": answer,
                }, headers=ex_headers)

        await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)
        await client.post(f"/api/v1/scores/grade/{sid}", headers=org_headers)

    return eid, qids


@pytest.mark.asyncio
async def test_analyze_single_question_no_data():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "无数据题目？",
            "correct_answer": "A",
            "options": {"A": "a", "B": "b"},
            "difficulty": 3,
        }, headers=org_headers)
        qid = resp.json()["id"]

        resp = await client.get(
            f"/api/v1/questions/analysis/{qid}",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_size"] == 0
    assert "message" in data


@pytest.mark.asyncio
async def test_analyze_single_question_with_data():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # 4 examinees: 3 correct, 1 wrong → difficulty=0.75
        answers_list = [
            [("A", "A")],  # Correct
            [("A", "A")],  # Correct
            [("A", "A")],  # Correct
            [("A", "B")],  # Wrong
        ]
        eid, qids = await create_scored_exam(client, org_token, answers_list)

        resp = await client.get(
            f"/api/v1/questions/analysis/{qids[0]}",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_size"] == 4
    assert "ctt" in data
    assert data["ctt"]["difficulty_index"] == 0.75
    assert "irt" in data
    assert "quality_level" in data


@pytest.mark.asyncio
async def test_analyze_exam_questions():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # 3 questions, 4 examinees with varied answers
        answers_list = [
            [("A", "A"), ("B", "B"), ("C", "C")],  # All correct
            [("A", "A"), ("B", "B"), ("C", "A")],  # 2/3 correct
            [("A", "B"), ("B", "B"), ("C", "A")],  # 1/3 correct
            [("A", "B"), ("B", "C"), ("C", "A")],  # 0/3 correct
        ]
        eid, qids = await create_scored_exam(client, org_token, answers_list)

        resp = await client.get(
            f"/api/v1/exams/{eid}/analysis",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_questions"] == 3
    assert data["analyzed_questions"] == 3
    assert len(data["questions"]) == 3
    assert "summary" in data
    assert "avg_difficulty" in data["summary"]
    assert "avg_discrimination" in data["summary"]
    assert "cronbach_alpha" in data["summary"]
    assert "quality_distribution" in data["summary"]


@pytest.mark.asyncio
async def test_question_quality_report():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # min_sample=1 to get results with small data
        resp = await client.get(
            "/api/v1/questions/analysis/report?min_sample=1",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_analyzed" in data
    assert "questions" in data


@pytest.mark.asyncio
async def test_question_flags_extreme_difficulty():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # All wrong → too hard → flagged
        answers_list = [
            [("A", "B")],
            [("A", "C")],
            [("A", "D")],
            [("A", "B")],
            [("A", "C")],
        ]
        eid, qids = await create_scored_exam(client, org_token, answers_list)

        resp = await client.get(
            f"/api/v1/questions/analysis/{qids[0]}",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ctt"]["difficulty_index"] == 0.0
    assert len(data["flags"]) > 0
    assert any("过难" in f for f in data["flags"])
