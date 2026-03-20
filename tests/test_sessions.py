"""Tests for exam sessions and answering (T013+T014)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles


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


async def setup_published_exam(client, org_token):
    """Create a published exam with approved questions. Returns (exam_id, question_ids)."""
    rev_token = await register_user(client, "reviewer")

    # Create and approve 3 questions
    qids = []
    for i in range(3):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"考试题目{i+1}：以下关于AI的说法正确的是？",
            "correct_answer": "A",
            "options": {"A": "正确答案", "B": "错误B", "C": "错误C", "D": "错误D"},
            "difficulty": 3,
            "dimension": "AI基础",
        }, headers={"Authorization": f"Bearer {org_token}"})
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit",
                         headers={"Authorization": f"Bearer {org_token}"})
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)

    # Create exam
    exam_resp = await client.post("/api/v1/exams", json={
        "title": "AI素养测试",
        "time_limit_minutes": 30,
    }, headers={"Authorization": f"Bearer {org_token}"})
    eid = exam_resp.json()["id"]

    # Add questions manually
    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [
            {"question_id": qids[i], "order_num": i + 1, "score": 10}
            for i in range(3)
        ]
    }, headers={"Authorization": f"Bearer {org_token}"})

    # Publish
    await client.post(f"/api/v1/exams/{eid}/publish",
                     headers={"Authorization": f"Bearer {org_token}"})

    return eid, qids


# ---- Start Exam ----

@pytest.mark.asyncio
async def test_start_exam():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)

        resp = await client.post(
            f"/api/v1/sessions/start/{eid}",
            headers={"Authorization": f"Bearer {ex_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exam_id"] == eid
    assert data["total_questions"] == 3
    assert "answer_sheet_id" in data


@pytest.mark.asyncio
async def test_start_unpublished_exam_fails():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        exam_resp = await client.post("/api/v1/exams", json={"title": "未发布"},
                                     headers={"Authorization": f"Bearer {org_token}"})
        eid = exam_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/sessions/start/{eid}",
            headers={"Authorization": f"Bearer {ex_token}"},
        )
    assert resp.status_code == 400
    assert "未发布" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_start_duplicate_session():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, _ = await setup_published_exam(client, org_token)

        await client.post(f"/api/v1/sessions/start/{eid}",
                         headers={"Authorization": f"Bearer {ex_token}"})

        resp = await client.post(f"/api/v1/sessions/start/{eid}",
                                headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 400
    assert "进行中" in resp.json()["detail"]


# ---- Get Session ----

@pytest.mark.asyncio
async def test_get_session_with_questions():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)

        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]

        resp = await client.get(f"/api/v1/sessions/{sid}",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exam_title"] == "AI素养测试"
    assert len(data["questions"]) == 3
    assert data["answers"] == {}


# ---- Submit Answers ----

@pytest.mark.asyncio
async def test_submit_answer():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)

        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]

        resp = await client.post(f"/api/v1/sessions/{sid}/answer", json={
            "question_id": qids[0],
            "answer_content": "A",
            "time_spent_seconds": 15,
        }, headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    assert resp.json()["answer_content"] == "A"
    assert resp.json()["question_id"] == qids[0]


@pytest.mark.asyncio
async def test_update_answer():
    """Submitting again for same question updates the answer."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)
        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]
        headers = {"Authorization": f"Bearer {ex_token}"}

        # First answer
        await client.post(f"/api/v1/sessions/{sid}/answer", json={
            "question_id": qids[0],
            "answer_content": "A",
        }, headers=headers)

        # Update
        resp = await client.post(f"/api/v1/sessions/{sid}/answer", json={
            "question_id": qids[0],
            "answer_content": "B",
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["answer_content"] == "B"


@pytest.mark.asyncio
async def test_mark_question():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)
        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]

        resp = await client.post(f"/api/v1/sessions/{sid}/mark", json={
            "question_id": qids[1],
            "is_marked": True,
        }, headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    assert resp.json()["is_marked"] is True


# ---- Submit Exam ----

@pytest.mark.asyncio
async def test_submit_exam():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)
        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]
        headers = {"Authorization": f"Bearer {ex_token}"}

        # Answer 2 out of 3
        for i in range(2):
            await client.post(f"/api/v1/sessions/{sid}/answer", json={
                "question_id": qids[i],
                "answer_content": "A",
            }, headers=headers)

        # Submit exam
        resp = await client.post(f"/api/v1/sessions/{sid}/submit", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["total_answered"] == 2
    assert data["total_questions"] == 3
    assert data["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_cannot_answer_after_submit():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)
        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]
        headers = {"Authorization": f"Bearer {ex_token}"}

        # Submit
        await client.post(f"/api/v1/sessions/{sid}/submit", headers=headers)

        # Try to answer
        resp = await client.post(f"/api/v1/sessions/{sid}/answer", json={
            "question_id": qids[0],
            "answer_content": "A",
        }, headers=headers)
    assert resp.status_code == 400
    assert "已提交" in resp.json()["detail"]


# ---- Session List ----

@pytest.mark.asyncio
async def test_list_my_sessions():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, _ = await setup_published_exam(client, org_token)

        await client.post(f"/api/v1/sessions/start/{eid}",
                         headers={"Authorization": f"Bearer {ex_token}"})

        resp = await client.get("/api/v1/sessions",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_session_detail():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        eid, qids = await setup_published_exam(client, org_token)
        start = await client.post(f"/api/v1/sessions/start/{eid}",
                                 headers={"Authorization": f"Bearer {ex_token}"})
        sid = start.json()["answer_sheet_id"]

        # Answer one question
        await client.post(f"/api/v1/sessions/{sid}/answer", json={
            "question_id": qids[0],
            "answer_content": "C",
        }, headers={"Authorization": f"Bearer {ex_token}"})

        resp = await client.get(f"/api/v1/sessions/{sid}/detail",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["answers"]) == 1
    assert data["answers"][0]["answer_content"] == "C"
