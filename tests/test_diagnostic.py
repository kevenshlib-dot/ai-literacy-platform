"""Tests for five-dimensional diagnostic report (T022)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.models.user import User


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
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
    data = resp.json()
    if data.get("access_token"):
        return data["access_token"]

    user_id = data["user"]["id"]
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        user.is_active = True
        await session.commit()
    await engine.dispose()

    login_resp = await client.post("/api/v1/auth/login", json={
        "username": f"user_{unique}",
        "password": "password123",
    })
    return login_resp.json()["access_token"]


async def create_scored_exam(client, org_token, ex_token, answers):
    """Create exam, take it, grade it. Returns score_id."""
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, (correct, _) in enumerate(answers):
        dim = f"AI基础知识" if i % 2 == 0 else "AI伦理安全"
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"诊断题{i+1}？",
            "correct_answer": correct,
            "options": {"A": "选A", "B": "选B", "C": "选C", "D": "选D"},
            "difficulty": 3,
            "dimension": dim,
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)

    exam_resp = await client.post("/api/v1/exams", json={
        "title": "诊断测试",
    }, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [
            {"question_id": qids[i], "order_num": i+1, "score": 10}
            for i in range(len(qids))
        ]
    }, headers=org_headers)
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    for i, (_, answer) in enumerate(answers):
        if answer is not None:
            await client.post(f"/api/v1/sessions/{sid}/answer", json={
                "question_id": qids[i],
                "answer_content": answer,
            }, headers=ex_headers)

    await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)
    score_resp = await client.get(
        f"/api/v1/scores/sheet/{sid}",
        headers={"Authorization": f"Bearer {ex_token}"},
    )
    assert score_resp.status_code == 200
    return score_resp.json()["score_id"]


@pytest.mark.asyncio
async def test_diagnostic_report_basic():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),  # correct
            ("B", "C"),  # wrong
            ("A", "A"),  # correct
            ("B", "B"),  # correct
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "radar_data" in data
    assert len(data["radar_data"]) == 5  # Five dimensions
    assert "dimension_analysis" in data
    assert "strengths" in data
    assert "weaknesses" in data
    assert "recommendations" in data
    assert "comparison" in data
    assert "wrong_answer_summary" in data
    assert "personalized_summary" in data
    assert "improvement_priorities" in data
    assert "actionable_suggestions" in data
    assert "recommended_resources" in data


@pytest.mark.asyncio
async def test_diagnostic_radar_data_format():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    for item in data["radar_data"]:
        assert "dimension" in item
        assert "score" in item
        assert "max" in item
        assert "level" in item
        assert 0 <= item["score"] <= 100


@pytest.mark.asyncio
async def test_diagnostic_comparison_data():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    comp = data["comparison"]
    assert "items" in comp
    assert "above_average_count" in comp
    assert "below_average_count" in comp
    for item in comp["items"]:
        assert "dimension" in item
        assert "user_score" in item
        assert "avg_score" in item
        assert "diff" in item


@pytest.mark.asyncio
async def test_diagnostic_recommendations():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "B"),  # all wrong
            ("B", "C"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    recs = data["recommendations"]
    assert len(recs) > 0
    assert isinstance(recs[0], str)


@pytest.mark.asyncio
async def test_diagnostic_wrong_answer_summary_contains_reason_details():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "B"),
            ("B", "C"),
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    wrong_summary = data["wrong_answer_summary"]
    assert "overview" in wrong_summary
    assert len(wrong_summary["items"]) > 0
    item = wrong_summary["items"][0]
    assert "question_id" in item
    assert "reason_summary" in item
    assert "improvement_tip" in item


@pytest.mark.asyncio
async def test_diagnostic_percentile():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex1_token = await register_user(client, "examinee")
        ex2_token = await register_user(client, "examinee")

        # Create shared exam setup - both take the same exam
        rev_token = await register_user(client, "reviewer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # Create question
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "百分位测试？",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错", "C": "错", "D": "错"},
            "difficulty": 3,
            "dimension": "AI基础",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})

        exam_resp = await client.post("/api/v1/exams", json={"title": "排名测试"}, headers=org_headers)
        eid = exam_resp.json()["id"]
        await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [{"question_id": qid, "order_num": 1, "score": 10}]
        }, headers=org_headers)
        await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

        # Examinee 1: correct
        s1 = await client.post(f"/api/v1/sessions/start/{eid}",
                              headers={"Authorization": f"Bearer {ex1_token}"})
        sid1 = s1.json()["answer_sheet_id"]
        await client.post(f"/api/v1/sessions/{sid1}/answer", json={
            "question_id": qid, "answer_content": "A",
        }, headers={"Authorization": f"Bearer {ex1_token}"})
        await client.post(f"/api/v1/sessions/{sid1}/submit",
                         headers={"Authorization": f"Bearer {ex1_token}"})

        # Examinee 2: wrong
        s2 = await client.post(f"/api/v1/sessions/start/{eid}",
                              headers={"Authorization": f"Bearer {ex2_token}"})
        sid2 = s2.json()["answer_sheet_id"]
        await client.post(f"/api/v1/sessions/{sid2}/answer", json={
            "question_id": qid, "answer_content": "B",
        }, headers={"Authorization": f"Bearer {ex2_token}"})
        await client.post(f"/api/v1/sessions/{sid2}/submit",
                         headers={"Authorization": f"Bearer {ex2_token}"})

        score_1 = await client.get(
            f"/api/v1/scores/sheet/{sid1}",
            headers={"Authorization": f"Bearer {ex1_token}"},
        )
        score_2 = await client.get(
            f"/api/v1/scores/sheet/{sid2}",
            headers={"Authorization": f"Bearer {ex2_token}"},
        )
        score_id_1 = score_1.json()["score_id"]
        score_id_2 = score_2.json()["score_id"]

        # Check diagnostics - ex1 should rank higher
        d1 = await client.get(f"/api/v1/scores/{score_id_1}/diagnostic",
                             headers={"Authorization": f"Bearer {ex1_token}"})
        d2 = await client.get(f"/api/v1/scores/{score_id_2}/diagnostic",
                             headers={"Authorization": f"Bearer {ex2_token}"})
    assert d1.status_code == 200
    assert d2.status_code == 200
    assert d1.json()["percentile_rank"] >= d2.json()["percentile_rank"]
