"""Tests for question auto-calibration and deduplication (T026)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.question_calibration_service import (
    _recalibrate_difficulty,
    _text_similarity,
    _ngrams,
)


# ---- Unit Tests ----

def test_recalibrate_difficulty_easy():
    assert _recalibrate_difficulty(0.95) == 1  # Very easy
    assert _recalibrate_difficulty(0.9) == 1


def test_recalibrate_difficulty_medium():
    assert _recalibrate_difficulty(0.5) == 3
    assert _recalibrate_difficulty(0.65) == 3


def test_recalibrate_difficulty_hard():
    assert _recalibrate_difficulty(0.15) == 5  # Very hard
    assert _recalibrate_difficulty(0.35) == 4


def test_text_similarity_identical():
    assert _text_similarity("人工智能是什么？", "人工智能是什么？") == 1.0


def test_text_similarity_different():
    sim = _text_similarity("人工智能基础知识", "量子计算发展历史")
    assert sim < 0.3


def test_text_similarity_similar():
    sim = _text_similarity("人工智能的基础知识是什么？", "人工智能的基本知识是什么？")
    assert sim > 0.5


def test_text_similarity_empty():
    assert _text_similarity("", "test") == 0.0
    assert _text_similarity("test", "") == 0.0


def test_ngrams():
    result = _ngrams("abcde", 3)
    assert result == ["abc", "bcd", "cde"]


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
    """Create exam with questions, have multiple examinees take it, grade all."""
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}

    qids = []
    for i in range(len(answers_list[0])):
        correct = answers_list[0][i][0]
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"校准题{i+1}？",
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

    exam_resp = await client.post("/api/v1/exams", json={"title": "校准测试"}, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [{"question_id": qids[i], "order_num": i+1, "score": 10}
                      for i in range(len(qids))]
    }, headers=org_headers)
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

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
async def test_auto_flag_no_data():
    """Auto-flag should work even with no data."""
    async with get_client() as client:
        admin_token = await register_user(client, "admin")
        resp = await client.post(
            "/api/v1/questions/calibration/auto-flag?min_sample=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] == 0


@pytest.mark.asyncio
async def test_auto_flag_with_data():
    """Auto-flag should detect and flag low-quality questions."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        admin_token = await register_user(client, "admin")

        # Question where everyone gets wrong (too hard)
        answers_list = [
            [("A", "B")],
            [("A", "C")],
            [("A", "D")],
            [("A", "B")],
        ]
        eid, qids = await create_scored_exam(client, org_token, answers_list)

        resp = await client.post(
            "/api/v1/questions/calibration/auto-flag?min_sample=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] >= 1


@pytest.mark.asyncio
async def test_calibrate_single_question():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # Very easy question (everyone gets right) → should recalibrate to difficulty 1
        answers_list = [
            [("A", "A")],
            [("A", "A")],
            [("A", "A")],
            [("A", "A")],
        ]
        eid, qids = await create_scored_exam(client, org_token, answers_list)

        resp = await client.post(
            f"/api/v1/questions/calibration/{qids[0]}",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["calibrated"] is True
    assert data["new_difficulty"] == 1  # Very easy


@pytest.mark.asyncio
async def test_find_similar_questions():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # Create two very similar questions
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "人工智能的基本定义是什么？请选择最准确的描述。",
            "correct_answer": "A",
            "options": {"A": "a", "B": "b"},
        }, headers=org_headers)
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "人工智能的基本定义是什么？请选择最准确的答案。",
            "correct_answer": "A",
            "options": {"A": "a", "B": "b"},
        }, headers=org_headers)

        resp = await client.get(
            "/api/v1/questions/calibration/similar?threshold=0.5",
            headers=org_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["similarity"] > 0.5
