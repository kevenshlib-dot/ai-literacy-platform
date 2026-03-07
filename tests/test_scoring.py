"""Tests for scoring engine and report generation (T015-T017)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.scoring_agent import _rule_based_scoring


# ---- Unit Tests for Scoring Agent ----

def test_rule_based_scoring_correct():
    result = _rule_based_scoring(
        stem="什么是AI？",
        correct_answer="人工智能，计算机科学，智能系统",
        student_answer="人工智能是计算机科学的一个分支，用于构建智能系统。",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] > 0
    assert "feedback" in result


def test_rule_based_scoring_empty():
    result = _rule_based_scoring(
        stem="什么是ML？",
        correct_answer="机器学习",
        student_answer="",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] == 0.0
    assert result["is_correct"] is False
    assert "未作答" in result["feedback"]


def test_rule_based_scoring_partial():
    result = _rule_based_scoring(
        stem="深度学习的特点？",
        correct_answer="多层神经网络，自动特征提取，大数据驱动",
        student_answer="深度学习使用多层神经网络来学习。",
        question_type="short_answer",
        max_score=10.0,
    )
    assert 0 < result["earned_score"] <= 10.0


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


async def setup_exam_and_submit(client, org_token, ex_token, answers_map):
    """Full flow: create exam -> examinee takes it -> submit.

    answers_map: list of (correct_answer_for_question, student_answer) tuples.
    Returns (sheet_id, org_token).
    """
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, (correct, _) in enumerate(answers_map):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"测评题目{i+1}？",
            "correct_answer": correct,
            "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
            "difficulty": 3,
            "dimension": f"维度{i % 2 + 1}",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)

    # Create and publish exam
    exam_resp = await client.post("/api/v1/exams", json={
        "title": "评分测试考试",
    }, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [
            {"question_id": qids[i], "order_num": i + 1, "score": 10}
            for i in range(len(qids))
        ]
    }, headers=org_headers)

    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    # Examinee takes exam
    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    # Submit answers
    for i, (_, student_answer) in enumerate(answers_map):
        if student_answer is not None:
            await client.post(f"/api/v1/sessions/{sid}/answer", json={
                "question_id": qids[i],
                "answer_content": student_answer,
            }, headers=ex_headers)

    # Submit exam
    await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)

    return sid


@pytest.mark.asyncio
async def test_grade_all_correct():
    """All correct answers should get full score."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
        ])

        resp = await client.post(
            f"/api/v1/scores/grade/{sid}",
            headers={"Authorization": f"Bearer {org_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_score"] == 30.0
    assert data["max_score"] == 30.0
    assert data["level"] == "优秀"


@pytest.mark.asyncio
async def test_grade_all_wrong():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "B"),
            ("B", "C"),
            ("C", "A"),
        ])

        resp = await client.post(
            f"/api/v1/scores/grade/{sid}",
            headers={"Authorization": f"Bearer {org_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_score"] == 0.0
    assert data["level"] == "不合格"


@pytest.mark.asyncio
async def test_grade_partial():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),  # correct
            ("B", "C"),  # wrong
            ("C", None), # unanswered
        ])

        resp = await client.post(
            f"/api/v1/scores/grade/{sid}",
            headers={"Authorization": f"Bearer {org_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_score"] == 10.0  # only first correct
    assert data["max_score"] == 30.0


@pytest.mark.asyncio
async def test_get_score_by_sheet():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])

        await client.post(f"/api/v1/scores/grade/{sid}",
                         headers={"Authorization": f"Bearer {org_token}"})

        resp = await client.get(f"/api/v1/scores/sheet/{sid}",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_score"] == 20.0
    assert len(data["details"]) == 2
    for d in data["details"]:
        assert d["is_correct"] is True
        assert d["feedback"] == "正确"


@pytest.mark.asyncio
async def test_cannot_double_grade():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [("A", "A")])
        headers = {"Authorization": f"Bearer {org_token}"}

        await client.post(f"/api/v1/scores/grade/{sid}", headers=headers)
        resp = await client.post(f"/api/v1/scores/grade/{sid}", headers=headers)
    assert resp.status_code == 400
    assert "已评分" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_report():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "C"),
        ])

        grade_resp = await client.post(f"/api/v1/scores/grade/{sid}",
                                      headers={"Authorization": f"Bearer {org_token}"})
        score_id = grade_resp.json()["score_id"]

        resp = await client.post(f"/api/v1/scores/{score_id}/report",
                                headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ratio" in data
    assert "dimension_analysis" in data
    assert "recommendations" in data
    assert data["total_questions"] == 2
    assert data["correct_count"] == 1


@pytest.mark.asyncio
async def test_dimension_scores():
    """Verify dimension-level scoring breakdown."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),  # 维度1 - correct
            ("B", "C"),  # 维度2 - wrong
        ])

        grade_resp = await client.post(f"/api/v1/scores/grade/{sid}",
                                      headers={"Authorization": f"Bearer {org_token}"})
        data = grade_resp.json()
    assert "dimension_scores" in data
    dim_scores = data["dimension_scores"]
    assert "维度1" in dim_scores
    assert "维度2" in dim_scores
    assert dim_scores["维度1"]["earned"] == 10.0
    assert dim_scores["维度2"]["earned"] == 0.0
