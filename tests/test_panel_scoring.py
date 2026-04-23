"""Tests for multi-model evaluator panel scoring (T020)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents.scoring_agent import multi_model_score, _rule_based_panel_scoring


# ---- Unit Tests ----

def test_panel_score_correct_answer():
    result = multi_model_score(
        stem="什么是AI？",
        correct_answer="人工智能，计算机科学，智能系统",
        student_answer="人工智能是计算机科学的一个分支，用于构建智能系统。",
        question_type="short_answer",
        max_score=10.0,
        num_evaluators=3,
    )
    assert result["earned_score"] > 0
    assert "panel_scores" in result
    assert len(result["panel_scores"]) == 3
    assert "dimension_scores" in result
    assert "accuracy" in result["dimension_scores"]


def test_panel_score_empty_answer():
    result = multi_model_score(
        stem="什么是ML？",
        correct_answer="机器学习",
        student_answer="",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] == 0.0
    assert result["is_correct"] is False


def test_panel_score_partial():
    result = multi_model_score(
        stem="深度学习的特点？",
        correct_answer="多层神经网络，自动特征提取，大数据驱动",
        student_answer="深度学习使用多层神经网络",
        question_type="short_answer",
        max_score=10.0,
        num_evaluators=3,
    )
    assert 0 < result["earned_score"] <= 10.0
    assert result["evaluator_count"] == 3
    assert "score_variance" in result


def test_panel_score_has_dimension_breakdown():
    result = multi_model_score(
        stem="解释监督学习",
        correct_answer="监督学习，标签数据，分类，回归",
        student_answer="监督学习是使用标签数据训练模型的方法，可以用于分类和回归任务。",
        question_type="short_answer",
        max_score=10.0,
    )
    dims = result["dimension_scores"]
    assert "accuracy" in dims
    assert "completeness" in dims
    assert "logic" in dims
    assert "expression" in dims
    for v in dims.values():
        assert 0 <= v <= 10


def test_panel_score_variance_reasonable():
    """Panel scores should have low variance (consistent evaluators)."""
    result = multi_model_score(
        stem="什么是NLP？",
        correct_answer="自然语言处理，文本分析，语言理解",
        student_answer="自然语言处理是让计算机理解和处理人类语言的技术。",
        question_type="short_answer",
        max_score=10.0,
        num_evaluators=3,
    )
    assert result["score_variance"] < 0.5  # Evaluators should roughly agree


def test_rule_based_panel_scoring():
    result = _rule_based_panel_scoring(
        stem="什么是CNN？",
        correct_answer="卷积神经网络，图像识别，特征提取",
        student_answer="CNN是卷积神经网络，用于图像识别。",
        question_type="short_answer",
        max_score=10.0,
        num_evaluators=3,
    )
    assert len(result["panel_scores"]) == 3
    assert result["evaluator_count"] == 3


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
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        pass
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
async def test_panel_score_endpoint():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post("/api/v1/scores/panel-score", json={
            "stem": "什么是深度学习？",
            "correct_answer": "多层神经网络，自动学习特征，大数据训练",
            "student_answer": "深度学习使用多层神经网络来自动学习数据特征。",
            "max_score": 10.0,
            "num_evaluators": 3,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["earned_score"] > 0
    assert len(data["panel_scores"]) == 3
    assert "dimension_scores" in data


@pytest.mark.asyncio
async def test_panel_score_with_rubric():
    async with get_client() as client:
        token = await register_user(client, "reviewer")
        resp = await client.post("/api/v1/scores/panel-score", json={
            "stem": "解释AI伦理的重要性",
            "correct_answer": "公平性，透明度，隐私保护，责任归属",
            "student_answer": "AI伦理很重要，需要确保公平性和保护隐私。",
            "rubric": {
                "满分": "覆盖4个要点且论述深入",
                "及格": "覆盖2个要点",
                "不及格": "少于2个要点"
            },
            "max_score": 10.0,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "feedback" in data


@pytest.mark.asyncio
async def test_panel_score_examinee_forbidden():
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post("/api/v1/scores/panel-score", json={
            "stem": "test",
            "correct_answer": "test",
            "student_answer": "test",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
