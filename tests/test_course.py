"""Tests for course management (T031)."""
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
        await conn.execute(text("TRUNCATE TABLE course_chapters CASCADE"))
        await conn.execute(text("TRUNCATE TABLE courses CASCADE"))
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


@pytest.mark.asyncio
async def test_create_course():
    async with get_client() as client:
        token = await register_user(client)
        resp = await client.post("/api/v1/courses", json={
            "title": "AI伦理入门课程",
            "description": "学习AI伦理基础知识",
            "dimension": "AI伦理安全",
            "difficulty": 2,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "AI伦理入门课程"
    assert data["dimension"] == "AI伦理安全"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_list_courses():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/courses", json={"title": "课程1"}, headers=headers)
        await client.post("/api/v1/courses", json={"title": "课程2"}, headers=headers)

        resp = await client.get("/api/v1/courses", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_course_detail():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "详情课程"},
                                   headers=headers)
        cid = create.json()["id"]

        resp = await client.get(f"/api/v1/courses/{cid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "详情课程"
    assert "chapters" in resp.json()


@pytest.mark.asyncio
async def test_update_course():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "更新课程"},
                                   headers=headers)
        cid = create.json()["id"]

        resp = await client.put(f"/api/v1/courses/{cid}",
                               json={"title": "已更新课程", "difficulty": 4},
                               headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "已更新课程"
    assert resp.json()["difficulty"] == 4


@pytest.mark.asyncio
async def test_publish_course():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "发布课程"},
                                   headers=headers)
        cid = create.json()["id"]

        resp = await client.post(f"/api/v1/courses/{cid}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_archive_course():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "归档课程"},
                                   headers=headers)
        cid = create.json()["id"]

        resp = await client.post(f"/api/v1/courses/{cid}/archive", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_add_chapters():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "章节课程"},
                                   headers=headers)
        cid = create.json()["id"]

        ch1 = await client.post(f"/api/v1/courses/{cid}/chapters", json={
            "title": "第一章 概述",
            "content": "AI伦理的基本概念...",
            "order_num": 1,
        }, headers=headers)
        ch2 = await client.post(f"/api/v1/courses/{cid}/chapters", json={
            "title": "第二章 视频讲解",
            "content_type": "video",
            "video_url": "https://example.com/video.mp4",
            "order_num": 2,
        }, headers=headers)

    assert ch1.status_code == 200
    assert ch2.status_code == 200
    assert ch1.json()["order_num"] == 1
    assert ch2.json()["content_type"] == "video"


@pytest.mark.asyncio
async def test_course_with_chapters_detail():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "完整课程"},
                                   headers=headers)
        cid = create.json()["id"]

        await client.post(f"/api/v1/courses/{cid}/chapters", json={
            "title": "章节A", "order_num": 1,
        }, headers=headers)
        await client.post(f"/api/v1/courses/{cid}/chapters", json={
            "title": "章节B", "order_num": 2,
        }, headers=headers)

        resp = await client.get(f"/api/v1/courses/{cid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["chapters"]) == 2
    assert data["chapters"][0]["title"] == "章节A"


@pytest.mark.asyncio
async def test_delete_chapter():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = await client.post("/api/v1/courses",
                                   json={"title": "删除章节课程"},
                                   headers=headers)
        cid = create.json()["id"]

        ch = await client.post(f"/api/v1/courses/{cid}/chapters", json={
            "title": "要删除", "order_num": 1,
        }, headers=headers)
        ch_id = ch.json()["id"]

        resp = await client.delete(f"/api/v1/courses/chapters/{ch_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_list_courses_filter_dimension():
    async with get_client() as client:
        token = await register_user(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/courses",
                         json={"title": "A", "dimension": "AI基础知识"},
                         headers=headers)
        await client.post("/api/v1/courses",
                         json={"title": "B", "dimension": "AI伦理安全"},
                         headers=headers)

        resp = await client.get("/api/v1/courses?dimension=AI基础知识", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
