"""Tests for exam assembly strategy engine (T012)."""
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


async def create_approved_questions(client, token, count=5, qtype="single_choice", dimension="AI基础"):
    """Create questions and approve them for exam assembly."""
    rev_token = await register_user(client, "reviewer")
    qids = []
    for i in range(count):
        resp = await client.post("/api/v1/questions", json={
            "question_type": qtype,
            "stem": f"已审核{qtype}题目{i+1}？",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错误B", "C": "错误C", "D": "错误D"},
            "difficulty": 3,
            "dimension": dimension,
        }, headers={"Authorization": f"Bearer {token}"})
        qid = resp.json()["id"]
        # Submit and approve
        await client.post(f"/api/v1/questions/{qid}/submit",
                         headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)
    return qids


# ---- CRUD Tests ----

@pytest.mark.asyncio
async def test_create_exam():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post("/api/v1/exams", json={
            "title": "AI素养基础测试",
            "description": "测试AI基础知识",
            "time_limit_minutes": 60,
            "total_score": 100,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "AI素养基础测试"
    assert data["status"] == "draft"
    assert data["total_score"] == 100


@pytest.mark.asyncio
async def test_list_exams():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/exams", json={"title": "试卷1"}, headers=headers)
        await client.post("/api/v1/exams", json={"title": "试卷2"}, headers=headers)

        resp = await client.get("/api/v1/exams", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_get_exam_detail():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "详情测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.get(f"/api/v1/exams/{eid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "详情测试"
    assert resp.json()["questions"] == []


@pytest.mark.asyncio
async def test_get_exam_composition():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        qids = await create_approved_questions(client, token, count=2)

        create = await client.post("/api/v1/exams", json={"title": "编排详情"}, headers=headers)
        eid = create.json()["id"]
        await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [
                {"question_id": qids[0], "order_num": 1, "score": 12},
                {"question_id": qids[1], "order_num": 2, "score": 18},
            ]
        }, headers=headers)

        resp = await client.get(f"/api/v1/exams/{eid}/composition", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["exam"]["title"] == "编排详情"
    assert len(data["items"]) == 2
    assert data["items"][0]["question"]["stem"].startswith("已审核")


@pytest.mark.asyncio
async def test_update_exam():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "原标题"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.put(f"/api/v1/exams/{eid}", json={
            "title": "新标题",
            "time_limit_minutes": 90,
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"
    assert resp.json()["time_limit_minutes"] == 90


@pytest.mark.asyncio
async def test_delete_exam():
    async with get_client() as client:
        token = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "待删除"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.delete(f"/api/v1/exams/{eid}", headers=headers)
        assert resp.status_code == 204

        resp2 = await client.get(f"/api/v1/exams/{eid}", headers=headers)
        assert resp2.status_code == 404


# ---- Manual Assembly ----

@pytest.mark.asyncio
async def test_manual_assemble():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        qids = await create_approved_questions(client, token, count=3)

        create = await client.post("/api/v1/exams", json={"title": "手动组卷测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [
                {"question_id": qids[0], "order_num": 1, "score": 10},
                {"question_id": qids[1], "order_num": 2, "score": 10},
                {"question_id": qids[2], "order_num": 3, "score": 10},
            ]
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_questions"] == 3
    assert data["total_score"] == 30


@pytest.mark.asyncio
async def test_save_exam_composition_updates_order_and_score():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        qids = await create_approved_questions(client, token, count=3)

        create = await client.post("/api/v1/exams", json={"title": "编排保存测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.put(f"/api/v1/exams/{eid}/composition", json={
            "items": [
                {"question_id": qids[2], "order_num": 1, "score": 20},
                {"question_id": qids[0], "order_num": 2, "score": 15},
            ]
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["exam"]["total_score"] == 35
    assert [item["question_id"] for item in data["items"]] == [qids[2], qids[0]]
    assert data["items"][0]["score"] == 20


@pytest.mark.asyncio
async def test_save_exam_composition_rejects_duplicate_questions():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        qids = await create_approved_questions(client, token, count=1)
        create = await client.post("/api/v1/exams", json={"title": "重复题测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.put(f"/api/v1/exams/{eid}/composition", json={
            "items": [
                {"question_id": qids[0], "order_num": 1, "score": 10},
                {"question_id": qids[0], "order_num": 2, "score": 10},
            ]
        }, headers=headers)
    assert resp.status_code == 400
    assert "重复" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_save_exam_composition_requires_approved_questions():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_q = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "未审核题目？",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错误"},
            "difficulty": 3,
            "dimension": "AI基础",
        }, headers=headers)
        qid = create_q.json()["id"]
        create_exam_resp = await client.post("/api/v1/exams", json={"title": "未审核候选测试"}, headers=headers)
        eid = create_exam_resp.json()["id"]

        resp = await client.put(f"/api/v1/exams/{eid}/composition", json={
            "items": [
                {"question_id": qid, "order_num": 1, "score": 10},
            ]
        }, headers=headers)
    assert resp.status_code == 400
    assert "已审核通过" in resp.json()["detail"]


# ---- Auto Assembly ----

@pytest.mark.asyncio
async def test_auto_assemble():
    """Auto-assemble selects approved questions matching constraints."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        # Create 5 approved single_choice questions
        await create_approved_questions(client, token, count=5, qtype="single_choice")

        create = await client.post("/api/v1/exams", json={"title": "自动组卷测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/assemble/auto", json={
            "type_distribution": {"single_choice": 3},
            "difficulty_target": 3,
            "difficulty_tolerance": 2,
            "score_per_question": 10,
        }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_questions"] == 3
    assert data["total_score"] == 30


@pytest.mark.asyncio
async def test_auto_assemble_with_dimension_filter():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        await create_approved_questions(client, token, count=3, dimension="AI伦理")
        await create_approved_questions(client, token, count=3, dimension="AI技术")

        create = await client.post("/api/v1/exams", json={"title": "维度筛选测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/assemble/auto", json={
            "type_distribution": {"single_choice": 2},
            "difficulty_target": 3,
            "dimensions": ["AI伦理"],
            "score_per_question": 5,
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total_questions"] == 2


@pytest.mark.asyncio
async def test_auto_assemble_no_approved_questions():
    """Auto-assemble with no approved questions returns 0 questions."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "空组卷"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/assemble/auto", json={
            "type_distribution": {"single_choice": 5},
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total_questions"] == 0


# ---- Lifecycle ----

@pytest.mark.asyncio
async def test_publish_exam():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        qids = await create_approved_questions(client, token, count=2)

        create = await client.post("/api/v1/exams", json={"title": "发布测试"}, headers=headers)
        eid = create.json()["id"]

        # Add questions
        await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [
                {"question_id": qids[0], "order_num": 1, "score": 50},
                {"question_id": qids[1], "order_num": 2, "score": 50},
            ]
        }, headers=headers)

        # Publish
        resp = await client.post(f"/api/v1/exams/{eid}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_publish_empty_exam_fails():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "空试卷"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/publish", headers=headers)
    assert resp.status_code == 400
    assert "至少需要" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_publish_exam_fails_when_question_is_no_longer_approved():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        reviewer_token = await register_user(client, "reviewer")
        headers = {"Authorization": f"Bearer {token}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

        qids = await create_approved_questions(client, token, count=1)
        create = await client.post("/api/v1/exams", json={"title": "发布前校验"}, headers=headers)
        eid = create.json()["id"]

        await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [
                {"question_id": qids[0], "order_num": 1, "score": 100},
            ]
        }, headers=headers)
        await client.post(f"/api/v1/questions/{qids[0]}/review", json={
            "action": "reject",
            "comment": "发布前撤回",
        }, headers=reviewer_headers)

        resp = await client.post(f"/api/v1/exams/{eid}/publish", headers=headers)
    assert resp.status_code == 400
    assert "已审核通过" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_close_exam():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post("/api/v1/exams", json={"title": "关闭测试"}, headers=headers)
        eid = create.json()["id"]

        resp = await client.post(f"/api/v1/exams/{eid}/close", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


# ---- RBAC ----

@pytest.mark.asyncio
async def test_examinee_cannot_create_exam():
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post("/api/v1/exams", json={"title": "不应成功"},
                                headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_exam_stats():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/exams", json={"title": "统计1"}, headers=headers)

        resp = await client.get("/api/v1/exams/stats", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_question_list_supports_exclude_ids():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        qids = await create_approved_questions(client, token, count=3)

        resp = await client.get(
            "/api/v1/questions",
            params=[
                ("status", "approved"),
                ("exclude_ids", qids[0]),
                ("exclude_ids", qids[1]),
            ],
            headers=headers,
        )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert qids[0] not in ids
    assert qids[1] not in ids
