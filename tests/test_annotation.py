"""Tests for material annotation (T024)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.annotation_agent import auto_annotate_content, _rule_based_annotation


# ---- Unit Tests ----

def test_rule_based_annotation_ai_basics():
    result = _rule_based_annotation(
        "人工智能基础入门：了解机器学习和深度学习的基本概念",
        "AI入门教程"
    )
    assert result["dimension"] == "AI基础知识"
    assert result["difficulty"] >= 1
    assert len(result["knowledge_points"]) > 0
    assert "人工智能" in result["knowledge_points"]
    assert result["confidence"] == 0.6


def test_rule_based_annotation_ethics():
    result = _rule_based_annotation(
        "AI伦理与隐私保护：数据安全、算法偏见与公平性问题",
        "AI伦理课程"
    )
    assert result["dimension"] == "AI伦理安全"
    assert "summary" in result
    assert "tags" in result


def test_rule_based_annotation_innovation():
    result = _rule_based_annotation(
        "提示工程与创新设计：如何通过prompt优化AI输出",
        "创新实践"
    )
    assert result["dimension"] == "AI创新实践"


def test_rule_based_annotation_difficulty_levels():
    basic = _rule_based_annotation("什么是人工智能？基础入门概述", None)
    advanced = _rule_based_annotation("高级深度学习模型调优与进阶技术", None)
    assert basic["difficulty"] < advanced["difficulty"]


def test_auto_annotate_content_returns_all_fields():
    result = auto_annotate_content(
        "神经网络训练数据集处理方法",
        "数据预处理"
    )
    assert "dimension" in result
    assert "difficulty" in result
    assert "knowledge_points" in result
    assert "summary" in result
    assert "confidence" in result


def test_rule_based_annotation_empty_content():
    result = _rule_based_annotation("", None)
    assert result["dimension"] is not None
    assert result["knowledge_points"] == ["AI相关知识"]


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
        await conn.execute(text("TRUNCATE TABLE annotations CASCADE"))
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


async def upload_material(client, token):
    """Upload a test material and return its ID."""
    import io
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.md", io.BytesIO(b"# AI basics\n\nmachine learning and deep learning"), "text/markdown")}
    data = {"title": "人工智能基础入门教程", "category": "AI基础"}
    resp = await client.post("/api/v1/materials", headers=headers, files=files, data=data)
    assert resp.status_code in (200, 201), f"Upload failed: {resp.status_code} {resp.text}"
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_auto_annotate_material():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        resp = await client.post(
            f"/api/v1/annotations/materials/{material_id}/auto",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["annotation_type"] == "ai_auto"
    assert data[0]["dimension"] is not None


@pytest.mark.asyncio
async def test_manual_annotation():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        resp = await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={
                "content": "这段内容讲解了机器学习基本概念",
                "dimension": "AI基础知识",
                "difficulty": 2,
                "highlighted_text": "machine learning",
                "start_offset": 12,
                "end_offset": 28,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["annotation_type"] == "manual"
    assert data["dimension"] == "AI基础知识"
    assert data["difficulty"] == 2
    assert data["highlighted_text"] == "machine learning"


@pytest.mark.asyncio
async def test_list_annotations():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        # Create two annotations
        await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "标注1", "dimension": "AI基础知识"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/annotations/materials/{material_id}/auto",
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = await client.get(
            f"/api/v1/annotations/materials/{material_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_annotations_filter_type():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "手动标注"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/annotations/materials/{material_id}/auto",
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = await client.get(
            f"/api/v1/annotations/materials/{material_id}?annotation_type=manual",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert all(a["annotation_type"] == "manual" for a in data)


@pytest.mark.asyncio
async def test_delete_annotation():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        create_resp = await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "要删除的标注"},
            headers={"Authorization": f"Bearer {token}"},
        )
        ann_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/annotations/{ann_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_annotation_by_other_user_forbidden():
    async with get_client() as client:
        token1 = await register_user(client)
        token2 = await register_user(client)
        material_id = await upload_material(client, token1)

        create_resp = await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "用户1的标注"},
            headers={"Authorization": f"Bearer {token1}"},
        )
        ann_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/annotations/{ann_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_annotation_consistency_no_conflicts():
    async with get_client() as client:
        token = await register_user(client)
        material_id = await upload_material(client, token)

        resp = await client.get(
            f"/api/v1/annotations/materials/{material_id}/consistency",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consistent"] is True


@pytest.mark.asyncio
async def test_annotation_consistency_with_conflicts():
    async with get_client() as client:
        token1 = await register_user(client)
        token2 = await register_user(client)
        material_id = await upload_material(client, token1)

        # Two annotators with different dimensions
        await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "标注A", "dimension": "AI基础知识", "difficulty": 1},
            headers={"Authorization": f"Bearer {token1}"},
        )
        await client.post(
            f"/api/v1/annotations/materials/{material_id}/manual",
            json={"content": "标注B", "dimension": "AI伦理安全", "difficulty": 5},
            headers={"Authorization": f"Bearer {token2}"},
        )

        resp = await client.get(
            f"/api/v1/annotations/materials/{material_id}/consistency",
            headers={"Authorization": f"Bearer {token1}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["annotator_count"] == 2
    assert len(data["conflicts"]) > 0
