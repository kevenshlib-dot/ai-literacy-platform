import io
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.embedding_service import embed_texts, get_embedding_dim


# ---- Unit Tests for Embedding Service ----

def test_embed_texts_deterministic():
    """Same text should produce the same embedding."""
    v1 = embed_texts(["AI是人工智能"])[0]
    v2 = embed_texts(["AI是人工智能"])[0]
    assert v1 == v2


def test_embed_texts_different():
    """Different texts should produce different embeddings."""
    v1 = embed_texts(["人工智能"])[0]
    v2 = embed_texts(["机器学习"])[0]
    assert v1 != v2


def test_embed_dimension():
    """Embedding should have the expected dimension."""
    dim = get_embedding_dim()
    v = embed_texts(["test"])[0]
    assert len(v) == dim


def test_embed_batch():
    """Should handle batch embedding."""
    texts = ["文本一", "文本二", "文本三"]
    results = embed_texts(texts)
    assert len(results) == 3
    assert all(len(v) == get_embedding_dim() for v in results)


def test_embed_normalized():
    """Embeddings should be approximately unit vectors."""
    v = embed_texts(["测试文本"])[0]
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 0.01


# ---- Integration Tests with Milvus ----

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
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
        await conn.execute(text("TRUNCATE TABLE knowledge_units CASCADE"))
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
async def test_vectorize_and_search():
    """Full pipeline: upload → parse → vectorize → semantic search."""
    async with get_client() as client:
        token = await register_user(client, "organizer")

        # 1. Upload markdown material about AI
        md_content = (
            "# 人工智能基础\n\n"
            "人工智能（AI）是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。"
            "机器学习是人工智能的核心技术之一，它让计算机能够从数据中学习。" * 10
            + "\n\n## 深度学习\n\n"
            "深度学习是机器学习的一个子领域，使用多层神经网络来处理复杂的模式识别任务。"
            "卷积神经网络（CNN）广泛应用于图像识别领域。" * 10
        )
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("ai_intro.md", md_content.encode(), "text/markdown")},
            data={"title": "AI入门教材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert upload.status_code == 201
        mid = upload.json()["id"]

        # 2. Parse the material
        parse_resp = await client.post(
            f"/api/v1/materials/{mid}/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert parse_resp.status_code == 200

        # 3. Vectorize
        vec_resp = await client.post(
            f"/api/v1/materials/{mid}/vectorize",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert vec_resp.status_code == 200
        assert vec_resp.json()["vectorized"] > 0

        # 4. Semantic search
        search_resp = await client.get(
            "/api/v1/materials/search/semantic?q=机器学习是什么&top_k=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert search_resp.status_code == 200
        data = search_resp.json()
        assert data["total"] > 0
        assert len(data["results"]) <= 3
        # Each result should have content and score
        for r in data["results"]:
            assert "content" in r
            assert "score" in r


@pytest.mark.asyncio
async def test_vectorize_after_manual_parse():
    """Parse then vectorize a small CSV material."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("data.csv", b"name,score\nAlice,95\nBob,87\nCarol,92", "text/csv")},
            data={"title": "成绩数据"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]

        # Manually parse first
        parse_resp = await client.post(
            f"/api/v1/materials/{mid}/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert parse_resp.status_code == 200

        # Then vectorize
        vec_resp = await client.post(
            f"/api/v1/materials/{mid}/vectorize",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert vec_resp.status_code == 200
        assert vec_resp.json()["vectorized"] > 0


@pytest.mark.asyncio
async def test_vector_stats():
    """Check vector collection statistics endpoint."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/materials/search/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "exists" in data
