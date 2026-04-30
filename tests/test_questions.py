"""Tests for question generation engine (T009)."""
import io
import re
import threading
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.services import question_prompt_service, question_service
from app.models.material import Material, MaterialFormat, MaterialStatus, KnowledgeUnit
from app.models.material_generation import MaterialGenerationRun, MaterialGenerationRunUnit
from app.models.question import BloomLevel, Question, QuestionStatus, QuestionType
from app.models.question_prompt_profile import QuestionPromptProfile
from app.services.user_service import create_user, init_roles
from app.agents.question_agent import generate_questions_via_llm, _template_fallback

VALID_TEST_USER_PROMPT_TEMPLATE = (
    "题型={{question_types}}\n"
    "数量={{count}}\n"
    "{{difficulty_section}}\n"
    "{{diversity_rules}}\n"
    "{{question_plan_section}}\n"
    "{{content_section}}"
)


# ---- Unit Tests for Question Agent ----

def test_template_fallback_single_choice():
    """Template fallback generates single choice questions."""
    questions = _template_fallback(
        content="人工智能是计算机科学的一个分支，它企图了解智能的实质。",
        question_types=["single_choice"],
        count=2,
        difficulty=3,
    )
    assert len(questions) == 2
    for q in questions:
        assert q["question_type"] == "single_choice"
        assert "stem" in q
        assert "options" in q
        assert "correct_answer" in q
        assert q["correct_answer"] == "A"
        assert "A" in q["options"]
        assert "D" in q["options"]


def test_template_fallback_true_false():
    questions = _template_fallback(
        content="机器学习是AI的核心技术之一。",
        question_types=["true_false"],
        count=1,
        difficulty=2,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "true_false"
    assert questions[0]["options"] == {"T": "正确", "F": "错误"}
    assert questions[0]["correct_answer"] in ("T", "F")


def test_template_fallback_fill_blank():
    questions = _template_fallback(
        content="深度学习使用多层神经网络。",
        question_types=["fill_blank"],
        count=1,
        difficulty=4,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "fill_blank"
    assert questions[0]["options"] is None


def test_template_fallback_short_answer():
    questions = _template_fallback(
        content="自然语言处理是AI的重要应用方向。",
        question_types=["short_answer"],
        count=1,
        difficulty=5,
    )
    assert len(questions) == 1
    assert questions[0]["question_type"] == "short_answer"


def test_build_slot_batch_generator_content_uses_neutral_slot_markers():
    content = question_service._build_slot_batch_generator_content([
        {"slot_index": 1, "generator_content": "【知识单元正文】\n片段一"},
        {"slot_index": 2, "generator_content": "【知识单元正文】\n片段二"},
    ])

    assert "题目槽位" not in content
    assert "参考素材" not in content
    assert "<slot index=\"1\">" in content
    assert "<slot index=\"2\">" in content


def test_build_knowledge_unit_prompt_content_omits_generated_segment_title():
    ku = KnowledgeUnit(
        title="人工智能伦理引论 (杜严勇) - 片段 20",
        summary="解释学科定位的分类差异。",
        keywords=["学科定位", "部门伦理学"],
        content="第一句正文内容。第二句补充证据。第三句延伸讨论。",
    )

    content = question_service._build_knowledge_unit_prompt_content(ku)
    planner_content = question_service._build_knowledge_unit_planner_content(ku)

    assert "【知识单元标题】" not in content
    assert "【知识单元标题】" not in planner_content
    assert "【知识单元摘要】" in content
    assert "【知识关键词】" in planner_content
    assert "【知识单元正文】" not in planner_content
    assert "【核心证据摘录】" in planner_content
    assert "第一句正文内容" in planner_content


def test_build_source_knowledge_unit_excerpt_trims_and_truncates():
    short = question_service._build_source_knowledge_unit_excerpt("  摘要内容  ")
    long = question_service._build_source_knowledge_unit_excerpt("a" * 205)

    assert short == "摘要内容"
    assert long == ("a" * 200) + "..."


def test_template_fallback_mixed_types():
    """Mixed types cycle through the list."""
    questions = _template_fallback(
        content="AI伦理包括公平性、透明性和可解释性。",
        question_types=["single_choice", "true_false", "fill_blank"],
        count=6,
        difficulty=3,
    )
    assert len(questions) == 6
    assert questions[0]["question_type"] == "single_choice"
    assert questions[1]["question_type"] == "true_false"
    assert questions[2]["question_type"] == "fill_blank"
    assert questions[3]["question_type"] == "single_choice"


def test_generate_questions_via_llm_uses_fallback():
    """When LLM API key is not configured, fallback is used."""
    questions = generate_questions_via_llm(
        content="测试内容，用于验证降级机制。",
        question_types=["single_choice"],
        count=2,
        difficulty=3,
    )
    assert len(questions) == 2
    assert questions[0]["question_type"] == "single_choice"


def test_select_generation_units_prefers_high_value_chunks():
    material_id = uuid.uuid4()
    units = [
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="导语",
            content="这是很短的引导语。",
            chunk_index=0,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="核心概念",
            summary="解释隐私最小化与授权范围控制。",
            keywords={"topics": ["隐私最小化", "授权范围", "数据治理"]},
            content="隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。",
            chunk_index=1,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="案例分析",
            summary="分析推荐系统上线前的合规审查步骤。",
            keywords={"topics": ["合规审查", "推荐系统"]},
            content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
            chunk_index=2,
        ),
    ]

    selected = question_service._select_generation_units(units, max_units=2)

    assert {unit.chunk_index for unit in selected} == {1, 2}


def test_select_generation_units_is_deterministic_for_fixed_material():
    material_id = uuid.uuid4()
    duplicate_signature = {
        "title": "核心概念",
        "summary": "解释隐私最小化与授权范围控制。",
        "keywords": {"topics": ["隐私最小化", "授权范围", "数据治理"]},
        "content": "隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。",
    }
    units = [
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="导语",
            content="这是很短的引导语。",
            chunk_index=0,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            chunk_index=1,
            **duplicate_signature,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="案例分析",
            summary="分析推荐系统上线前的合规审查步骤。",
            keywords={"topics": ["合规审查", "推荐系统"]},
            content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
            chunk_index=2,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            chunk_index=3,
            **duplicate_signature,
        ),
    ]

    selections = [
        [
            str(unit.id)
            for unit in question_service._select_generation_units(units, max_units=2)
        ]
        for _ in range(5)
    ]

    assert selections[0] == selections[1] == selections[2] == selections[3] == selections[4]
    assert selections[0] == [str(units[1].id), str(units[2].id)]


def test_select_generation_units_stays_stable_for_each_max_units():
    material_id = uuid.uuid4()
    units = [
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="导语",
            content="这是很短的引导语。",
            chunk_index=0,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="核心概念",
            summary="解释隐私最小化与授权范围控制。",
            keywords={"topics": ["隐私最小化", "授权范围", "数据治理"]},
            content="隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。",
            chunk_index=1,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="案例分析",
            summary="分析推荐系统上线前的合规审查步骤。",
            keywords={"topics": ["合规审查", "推荐系统"]},
            content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
            chunk_index=2,
        ),
    ]

    expected = {
        1: [str(units[1].id)],
        2: [str(units[1].id), str(units[2].id)],
        3: [str(units[0].id), str(units[1].id), str(units[2].id)],
    }

    for max_units, expected_ids in expected.items():
        selections = [
            [str(unit.id) for unit in question_service._select_generation_units(units, max_units=max_units)]
            for _ in range(3)
        ]
        assert selections[0] == selections[1] == selections[2]
        assert selections[0] == expected_ids


def test_select_generation_units_coverage_mode_cools_recent_units():
    material_id = uuid.uuid4()
    units = [
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="片段1",
            summary="解释隐私最小化与用途约束。",
            keywords={"topics": ["隐私最小化", "用途约束", "合规"]},
            content="片段1说明隐私最小化要求只采集必要字段，并且用途必须与授权范围保持一致，防止数据滥用。",
            chunk_index=0,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="片段2",
            summary="解释访问审计与审批控制。",
            keywords={"topics": ["访问审计", "审批控制", "合规"]},
            content="片段2说明访问审计需要记录关键操作日志，并结合审批控制限制高风险数据访问，降低越权使用风险。",
            chunk_index=1,
        ),
        KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="片段3",
            summary="解释上线前的风险评估流程。",
            keywords={"topics": ["风险评估", "上线审查", "治理"]},
            content="片段3说明系统上线前需要完成数据来源核查、字段敏感度评估、脱敏策略确认和回滚预案审查。",
            chunk_index=2,
        ),
    ]

    stable_selected = question_service._select_generation_units(units, max_units=2)
    coverage_selected = question_service._select_generation_units(
        units,
        max_units=2,
        selection_mode="coverage",
        coverage_penalties={
            units[0].id: 2.4,
            units[1].id: 1.2,
        },
    )

    stable_ids = [str(unit.id) for unit in stable_selected]
    coverage_ids = [str(unit.id) for unit in coverage_selected]

    assert stable_ids == [str(units[0].id), str(units[1].id)]
    assert str(units[2].id) in coverage_ids
    assert str(units[0].id) not in coverage_ids


def test_review_preview_calibration_detects_severe_mismatch():
    raw_questions = [
        {
            "question_type": "single_choice",
            "stem": "人工智能的英文缩写是什么？",
            "options": {"A": "AI", "B": "BI", "C": "CI", "D": "DI"},
            "correct_answer": "A",
            "difficulty": 5,
            "bloom_level": "create",
        }
    ]

    summary = question_service._review_preview_calibration(raw_questions)

    assert summary["reviewed_count"] == 1
    assert summary["difficulty_mismatch_count"] == 1
    assert summary["difficulty_severe_mismatch_count"] == 1
    assert summary["bloom_mismatch_count"] == 1
    assert summary["bloom_severe_mismatch_count"] == 1
    assert raw_questions[0]["calibration_review"]["severity"] == "severe"
    assert raw_questions[0]["calibration_review"]["estimated_bloom_level"] == "remember"


@pytest.mark.asyncio
async def test_suggest_question_distribution_expands_effective_max_units():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"suggest_expand_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material = Material(
            id=uuid.uuid4(),
            title="建议扩容素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/suggest-expand.md",
            file_size=256,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        session.add_all(
            [
                KnowledgeUnit(
                    material_id=material.id,
                    title=f"知识点{i}",
                    summary=f"摘要{i}",
                    content=f"知识点{i}详细说明数据治理、权限控制和审计流程，适合独立出题。",
                    chunk_index=i,
                )
                for i in range(6)
            ]
        )
        await session.commit()

        result = await question_service.suggest_question_distribution(
            db=session,
            material_id=material.id,
            max_units=2,
        )

    await engine.dispose()

    assert result["configured_max_units"] == 2
    assert result["effective_max_units"] == 6
    assert result["total_units"] == 6
    assert result["suggested_total"] == 6


# ---- Integration Tests: Question API ----

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
        await conn.execute(text("TRUNCATE TABLE question_generation_prompt_profiles CASCADE"))
        await conn.execute(text("TRUNCATE TABLE questions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE knowledge_units CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
        # Preserve existing users when tests run against a shared local database.
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


@pytest.fixture(autouse=True)
def disable_material_auto_parse(monkeypatch):
    async def _noop_trigger_parse(material_id):
        return None

    monkeypatch.setattr("app.api.v1.endpoints.materials.trigger_parse", _noop_trigger_parse)


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="organizer"):
    unique = uuid.uuid4().hex[:8]
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        user = await create_user(
            session,
            username=f"user_{unique}",
            email=f"{unique}@test.com",
            password="password123",
            role_name=role,
            is_active=True,
        )
        await session.commit()
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.name.value},
        )
    await engine.dispose()
    return token


async def upload_and_parse_material(client, token, title="AI基础教材", filename="ai_basics.md"):
    """Create a parsed material and one knowledge unit directly in the test DB."""
    payload = decode_access_token(token)
    user_id = uuid.UUID(payload["sub"])
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        material = Material(
            title=title,
            format=MaterialFormat.MARKDOWN,
            file_path=f"tests/{filename}",
            file_size=1024,
            status=MaterialStatus.PARSED,
            uploaded_by=user_id,
        )
        session.add(material)
        await session.flush()

        knowledge_unit = KnowledgeUnit(
            material_id=material.id,
            title=f"{title} - 片段 1",
            content="# AI基础认知\n\n人工智能是计算机科学的一个分支。",
            chunk_index=0,
        )
        session.add(knowledge_unit)
        await session.commit()

        material_id = str(material.id)
        knowledge_unit_id = str(knowledge_unit.id)

    await engine.dispose()
    return material_id, knowledge_unit_id


@pytest.mark.asyncio
async def test_prompt_config_defaults_round_trip():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/questions/generation/prompt-config", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_saved_config"] is False
    assert data["system_prompt"] == data["defaults"]["system_prompt"]
    assert data["user_prompt_template"] == data["defaults"]["user_prompt_template"]
    count_placeholder = next(item for item in data["placeholders"] if item["key"] == "{{count}}")
    plan_placeholder = next(item for item in data["placeholders"] if item["key"] == "{{question_plan_section}}")
    assert count_placeholder["source"] == "题型分配合计数量"
    assert plan_placeholder["source"] == "规划阶段抽取的知识点、证据和出题建议"


@pytest.mark.asyncio
async def test_prompt_config_save_and_delete():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        save_resp = await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "自定义系统提示词",
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            },
            headers=headers,
        )
        get_resp = await client.get("/api/v1/questions/generation/prompt-config", headers=headers)
        delete_resp = await client.delete("/api/v1/questions/generation/prompt-config", headers=headers)

    assert save_resp.status_code == 200
    assert get_resp.status_code == 200
    assert delete_resp.status_code == 200
    assert save_resp.json()["has_saved_config"] is True
    assert get_resp.json()["system_prompt"] == "自定义系统提示词"
    assert get_resp.json()["user_prompt_template"] == VALID_TEST_USER_PROMPT_TEMPLATE
    assert delete_resp.json()["has_saved_config"] is False


@pytest.mark.asyncio
async def test_prompt_config_falls_back_when_saved_profile_is_outdated():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        user = await create_user(
            session,
            username=f"prompt_fallback_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            QuestionPromptProfile(
                user_id=user.id,
                system_prompt="过期系统提示词",
                user_prompt_template="题型={{question_types}}\n数量={{count}}\n{{difficulty_section}}\n{{diversity_rules}}\n{{content_section}}",
            )
        )
        await session.commit()

        config = await question_prompt_service.get_effective_prompt_config(
            db=session,
            user_id=user.id,
        )

    await engine.dispose()

    assert config["has_saved_config"] is False
    assert config["user_prompt_template"] == question_prompt_service.get_default_prompt_config()["user_prompt_template"]


@pytest.mark.asyncio
async def test_prompt_config_rejects_unknown_placeholder():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "自定义系统提示词",
                "user_prompt_template": "生成 {{unknown_value}} 道题目",
            },
            headers=headers,
        )

    assert resp.status_code == 422
    assert "未知占位符" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_prompt_config_rejects_missing_required_placeholders():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "自定义系统提示词",
                "user_prompt_template": "生成 {{count}} 道题目",
            },
            headers=headers,
        )

    assert resp.status_code == 422
    assert "缺少必填占位符" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_prompt_preview_renders_free_generation_prompt():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/questions/generation/prompt-preview",
            json={
                "type_distribution": {"single_choice": 2, "true_false": 1},
                "difficulty": 4,
                "bloom_level": "apply",
                "custom_prompt": "侧重工作流自动化",
                "user_prompt_template": (
                    "题型={{question_types}}\n"
                    "数量={{count}}\n"
                    "{{difficulty_section}}\n"
                    "{{bloom_section}}\n"
                    "{{diversity_rules}}\n"
                    "{{question_plan_section}}\n"
                    "{{custom_requirements}}\n"
                    "{{content_section}}"
                ),
                "material_ids": [],
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["prompt_seed"] > 0
    assert data["rendered_user_prompt"] == ""
    assert len(data["rendered_user_prompts"]) == 2
    assert data["rendered_user_prompts"][0]["title"] == "自由出题 / 单选题 / 2 题"
    assert "题型=单选题(single_choice)" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "数量=2" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "侧重工作流自动化" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "【知识点出题规划】" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "【出题范围】" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "按实际调用顺序向模型发送 2 条用户提示词" in data["preview_note"]
    assert any(item["source"] == "额外要求" for item in data["placeholders"])


@pytest.mark.asyncio
async def test_prompt_preview_uses_actual_material_split_for_preview():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        material_id, _ = await upload_and_parse_material(client, token)

        resp = await client.post(
            "/api/v1/questions/generation/prompt-preview",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
                "material_ids": [material_id],
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rendered_user_prompts"]) == 1
    assert "【知识点出题规划】" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "【参考素材】" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "人工智能是计算机科学的一个分支" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "先生成知识点规划" in data["preview_note"]
    assert "按实际调用顺序向模型发送 1 条用户提示词" in data["preview_note"]
    assert "若目标题量超过该值，系统会自动扩展候选片段" in data["preview_note"]


@pytest.mark.asyncio
async def test_prompt_preview_multi_material_uses_total_distribution_once():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"prompt_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material_a = Material(
            id=uuid.uuid4(),
            title="素材A",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/a.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        material_b = Material(
            id=uuid.uuid4(),
            title="素材B",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/b.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add_all([material_a, material_b])
        session.add_all([
            KnowledgeUnit(
                material_id=material_a.id,
                title="素材A核心片段",
                summary="A的核心知识",
                content="素材A介绍了模型评估与审计流程。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material_b.id,
                title="素材B核心片段",
                summary="B的核心知识",
                content="素材B介绍了隐私最小化和授权范围控制。",
                chunk_index=0,
            ),
        ])
        await session.commit()

        preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            type_distribution={"single_choice": 1},
            difficulty=3,
            user_prompt_template=VALID_TEST_USER_PROMPT_TEMPLATE,
            material_ids=[material_a.id, material_b.id],
            max_units=5,
            prompt_seed=42,
        )

    await engine.dispose()

    assert len(preview["rendered_user_prompts"]) == 1


@pytest.mark.asyncio
async def test_prompt_preview_fails_when_unique_units_are_insufficient():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"prompt_capacity_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material = Material(
            id=uuid.uuid4(),
            title="Prompt容量测试素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/prompt-capacity.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        session.add_all(
            [
                KnowledgeUnit(
                    material_id=material.id,
                    title="知识点A",
                    summary="A摘要",
                    content="知识点A说明奖励建模和偏好优化流程。",
                    chunk_index=0,
                ),
                KnowledgeUnit(
                    material_id=material.id,
                    title="知识点B",
                    summary="B摘要",
                    content="知识点B说明混合加密与密钥分发策略。",
                    chunk_index=1,
                ),
            ]
        )
        await session.commit()

        with pytest.raises(ValueError, match="当前素材去重后仅有 2 个可用知识点，不足以生成 3 道互不重复知识点的题目"):
            await question_prompt_service.render_generation_prompt_preview(
                db=session,
                user_id=uploader.id,
                type_distribution={"single_choice": 2, "true_false": 1},
                difficulty=3,
                material_ids=[material.id],
                max_units=1,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_preview_seed_can_be_reused_for_stable_rendering():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        first_resp = await client.post(
            "/api/v1/questions/generation/prompt-preview",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            },
            headers=headers,
        )
        seed = first_resp.json()["prompt_seed"]
        second_resp = await client.post(
            "/api/v1/questions/generation/prompt-preview",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
                "prompt_seed": seed,
            },
            headers=headers,
        )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    assert first_resp.json()["rendered_user_prompts"] == second_resp.json()["rendered_user_prompts"]


@pytest.mark.asyncio
async def test_material_prompt_preview_selects_same_units_for_fixed_conditions():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"stable_material_{uuid.uuid4().hex[:8]}",
            email=f"stable_material_{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material = Material(
            title="稳定选片素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/stable.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        await session.flush()
        session.add_all([
            KnowledgeUnit(
                material_id=material.id,
                title="导语",
                content="这是很短的导语。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="核心概念",
                summary="解释隐私最小化与授权范围控制。",
                keywords={"topics": ["隐私最小化", "授权范围", "数据治理"]},
                content="隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="案例分析",
                summary="分析推荐系统上线前的合规审查步骤。",
                keywords={"topics": ["合规审查", "推荐系统"]},
                content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
                chunk_index=2,
            ),
        ])
        await session.commit()

        common_payload = {
            "type_distribution": {"single_choice": 2, "true_false": 1},
            "difficulty": 3,
            "bloom_level": "apply",
            "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            "material_ids": [material.id],
            "max_units": 2,
            "prompt_seed": 20260323,
        }
        first_preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            **common_payload,
        )
        second_preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            **common_payload,
        )

    await engine.dispose()

    assert first_preview["rendered_user_prompts"] == second_preview["rendered_user_prompts"]
    joined = "\n".join(item["rendered_user_prompt"] for item in first_preview["rendered_user_prompts"])
    assert "核心概念" in joined
    assert "案例分析" in joined
    assert "【知识点出题规划】" in joined


@pytest.mark.asyncio
async def test_multi_material_prompt_preview_is_stable_for_fixed_conditions():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"stable_multi_{uuid.uuid4().hex[:8]}",
            email=f"stable_multi_{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material_a = Material(
            title="稳定素材A",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/stable-a.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        material_b = Material(
            title="稳定素材B",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/stable-b.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add_all([material_a, material_b])
        await session.flush()
        session.add_all([
            KnowledgeUnit(
                material_id=material_a.id,
                title="A导语",
                content="这是很短的导语。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material_a.id,
                title="A核心概念",
                summary="解释A中的隐私最小化要求。",
                keywords={"topics": ["隐私最小化", "数据治理"]},
                content="素材A介绍隐私最小化、授权边界与审计要求，强调字段裁剪和用途一致性。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material_a.id,
                title="A案例分析",
                summary="分析A中的上线审查流程。",
                keywords={"topics": ["上线审查", "访问审计"]},
                content="素材A分析推荐系统上线前的数据来源核查、脱敏策略、访问审计与审批流程。",
                chunk_index=2,
            ),
            KnowledgeUnit(
                material_id=material_b.id,
                title="B导语",
                content="这是很短的导语。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material_b.id,
                title="B核心概念",
                summary="解释B中的模型评估与风险控制。",
                keywords={"topics": ["模型评估", "风险控制"]},
                content="素材B介绍模型评估指标、错误分析、上线阈值设定和风控补救措施。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material_b.id,
                title="B案例分析",
                summary="分析B中的偏差排查流程。",
                keywords={"topics": ["偏差排查", "监控告警"]},
                content="素材B分析模型偏差排查、线上监控告警、人工复核与回滚流程。",
                chunk_index=2,
            ),
        ])
        await session.commit()

        payload = {
            "type_distribution": {"single_choice": 3, "true_false": 1},
            "difficulty": 3,
            "bloom_level": "apply",
            "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            "material_ids": [material_a.id, material_b.id],
            "max_units": 2,
            "prompt_seed": 20260323,
        }
        first_preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            **payload,
        )
        second_preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            **payload,
        )

    await engine.dispose()

    assert first_preview["rendered_user_prompts"] == second_preview["rendered_user_prompts"]
    joined = "\n".join(item["rendered_user_prompt"] for item in first_preview["rendered_user_prompts"])
    assert "A核心概念" in joined or "A案例分析" in joined
    assert "B核心概念" in joined or "B案例分析" in joined
    assert "【知识点出题规划】" in joined


@pytest.mark.asyncio
async def test_preview_question_bank_records_history_and_coverage_rotates_units(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    def fake_generate(*args, **kwargs):
        content = kwargs.get("content", "")
        count = kwargs.get("count", 1)
        label = "未知片段"
        stem_templates = [
            "{label} 中最关键的合规控制是什么？",
            "如果围绕 {label} 设计一道实践题，最应强调哪项措施？",
            "下列哪项最符合 {label} 对应的治理要求？",
        ]
        for candidate in ("片段1", "片段2", "片段3"):
            if candidate in content:
                label = candidate
                break
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                        "stem": stem_templates[index % len(stem_templates)].format(label=label),
                    "options": {"A": "正确", "B": "错误", "C": "干扰项1", "D": "干扰项2"},
                    "correct_answer": "A",
                    "explanation": f"{label} 的解释。",
                    "knowledge_tags": [label],
                    "dimension": "AI伦理安全",
                }
                for index in range(count)
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {"stem_clarity": 4},
        "overall_score": 4.4,
        "recommendation": "approve",
        "comments": "质量良好",
    })
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": True,
        "reasons": [],
    })
    monkeypatch.setattr(question_service, "_collect_near_duplicate_pairs", lambda *args, **kwargs: [])
    monkeypatch.setattr(question_service, "_review_preview_questions", lambda *args, **kwargs: {
        "reviewed_count": 0,
        "warnings": [],
        "blocked_items": [],
    })

    async def no_duplicates(*args, **kwargs):
        return []

    monkeypatch.setattr(question_service, "_collect_existing_duplicate_stems", no_duplicates)
    monkeypatch.setattr(question_service, "_collect_existing_near_duplicate_pairs", no_duplicates)

    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"coverage_rotation_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material = Material(
            title="覆盖优先轮换素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/coverage-rotation.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        await session.flush()
        session.add_all([
            KnowledgeUnit(
                material_id=material.id,
                title="片段1",
                summary="解释片段1中的数据最小化原则。",
                keywords={"topics": ["最小化", "字段裁剪", "授权范围"]},
                content="片段1说明数据最小化要求围绕必要字段裁剪和授权范围控制，避免过度采集与越界使用。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="片段2",
                summary="解释片段2中的访问审计要求。",
                keywords={"topics": ["访问审计", "审批控制", "日志追踪"]},
                content="片段2说明访问审计需要记录关键日志，并在高风险访问前引入审批控制与追踪复核。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="片段3",
                summary="解释片段3中的上线前风险评估。",
                keywords={"topics": ["风险评估", "上线审查", "回滚预案"]},
                content="片段3说明系统上线前需要完成风险评估、字段敏感度分级、回滚预案与应急演练。",
                chunk_index=2,
            ),
        ])
        await session.commit()

        first_preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material.id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            max_units=2,
            selection_mode="stable",
            created_by=uploader.id,
        )
        second_preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material.id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            max_units=2,
            selection_mode="coverage",
            created_by=uploader.id,
        )

        run_result = await session.execute(
            select(MaterialGenerationRun)
            .where(MaterialGenerationRun.material_id == material.id)
            .order_by(MaterialGenerationRun.created_at)
        )
        runs = list(run_result.scalars().all())
        run_unit_result = await session.execute(
            select(MaterialGenerationRunUnit).where(
                MaterialGenerationRunUnit.run_id.in_([run.id for run in runs])
            )
        )
        run_units = list(run_unit_result.scalars().all())

    await engine.dispose()

    first_titles = {item["source_knowledge_unit_title"] for item in first_preview["questions"]}
    second_titles = {item["source_knowledge_unit_title"] for item in second_preview["questions"]}

    assert first_titles == {"片段1", "片段2"}
    assert "片段3" in second_titles
    assert second_titles != first_titles
    assert len(runs) == 2
    assert runs[0].selection_mode == "stable"
    assert runs[1].selection_mode == "coverage"
    assert len(run_units) == 4


@pytest.mark.asyncio
async def test_preview_question_bank_records_history_when_quality_gate_warns(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "根据素材，作者在第1章最强调的观点是什么？",
                "options": {"A": "观点A", "B": "观点B", "C": "观点C", "D": "观点D"},
                "correct_answer": "A",
                "explanation": "根据素材可知答案为A。",
                "knowledge_tags": ["章节信息"],
                "dimension": "AI基础知识",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })

    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"coverage_blocked_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material = Material(
            title="覆盖优先阻断素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/coverage-blocked.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        await session.flush()
        session.add(
            KnowledgeUnit(
                material_id=material.id,
                title="片段1",
                content="素材正文内容。",
                chunk_index=0,
            )
        )
        await session.commit()

        preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material.id,
            type_distribution={"single_choice": 1},
            difficulty=3,
            selection_mode="coverage",
            created_by=uploader.id,
        )

        run_count = await session.scalar(
            select(func.count()).select_from(MaterialGenerationRun).where(
                MaterialGenerationRun.material_id == material.id
            )
        )

    await engine.dispose()

    assert preview["stats"]["save_blocked"] is False
    assert preview["stats"]["quality_gate_failed"] is True
    assert run_count == 1


@pytest.mark.asyncio
async def test_preview_question_bank_skips_history_when_disabled(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "上线前哪项做法最能降低隐私风险？",
                "options": {"A": "先做脱敏", "B": "扩大采集", "C": "跳过评估", "D": "关闭审计"},
                "correct_answer": "A",
                "explanation": "脱敏可以降低敏感信息误用风险。",
                "knowledge_tags": ["脱敏"],
                "dimension": "AI伦理安全",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": True,
        "reasons": [],
    })

    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"preview_no_history_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material = Material(
            title="仅导出不记历史素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/no-history.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        await session.flush()
        session.add(
            KnowledgeUnit(
                material_id=material.id,
                title="片段1",
                content="上线前需要完成数据脱敏和风险评估。",
                chunk_index=0,
                dimension="AI伦理安全",
            )
        )
        await session.commit()

        preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material.id,
            type_distribution={"single_choice": 1},
            difficulty=3,
            created_by=uploader.id,
            record_generation_run=False,
        )

        run_count = await session.scalar(
            select(func.count()).select_from(MaterialGenerationRun).where(
                MaterialGenerationRun.material_id == material.id
            )
        )

    await engine.dispose()

    assert len(preview["questions"]) == 1
    assert run_count == 0


@pytest.mark.asyncio
async def test_prompt_preview_coverage_mode_matches_preview_selection(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    def fake_generate(*args, **kwargs):
        content = kwargs.get("content", "")
        labels = []
        for chunk in re.findall(r"<slot index=\"\\d+\">\\n(.*?)\\n</slot>", content, re.S):
            label = "未知片段"
            for candidate in ("片段1", "片段2", "片段3"):
                if candidate in chunk:
                    label = candidate
                    break
            labels.append(label)
        if not labels:
            labels = ["未知片段"] * max(1, int(kwargs.get("count", 1) or 1))
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": f"{label} 覆盖测试题",
                    "options": {"A": "正确", "B": "错误", "C": "干扰项1", "D": "干扰项2"},
                    "correct_answer": "A",
                    "explanation": f"{label} 的解释。",
                    "knowledge_tags": [label],
                    "dimension": "AI伦理安全",
                }
                for label in labels
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {"stem_clarity": 4},
        "overall_score": 4.4,
        "recommendation": "approve",
        "comments": "质量良好",
    })
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": True,
        "reasons": [],
    })

    async with session_factory() as session:
        await init_roles(session)
        uploader = await create_user(
            session,
            username=f"coverage_prompt_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password="password123",
            role_name="organizer",
            is_active=True,
        )
        material = Material(
            title="覆盖优先提示词素材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/coverage-prompt.md",
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        await session.flush()
        units = [
            KnowledgeUnit(
                material_id=material.id,
                title="片段1",
                summary="解释片段1中的数据最小化原则。",
                keywords={"topics": ["最小化", "字段裁剪", "授权范围"]},
                content="片段1说明数据最小化要求围绕必要字段裁剪和授权范围控制，避免过度采集与越界使用。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="片段2",
                summary="解释片段2中的访问审计要求。",
                keywords={"topics": ["访问审计", "审批控制", "日志追踪"]},
                content="片段2说明访问审计需要记录关键日志，并在高风险访问前引入审批控制与追踪复核。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material.id,
                title="片段3",
                summary="解释片段3中的上线前风险评估。",
                keywords={"topics": ["风险评估", "上线审查", "回滚预案"]},
                content="片段3说明系统上线前需要完成风险评估、字段敏感度分级、回滚预案与应急演练。",
                chunk_index=2,
            ),
        ]
        session.add_all(units)
        await session.commit()

        await question_service._record_material_generation_run(
            db=session,
            material_id=material.id,
            knowledge_unit_ids=[units[0].id, units[1].id],
            selection_mode="stable",
            created_by=uploader.id,
        )
        await session.commit()

        prompt_preview = await question_prompt_service.render_generation_prompt_preview(
            db=session,
            user_id=uploader.id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            user_prompt_template=VALID_TEST_USER_PROMPT_TEMPLATE,
            material_ids=[material.id],
            max_units=2,
            selection_mode="coverage",
            prompt_seed=42,
        )
        preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material.id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            max_units=2,
            selection_mode="coverage",
            created_by=uploader.id,
        )

    await engine.dispose()

    joined_prompt = "\n".join(item["rendered_user_prompt"] for item in prompt_preview["rendered_user_prompts"])
    preview_titles = {item["source_knowledge_unit_title"] for item in preview["questions"]}

    assert "片段3" in joined_prompt
    assert "片段3" in preview_titles
    assert any(title in joined_prompt for title in preview_titles)


@pytest.mark.asyncio
async def test_preview_free_uses_saved_prompt_config(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured["system_prompt"] = kwargs.get("system_prompt")
        captured["user_prompt_template"] = kwargs.get("user_prompt_template")
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "测试题目",
                    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                    "correct_answer": "A",
                    "explanation": "解释",
                    "knowledge_tags": ["标签"],
                    "dimension": "AI基础知识",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "保存的系统提示词",
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            },
            headers=headers,
        )

        resp = await client.post(
            "/api/v1/questions/preview/free",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert captured["system_prompt"] == "保存的系统提示词"
    assert captured["user_prompt_template"] == VALID_TEST_USER_PROMPT_TEMPLATE


@pytest.mark.asyncio
async def test_preview_free_request_prompt_overrides_saved_defaults(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured["system_prompt"] = kwargs.get("system_prompt")
        captured["user_prompt_template"] = kwargs.get("user_prompt_template")
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "测试题目",
                    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                    "correct_answer": "A",
                    "explanation": "解释",
                    "knowledge_tags": ["标签"],
                    "dimension": "AI基础知识",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "保存的系统提示词",
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            },
            headers=headers,
        )

        resp = await client.post(
            "/api/v1/questions/preview/free",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "system_prompt": "本次系统提示词",
                "user_prompt_template": VALID_TEST_USER_PROMPT_TEMPLATE,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert captured["system_prompt"] == "本次系统提示词"
    assert captured["user_prompt_template"] == VALID_TEST_USER_PROMPT_TEMPLATE


@pytest.mark.asyncio
async def test_preview_questions_free_runs_type_batches_concurrently(monkeypatch):
    state = {
        "active": 0,
        "max_active": 0,
    }
    lock = threading.Lock()

    def fake_generate(**kwargs):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            time.sleep(0.12)
            qtype = kwargs["question_types"][0]
            return {
                "questions": [
                    {
                        "question_type": qtype,
                        "stem": f"{qtype} 并发测试题",
                        "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"} if qtype != "true_false" else {"T": "正确", "F": "错误"},
                        "correct_answer": "T" if qtype == "true_false" else "A",
                        "explanation": "并发测试",
                        "knowledge_tags": [qtype],
                        "dimension": "AI基础知识",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "fallback_used": False,
                "error": None,
            }
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    result = await question_service.preview_questions_free(
        type_distribution={"single_choice": 1, "true_false": 1},
        difficulty=3,
    )

    assert len(result["questions"]) == 2
    assert state["max_active"] >= 2


# ---- CRUD Tests ----

@pytest.mark.asyncio
async def test_create_question():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/questions",
            json={
                "question_type": "single_choice",
                "stem": "人工智能的英文缩写是？",
                "options": {"A": "AI", "B": "BI", "C": "CI", "D": "DI"},
                "correct_answer": "A",
                "explanation": "AI = Artificial Intelligence",
                "difficulty": 1,
                "dimension": "AI基础认知",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stem"] == "人工智能的英文缩写是？"
    assert data["status"] == "draft"
    assert data["difficulty"] == 1


@pytest.mark.asyncio
async def test_list_questions_empty():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/questions",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_questions_with_filter():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two questions with different types
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "单选题1",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "difficulty": 2,
        }, headers=headers)

        await client.post("/api/v1/questions", json={
            "question_type": "true_false",
            "stem": "判断题1",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错误"},
            "difficulty": 3,
        }, headers=headers)

        # Filter by type
        resp = await client.get(
            "/api/v1/questions?question_type=single_choice",
            headers=headers,
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["question_type"] == "single_choice"

        # Filter by keyword
        resp = await client.get(
            "/api/v1/questions?keyword=判断",
            headers=headers,
        )
        assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_questions_includes_source_titles():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, ku_id = await upload_and_parse_material(client, token)
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers=headers,
        )
        ku_title = ku_resp.json()["units"][0]["title"]

        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "来源题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "source_material_id": mid,
            "source_knowledge_unit_id": ku_id,
        }, headers=headers)
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "自由题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers=headers)

        resp = await client.get("/api/v1/questions", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    source_item = next(item for item in data["items"] if item["stem"] == "来源题目")
    free_item = next(item for item in data["items"] if item["stem"] == "自由题目")
    assert source_item["source_material_title"] == "AI基础教材"
    assert source_item["source_knowledge_unit_title"] == ku_title
    assert free_item["source_material_title"] is None
    assert free_item["source_knowledge_unit_title"] is None


@pytest.mark.asyncio
async def test_list_questions_filters_by_source_material():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(decode_access_token(token)["sub"])

        mid1, ku_id1 = await upload_and_parse_material(client, token, title="筛选素材一", filename="material_one.md")
        mid2, ku_id2 = await upload_and_parse_material(client, token, title="筛选素材二", filename="material_two.md")

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            session.add_all([
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="素材一题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    source_material_id=uuid.UUID(mid1),
                    source_knowledge_unit_id=uuid.UUID(ku_id1),
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="素材二题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    source_material_id=uuid.UUID(mid2),
                    source_knowledge_unit_id=uuid.UUID(ku_id2),
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="自由题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
            ])
            await session.commit()
        await engine.dispose()

        resp = await client.get(
            f"/api/v1/questions?source_material_id={mid1}",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["stem"] == "素材一题目"
    assert data["items"][0]["source_material_id"] == mid1


@pytest.mark.asyncio
async def test_preview_bank_retries_invalid_material_question_set(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    responses = [
        {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "根据本文，一位产品经理首先应该完成哪一步？",
                    "options": {"A": "识别敏感字段", "B": "跳过清洗", "C": "直接上线", "D": "共享原始数据"},
                    "correct_answer": "A",
                    "explanation": "应先识别敏感字段。",
                    "knowledge_tags": ["隐私脱敏"],
                    "dimension": "AI伦理安全",
                },
                {
                    "question_type": "single_choice",
                    "stem": "一位产品经理在上线推荐服务前，首要的合规动作是什么？",
                    "options": {"A": "评估用途与授权范围", "B": "扩大数据采集", "C": "忽略用户同意", "D": "删除审计日志"},
                    "correct_answer": "A",
                    "explanation": "应先评估用途与授权范围。",
                    "knowledge_tags": ["隐私脱敏"],
                    "dimension": "AI伦理安全",
                },
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "model_name": "fake-model",
            "provider": "fake",
            "fallback_used": False,
            "error": None,
        },
        {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "推荐系统上线前，哪项做法最能降低个人信息误用风险？",
                    "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期留存原始数据", "D": "取消访问审计"},
                    "correct_answer": "A",
                    "explanation": "只保留必要字段符合最小化原则。",
                    "knowledge_tags": ["数据最小化"],
                    "dimension": "AI伦理安全",
                },
                {
                    "question_type": "single_choice",
                    "stem": "一位数据分析师在训练推荐模型前，最应优先核查哪项内容？",
                    "options": {"A": "字段用途与授权范围是否一致", "B": "是否收集更多敏感数据", "C": "是否跳过样本清洗", "D": "是否关闭审计日志"},
                    "correct_answer": "A",
                    "explanation": "先核查用途与授权范围，才能判断数据是否可用。",
                    "knowledge_tags": ["授权范围"],
                    "dimension": "AI伦理安全",
                },
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 21, "total_tokens": 32},
            "model_name": "fake-model",
            "provider": "fake",
            "fallback_used": False,
            "error": None,
        },
    ]
    call_count = {"value": 0}

    def fake_generate(*args, **kwargs):
        index = call_count["value"]
        call_count["value"] += 1
        return responses[min(index, len(responses) - 1)]

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"material_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material = Material(
            id=material_id,
            title="AI基础教材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/test.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="大模型应用需要完成隐私脱敏和合规审查。",
                chunk_index=0,
                dimension="AI伦理安全",
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            custom_prompt="侧重隐私合规",
        )

    await engine.dispose()

    assert call_count["value"] == 2
    assert len(result["questions"]) == 2
    assert result["questions"][0]["stem"] == "推荐系统上线前，哪项做法最能降低个人信息误用风险？"


@pytest.mark.asyncio
async def test_preview_question_bank_includes_source_titles(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    def fake_generate(*args, **kwargs):
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "预览来源题目",
                    "options": {"A": "正确", "B": "错误"},
                    "correct_answer": "A",
                    "explanation": "测试预览来源标题",
                    "knowledge_tags": ["来源测试"],
                    "dimension": "AI基础知识",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"preview_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material = Material(
            id=material_id,
            title="AI基础教材",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/test.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        session.add(material)
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="AI基础教材 - 片段 1",
                content="知识单元内容",
                chunk_index=0,
                dimension="AI基础知识",
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
        )

    await engine.dispose()

    assert len(result["questions"]) == 1
    assert result["questions"][0]["source_material_title"] == "AI基础教材"
    assert result["questions"][0]["source_knowledge_unit_title"] == "AI基础教材 - 片段 1"


@pytest.mark.asyncio
async def test_preview_question_bank_reuses_batch_planner_and_only_retries_failed_slots(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()
    planner_calls = {"count": 0}
    injected_plans: list[list[dict] | None] = []
    generator_calls: list[dict] = []
    attempt_state = {"single_choice": 0, "true_false": 0}

    def fake_batch_planner(**kwargs):
        planner_calls["count"] += 1
        slot_requests = kwargs.get("slot_requests", [])
        return {
            "question_plan": [
                {
                    "knowledge_point": f"规划知识点{slot['slot_index']}",
                    "evidence": f"证据{slot['slot_index']}",
                    "question_type": slot["question_type"],
                    "stem_style": "直接知识型",
                    "scenario": "课堂学习场景",
                    "answer_focus": f"答案聚焦{slot['slot_index']}",
                    "distractor_focus": f"干扰项{slot['slot_index']}",
                    "knowledge_tags": [f"标签{slot['slot_index']}"],
                    "dimension": "AI基础知识",
                }
                for slot in slot_requests
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "fallback_used": False,
            "error": None,
        }

    def fake_generate_questions_via_llm(**kwargs):
        question_plan = kwargs.get("question_plan")
        injected_plans.append(question_plan)
        question_type = kwargs["question_types"][0]
        count = kwargs["count"]
        attempt_state[question_type] += 1
        generator_calls.append({
            "question_type": question_type,
            "count": count,
            "question_plan": question_plan,
        })

        questions = []
        effective_count = count
        if question_type == "single_choice" and attempt_state[question_type] == 1:
            effective_count = 1

        for index in range(effective_count):
            plan_item = (question_plan or [{}])[index] if question_plan and index < len(question_plan) else {}
            if question_type == "true_false":
                questions.append(
                    {
                        "question_type": "true_false",
                        "stem": f"{plan_item.get('knowledge_point', '默认知识点')} 是正确的表述。",
                        "options": {"A": "正确", "B": "错误"},
                        "correct_answer": "A",
                        "explanation": "测试整批 planner 注入。",
                        "knowledge_tags": plan_item.get("knowledge_tags", [f"默认标签{index + 1}"]),
                        "dimension": plan_item.get("dimension", "AI基础知识"),
                    }
                )
                continue
            questions.append(
                {
                    "question_type": question_type,
                    "stem": f"{plan_item.get('knowledge_point', '默认知识点')} 对应的测试题目是什么？",
                    "options": {"A": "方案A", "B": "方案B", "C": "方案C", "D": "方案D"},
                    "correct_answer": "A",
                    "explanation": "测试整批 planner 注入。",
                    "knowledge_tags": plan_item.get("knowledge_tags", [f"默认标签{index + 1}"]),
                    "dimension": plan_item.get("dimension", "AI基础知识"),
                }
            )
        return {
            "questions": questions,
            "usage": {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17},
            "fallback_used": False,
            "error": None if effective_count == count else "Only 1/2 questions passed validation",
        }

    monkeypatch.setattr(question_service, "generate_question_plan_batch_via_llm", fake_batch_planner)
    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate_questions_via_llm)
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": True,
        "reasons": [],
    })
    monkeypatch.setattr(question_service, "_collect_near_duplicate_pairs", lambda *args, **kwargs: [])

    async def empty_existing_duplicates(*args, **kwargs):
        return []

    monkeypatch.setattr(question_service, "_collect_existing_duplicate_stems", empty_existing_duplicates)
    monkeypatch.setattr(question_service, "_collect_existing_near_duplicate_pairs", empty_existing_duplicates)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"batch_plan_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="整批规划素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add_all([
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="片段1内容，说明数据脱敏。",
                chunk_index=0,
            ),
            KnowledgeUnit(
                material_id=material_id,
                title="片段2",
                content="片段2内容，说明访问审计。",
                chunk_index=1,
            ),
            KnowledgeUnit(
                material_id=material_id,
                title="片段3",
                content="片段3内容，说明风险评估。",
                chunk_index=2,
            ),
        ])
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 2, "true_false": 1},
            difficulty=3,
            max_units=3,
        )

    await engine.dispose()

    assert planner_calls["count"] == 1
    assert len(result["questions"]) == 3
    assert len(injected_plans) == 3
    assert len(generator_calls) == 3
    assert generator_calls[0]["question_type"] == "single_choice"
    assert generator_calls[0]["count"] == 2
    assert len(generator_calls[0]["question_plan"]) == 2
    assert generator_calls[1]["question_type"] == "true_false"
    assert generator_calls[1]["count"] == 1
    assert len(generator_calls[1]["question_plan"]) == 1
    assert generator_calls[2]["question_type"] == "single_choice"
    assert generator_calls[2]["count"] == 1
    assert len(generator_calls[2]["question_plan"]) == 1
    assert injected_plans[0][0]["knowledge_point"] == "规划知识点1"
    assert injected_plans[0][1]["knowledge_point"] == "规划知识点2"
    assert injected_plans[1][0]["knowledge_point"] == "规划知识点3"
    assert injected_plans[2][0]["knowledge_point"] == "规划知识点2"
    assert result["stats"]["generation_attempts"] == 2
    assert result["stats"]["prompt_tokens"] == 5 + 11 * 3
    assert result["stats"]["total_tokens"] == 8 + 17 * 3
    assert result["stats"]["timings"]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_preview_question_bank_does_not_retry_for_warning_only_risks(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()
    planner_calls = {"count": 0}
    generator_calls = {"count": 0}

    def fake_batch_planner(**kwargs):
        planner_calls["count"] += 1
        slot_requests = kwargs.get("slot_requests", [])
        return {
            "question_plan": [
                {
                    "knowledge_point": f"规划知识点{slot['slot_index']}",
                    "evidence": f"证据{slot['slot_index']}",
                    "question_type": slot["question_type"],
                    "stem_style": "直接知识型",
                    "scenario": "",
                    "answer_focus": f"答案聚焦{slot['slot_index']}",
                    "distractor_focus": f"干扰项{slot['slot_index']}",
                    "knowledge_tags": [f"标签{slot['slot_index']}"],
                    "dimension": "AI基础知识",
                }
                for slot in slot_requests
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    def fake_generate_questions_via_llm(**kwargs):
        generator_calls["count"] += 1
        qtype = kwargs["question_types"][0]
        count = kwargs["count"]
        questions = []
        for index in range(count):
            questions.append(
                {
                    "question_type": qtype,
                    "stem": f"第{index + 1}题测试题干",
                    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"} if qtype != "true_false" else {"T": "正确", "F": "错误"},
                    "correct_answer": "T" if qtype == "true_false" else "A",
                    "explanation": "解释",
                    "knowledge_tags": [f"标签{index + 1}"],
                    "dimension": "AI基础知识",
                }
            )
        return {
            "questions": questions,
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            "fallback_used": True,
            "error": "warning only",
        }

    monkeypatch.setattr(question_service, "generate_question_plan_batch_via_llm", fake_batch_planner)
    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate_questions_via_llm)
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": False,
        "reasons": ["批次级提示"],
    })
    monkeypatch.setattr(question_service, "_collect_near_duplicate_pairs", lambda *args, **kwargs: [])

    async def empty_existing_duplicates(*args, **kwargs):
        return []

    monkeypatch.setattr(question_service, "_collect_existing_duplicate_stems", empty_existing_duplicates)
    monkeypatch.setattr(question_service, "_collect_existing_near_duplicate_pairs", empty_existing_duplicates)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"warning_only_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="warning only 素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add_all([
            KnowledgeUnit(material_id=material_id, title="片段1", content="片段1", chunk_index=0),
            KnowledgeUnit(material_id=material_id, title="片段2", content="片段2", chunk_index=1),
        ])
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 2},
            difficulty=3,
            max_units=2,
        )

    await engine.dispose()

    assert planner_calls["count"] == 1
    assert generator_calls["count"] == 1
    assert result["stats"]["generation_attempts"] == 1
    assert result["stats"]["generated_total"] == 2
    assert result["stats"]["quality_gate_failed"] is True
    assert "批次级提示" in result["stats"]["validation_reasons"]


@pytest.mark.asyncio
async def test_preview_question_bank_skips_ai_review_batching(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "预览异步质检测试题",
                "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                "correct_answer": "A",
                "explanation": "测试异步质检回填。",
                "knowledge_tags": ["异步质检"],
                "dimension": "AI基础知识",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })
    monkeypatch.setattr(question_service, "_validate_generated_question_set", lambda *args, **kwargs: {
        "passed": True,
        "reasons": [],
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"preview_async_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="异步质检素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="素材正文内容",
                chunk_index=0,
            )
        )
        await session.commit()

        preview = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
        )

    await engine.dispose()

    assert preview.get("preview_batch_id") is None
    assert preview["stats"]["quality_review_count"] == 0
    assert preview["stats"]["ai_review_pending"] is False
    assert preview["stats"]["ai_review_completed"] is False
    assert preview["questions"][0].get("quality_review") is None


@pytest.mark.asyncio
async def test_preview_batch_review_endpoint_is_unavailable():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get(
            f"/api/v1/questions/preview/batch/{uuid.uuid4()}",
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_preview_question_bank_does_not_run_ai_review(monkeypatch):
    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只收集必要字段", "B": "长期保留原始日志", "C": "默认开放所有画像", "D": "对外共享用户ID"},
                "correct_answer": "A",
                "explanation": "最小化原则要求只收集实现目标所必需的数据。",
                "difficulty": 3,
                "dimension": "AI基础知识",
                "knowledge_tags": ["隐私最小化"],
                "bloom_level": "understand",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {"stem_clarity": 1},
        "overall_score": 1.2,
        "recommendation": "reject",
        "comments": "这条审核结果不应出现在 preview 中",
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"preview_no_ai_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="AI质检素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="推荐系统上线前，需要落实隐私最小化原则。",
                chunk_index=0,
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
        )

    await engine.dispose()

    assert result.get("preview_batch_id") is None
    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["quality_gate_failed"] is False
    assert result["stats"]["quality_review_blocked"] == 0
    assert result["stats"]["quality_review_count"] == 0
    assert result["stats"]["ai_review_pending"] is False
    assert result["questions"][0].get("quality_review") is None


@pytest.mark.asyncio
async def test_preview_question_bank_reports_quality_gate_warning(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    def fake_generate(*args, **kwargs):
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "根据材料，作者在第1章最强调的观点是什么？",
                    "options": {"A": "观点A", "B": "观点B", "C": "观点C", "D": "观点D"},
                    "correct_answer": "A",
                    "explanation": "根据材料可知答案为A。",
                    "knowledge_tags": ["章节信息"],
                    "dimension": "AI基础知识",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"gate_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="AI基础教材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="素材正文内容",
                chunk_index=0,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段2",
                content="另一段素材正文内容",
                chunk_index=1,
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
            max_units=1,
        )

    await engine.dispose()

    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["quality_gate_failed"] is True
    assert result["stats"]["configured_max_units"] == 1
    assert result["stats"]["effective_max_units"] == 1
    assert result["stats"]["selected_unit_count"] == 1
    assert any("素材元信息" in item for item in result["stats"]["validation_reasons"])


@pytest.mark.asyncio
async def test_preview_question_bank_blocks_near_duplicate_questions(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {},
        "overall_score": 4.2,
        "recommendation": "approve",
        "comments": "质量良好",
    })
    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                "correct_answer": "A",
                "explanation": "只保留必要字段符合最小化原则。",
                "knowledge_tags": ["隐私最小化", "推荐系统"],
                "dimension": "AI伦理安全",
            },
            {
                "question_type": "single_choice",
                "stem": "推荐系统上线之前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                "correct_answer": "A",
                "explanation": "只保留必要字段符合最小化原则。",
                "knowledge_tags": ["隐私最小化", "推荐系统"],
                "dimension": "AI伦理安全",
            },
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"near_dup_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="近重复检测素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="推荐系统上线前，需要落实隐私最小化原则。",
                chunk_index=0,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段2",
                content="推荐系统部署前，需要确保数据采集符合最小必要原则。",
                chunk_index=1,
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 2},
            difficulty=3,
        )

    await engine.dispose()

    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["quality_gate_failed"] is True
    assert result["stats"]["near_duplicate_count"] > 0
    assert any("近重复" in item for item in result["stats"]["warnings"])


@pytest.mark.asyncio
async def test_preview_question_bank_blocks_existing_near_duplicate(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {},
        "overall_score": 4.2,
        "recommendation": "approve",
        "comments": "质量良好",
    })
    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                "correct_answer": "A",
                "explanation": "只保留必要字段符合最小化原则。",
                "knowledge_tags": ["隐私最小化", "推荐系统"],
                "dimension": "AI伦理安全",
            },
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"history_dup_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="历史近重复素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="推荐系统上线前，需要落实隐私最小化原则。",
                chunk_index=0,
            )
        )
        await question_service.create_question(
            db=session,
            question_type="single_choice",
            stem="推荐系统上线之前，哪项做法最符合隐私最小化原则？",
            options={"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
            correct_answer="A",
            explanation="只保留必要字段符合最小化原则。",
            difficulty=3,
            dimension="AI伦理安全",
            knowledge_tags=["隐私最小化", "推荐系统"],
            created_by=uploader.id,
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
        )

    await engine.dispose()

    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["quality_gate_failed"] is True
    assert result["stats"]["existing_near_duplicate_count"] == 1
    assert any("题库已有题目" in item for item in result["stats"]["warnings"])


@pytest.mark.asyncio
async def test_preview_question_bank_ignores_ai_reject_in_preview(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                "correct_answer": "A",
                "explanation": "只保留必要字段符合最小化原则。",
                "knowledge_tags": ["隐私最小化"],
                "dimension": "AI伦理安全",
            },
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {"stem_clarity": 2},
        "overall_score": 2.1,
        "recommendation": "reject",
        "comments": "题干存在明显歧义",
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"ai_reject_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="AI质检素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="推荐系统上线前，需要落实隐私最小化原则。",
                chunk_index=0,
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=3,
        )

    await engine.dispose()

    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["quality_gate_failed"] is False
    assert result["stats"]["quality_review_blocked"] == 0
    assert result["stats"]["quality_review_count"] == 0
    assert result["stats"]["ai_review_pending"] is False
    assert result.get("preview_batch_id") is None


@pytest.mark.asyncio
async def test_preview_question_bank_reports_calibration_warnings(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {
        "questions": [
            {
                "question_type": "single_choice",
                "stem": "人工智能的英文缩写是什么？",
                "options": {"A": "AI", "B": "BI", "C": "CI", "D": "DI"},
                "correct_answer": "A",
                "explanation": "AI 是 Artificial Intelligence 的缩写。",
                "knowledge_tags": ["AI基础"],
                "dimension": "AI基础认知",
            },
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "fallback_used": False,
        "error": None,
    })
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {"stem_clarity": 4},
        "overall_score": 4.3,
        "recommendation": "approve",
        "comments": "质量良好",
    })

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"calibration_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="校准检测素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="人工智能的英文缩写是 AI。",
                chunk_index=0,
            )
        )
        await session.commit()

        result = await question_service.preview_question_bank_from_material(
            db=session,
            material_id=material_id,
            type_distribution={"single_choice": 1},
            difficulty=5,
            bloom_level="create",
        )

    await engine.dispose()

    assert result["stats"]["save_blocked"] is False
    assert result["stats"]["calibration_review_count"] == 1
    assert result["stats"]["difficulty_mismatch_count"] == 1
    assert result["stats"]["bloom_mismatch_count"] == 1
    assert any("后验校准" in item for item in result["stats"]["warnings"])
    assert result["questions"][0]["calibration_review"]["severity"] == "severe"


@pytest.mark.asyncio
async def test_preview_question_bank_rejects_placeholder_material(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()

    monkeypatch.setattr(question_service, "generate_questions_via_llm", lambda *args, **kwargs: {"questions": []})

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"image_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="图片素材",
                format=MaterialFormat.IMAGE,
                file_path="materials/test.png",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                material_id=material_id,
                title="片段1",
                content="[图片素材: test.png - 待OCR处理]",
                chunk_index=0,
            )
        )
        await session.commit()

        with pytest.raises(ValueError, match="OCR/ASR"):
            await question_service.preview_question_bank_from_material(
                db=session,
                material_id=material_id,
                type_distribution={"single_choice": 1},
                difficulty=3,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_preview_question_bank_fails_when_unique_units_are_insufficient(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()
    llm_called = {"value": False}

    def _unexpected_llm_call(*args, **kwargs):
        llm_called["value"] = True
        raise AssertionError("LLM should not be called when unique knowledge units are insufficient")

    monkeypatch.setattr(question_service, "generate_questions_via_llm", _unexpected_llm_call)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"capacity_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="唯一知识点容量测试素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add_all(
            [
                KnowledgeUnit(
                    material_id=material_id,
                    title="知识点A",
                    summary="说明奖励建模。",
                    keywords={"topics": ["奖励建模"]},
                    content="知识点A说明奖励建模如何将偏好数据转化为训练目标。",
                    chunk_index=0,
                ),
                KnowledgeUnit(
                    material_id=material_id,
                    title="知识点B",
                    summary="说明混合加密。",
                    keywords={"topics": ["AES-GCM", "RSA"]},
                    content="知识点B说明混合加密如何同时兼顾效率与密钥分发安全。",
                    chunk_index=1,
                ),
            ]
        )
        await session.commit()

        with pytest.raises(ValueError, match="当前素材去重后仅有 2 个可用知识点，不足以生成 3 道互不重复知识点的题目"):
            await question_service.preview_question_bank_from_material(
                db=session,
                material_id=material_id,
                type_distribution={"single_choice": 2, "true_false": 1},
                difficulty=3,
                max_units=1,
            )

    await engine.dispose()
    assert llm_called["value"] is False


@pytest.mark.asyncio
async def test_get_question_by_id():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "测试题目",
            "correct_answer": "B",
            "options": {"A": "错", "B": "对"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/questions/{qid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["stem"] == "测试题目"


@pytest.mark.asyncio
async def test_get_question_by_id_includes_source_titles():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, ku_id = await upload_and_parse_material(client, token)
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers=headers,
        )
        ku_title = ku_resp.json()["units"][0]["title"]

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "带来源题目",
            "correct_answer": "A",
            "options": {"A": "对", "B": "错"},
            "source_material_id": mid,
            "source_knowledge_unit_id": ku_id,
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/questions/{qid}", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_material_title"] == "AI基础教材"
    assert data["source_knowledge_unit_title"] == ku_title
    assert data["source_knowledge_unit_excerpt"]


@pytest.mark.asyncio
async def test_get_question_by_id_includes_truncated_source_excerpt():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_material_resp = await client.post(
            "/api/v1/materials",
            headers=headers,
            files={"file": ("excerpt.md", io.BytesIO(b"long content"), "text/markdown")},
            data={"title": "摘要素材"},
        )
        assert create_material_resp.status_code == 201
        material_id = create_material_resp.json()["id"]

        long_content = "A" * 210
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            unit = KnowledgeUnit(
                material_id=uuid.UUID(material_id),
                title="摘要片段",
                content=long_content,
                chunk_index=0,
            )
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
            ku_id = str(unit.id)
        await engine.dispose()

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "来源摘要题目",
            "correct_answer": "A",
            "options": {"A": "对", "B": "错"},
            "source_material_id": material_id,
            "source_knowledge_unit_id": ku_id,
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/questions/{qid}", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_knowledge_unit_excerpt"] == ("A" * 200) + "..."


@pytest.mark.asyncio
async def test_get_question_by_id_without_source_has_no_excerpt():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "无来源摘要题目",
            "correct_answer": "A",
            "options": {"A": "对", "B": "错"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/questions/{qid}", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["source_knowledge_unit_excerpt"] is None


@pytest.mark.asyncio
async def test_get_question_not_found():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/questions/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_question():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "原始题干",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "difficulty": 2,
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.put(f"/api/v1/questions/{qid}", json={
            "stem": "更新后的题干",
            "difficulty": 4,
        }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["stem"] == "更新后的题干"
    assert resp.json()["difficulty"] == 4


@pytest.mark.asyncio
async def test_update_approved_question_keeps_status_and_ignores_question_type_change():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")
        org_headers = {"Authorization": f"Bearer {org_token}"}
        rev_headers = {"Authorization": f"Bearer {rev_token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "审核通过前的题干",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "difficulty": 2,
        }, headers=org_headers)
        qid = create_resp.json()["id"]

        submit_resp = await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        assert submit_resp.status_code == 200

        review_resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve", "comment": "通过"},
            headers=rev_headers,
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "approved"

        update_resp = await client.put(f"/api/v1/questions/{qid}", json={
            "stem": "审核通过后的新题干",
            "difficulty": 4,
            "question_type": "multiple_choice",
        }, headers=org_headers)

    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["stem"] == "审核通过后的新题干"
    assert data["difficulty"] == 4
    assert data["status"] == "approved"
    assert data["question_type"] == "single_choice"


@pytest.mark.asyncio
async def test_update_rejected_question_keeps_status():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")
        org_headers = {"Authorization": f"Bearer {org_token}"}
        rev_headers = {"Authorization": f"Bearer {rev_token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待驳回题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers=org_headers)
        qid = create_resp.json()["id"]

        submit_resp = await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        assert submit_resp.status_code == 200

        review_resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "reject", "comment": "需修改"},
            headers=rev_headers,
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "rejected"

        update_resp = await client.put(f"/api/v1/questions/{qid}", json={
            "stem": "驳回后修改的题干",
            "explanation": "补充解析",
        }, headers=org_headers)

    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["stem"] == "驳回后修改的题干"
    assert data["explanation"] == "补充解析"
    assert data["status"] == "rejected"


@pytest.mark.asyncio
async def test_update_archived_question_is_rejected():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待归档题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            question = await session.get(Question, uuid.UUID(qid))
            question.status = QuestionStatus.ARCHIVED
            await session.commit()
        await engine.dispose()

        update_resp = await client.put(f"/api/v1/questions/{qid}", json={
            "stem": "归档后不应可改",
        }, headers=headers)

    assert update_resp.status_code == 400
    assert update_resp.json()["detail"] == "已归档题目不允许编辑"


@pytest.mark.asyncio
async def test_delete_question():
    async with get_client() as client:
        token = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待删除",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers=headers)
        qid = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/questions/{qid}", headers=headers)
        assert resp.status_code == 204

        # Verify deleted
        resp2 = await client.get(f"/api/v1/questions/{qid}", headers=headers)
        assert resp2.status_code == 404


# ---- Review Workflow Tests ----

@pytest.mark.asyncio
async def test_submit_and_review_workflow():
    """Test full review workflow: create -> submit -> approve."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        # Create question
        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待审核题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {org_token}"})
        qid = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"

        # Submit for review
        submit_resp = await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "pending_review"

        # Approve
        review_resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve", "comment": "质量良好"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "approved"
        assert review_resp.json()["review_comment"] == "质量良好"


@pytest.mark.asyncio
async def test_reject_question():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "低质量题目",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {org_token}"})
        qid = create_resp.json()["id"]

        # Submit
        await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers={"Authorization": f"Bearer {org_token}"},
        )

        # Reject
        resp = await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "reject", "comment": "题干不够清晰"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_pending_review_list_includes_source_titles():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        rev_token = await register_user(client, "reviewer")
        headers = {"Authorization": f"Bearer {org_token}"}

        mid, ku_id = await upload_and_parse_material(client, org_token)
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers=headers,
        )
        ku_title = ku_resp.json()["units"][0]["title"]

        create_resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "待审核来源题",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "source_material_id": mid,
            "source_knowledge_unit_id": ku_id,
        }, headers=headers)
        qid = create_resp.json()["id"]

        await client.post(
            f"/api/v1/questions/{qid}/submit",
            headers=headers,
        )
        resp = await client.get(
            "/api/v1/questions/review/pending",
            headers={"Authorization": f"Bearer {rev_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["source_material_title"] == "AI基础教材"
    assert data["items"][0]["source_knowledge_unit_title"] == ku_title


@pytest.mark.asyncio
async def test_examinee_cannot_create_question():
    """Examinees should not be able to create questions."""
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "不应该成功",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ---- Generation Tests ----

@pytest.mark.asyncio
async def test_generate_from_knowledge_unit():
    """Generate questions from a parsed knowledge unit."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, ku_id = await upload_and_parse_material(client, token)
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers=headers,
        )
        ku_title = ku_resp.json()["units"][0]["title"]

        resp = await client.post("/api/v1/questions/generate", json={
            "knowledge_unit_id": ku_id,
            "question_types": ["single_choice", "true_false"],
            "count": 3,
            "difficulty": 2,
        }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 3
    assert len(data["questions"]) == 3
    # Verify questions have source references
    for q in data["questions"]:
        assert q["source_material_id"] == mid
        assert q["source_knowledge_unit_id"] == ku_id
        assert q["source_material_title"] == "AI基础教材"
        assert q["source_knowledge_unit_title"] == ku_title


@pytest.mark.asyncio
async def test_batch_generate_from_material():
    """Batch generate questions from all knowledge units of a material."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, _ = await upload_and_parse_material(client, token)

        resp = await client.post(
            f"/api/v1/questions/generate/material/{mid}",
            json={
                "question_types": ["single_choice"],
                "count_per_unit": 1,
                "difficulty": 3,
                "max_units": 3,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] >= 1


@pytest.mark.asyncio
async def test_batch_generate_from_material_prefers_high_value_units(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()
    called_ids: list[uuid.UUID] = []

    async def fake_generate_from_knowledge_unit(*args, **kwargs):
        called_ids.append(kwargs["knowledge_unit_id"])
        return {"questions": [], "usage": {}}

    monkeypatch.setattr(question_service, "generate_from_knowledge_unit", fake_generate_from_knowledge_unit)

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"select_owner_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        material = Material(
            id=material_id,
            title="知识片段选择测试",
            format=MaterialFormat.MARKDOWN,
            file_path="materials/test.md",
            file_size=128,
            status=MaterialStatus.PARSED,
            uploaded_by=uploader.id,
        )
        weak_unit = KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="导语",
            content="这是很短的引导语。",
            chunk_index=0,
        )
        rich_unit_a = KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="核心概念",
            summary="解释隐私最小化与授权范围控制。",
            keywords={"topics": ["隐私最小化", "授权范围", "数据治理"]},
            content="隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。",
            chunk_index=1,
        )
        rich_unit_b = KnowledgeUnit(
            id=uuid.uuid4(),
            material_id=material_id,
            title="案例分析",
            summary="分析推荐系统上线前的合规审查步骤。",
            keywords={"topics": ["合规审查", "推荐系统"]},
            content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
            chunk_index=2,
        )
        session.add(material)
        session.add_all([weak_unit, rich_unit_a, rich_unit_b])
        await session.commit()

        await question_service.batch_generate_from_material(
            db=session,
            material_id=material_id,
            question_types=["single_choice"],
            count_per_unit=1,
            difficulty=3,
            max_units=2,
        )

    await engine.dispose()

    assert set(called_ids) == {rich_unit_a.id, rich_unit_b.id}
    assert weak_unit.id not in called_ids


@pytest.mark.asyncio
async def test_generate_from_knowledge_unit_accepts_injected_question_plan(monkeypatch):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    material_id = uuid.uuid4()
    knowledge_unit_id = uuid.uuid4()
    captured: dict[str, object] = {}

    def fake_generate_questions_via_llm(**kwargs):
        captured["question_plan"] = kwargs.get("question_plan")
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "stem": "基于注入规划生成的题目",
                    "options": {"A": "答案A", "B": "答案B", "C": "答案C", "D": "答案D"},
                    "correct_answer": "A",
                    "explanation": "测试注入 question_plan。",
                    "knowledge_tags": ["注入规划"],
                    "dimension": "AI基础知识",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "fallback_used": False,
            "error": None,
        }

    monkeypatch.setattr(question_service, "generate_questions_via_llm", fake_generate_questions_via_llm)

    injected_plan = [
        {
            "knowledge_point": "注入规划知识点",
            "evidence": "知识片段中包含注入规划的证据。",
            "question_type": "single_choice",
            "stem_style": "直接知识型",
            "scenario": "课堂学习场景",
            "answer_focus": "理解注入规划的作用",
            "distractor_focus": "混入跳过规划的错误做法",
            "knowledge_tags": ["注入规划"],
            "dimension": "AI基础知识",
        }
    ]

    async with session_factory() as session:
        uploader = await create_user(
            session,
            username=f"plan_inject_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            password="password123",
            role_name="organizer",
        )
        session.add(
            Material(
                id=material_id,
                title="注入规划素材",
                format=MaterialFormat.MARKDOWN,
                file_path="materials/test.md",
                file_size=128,
                status=MaterialStatus.PARSED,
                uploaded_by=uploader.id,
            )
        )
        session.add(
            KnowledgeUnit(
                id=knowledge_unit_id,
                material_id=material_id,
                title="片段1",
                content="知识片段中包含注入规划的证据。",
                chunk_index=0,
            )
        )
        await session.commit()

        result = await question_service.generate_from_knowledge_unit(
            db=session,
            knowledge_unit_id=knowledge_unit_id,
            question_types=["single_choice"],
            count=1,
            difficulty=3,
            created_by=uploader.id,
            question_plan=injected_plan,
        )

    await engine.dispose()

    assert len(result["questions"]) == 1
    assert captured["question_plan"] == injected_plan
    assert result["questions"][0].stem == "基于注入规划生成的题目"


@pytest.mark.asyncio
async def test_batch_create_from_raw_accepts_uuid_source_fields():
    """Preview save should accept UUID objects produced by Pydantic."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        mid, ku_id = await upload_and_parse_material(client, token)
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers=headers,
        )
        ku_title = ku_resp.json()["units"][0]["title"]

        resp = await client.post(
            "/api/v1/questions/batch/create-raw",
            json={
                "questions": [
                    {
                        "question_type": "single_choice",
                        "stem": "保存预览题目",
                        "options": {"A": "人工智能", "B": "区块链"},
                        "correct_answer": "A",
                        "explanation": "测试保存预览题目",
                        "difficulty": 3,
                        "dimension": "AI基础认知",
                        "knowledge_tags": ["AI基础"],
                        "bloom_level": "understand",
                        "source_material_id": mid,
                        "source_knowledge_unit_id": ku_id,
                    }
                ]
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 1
    assert data["questions"][0]["source_material_id"] == mid
    assert data["questions"][0]["source_knowledge_unit_id"] == ku_id
    assert data["questions"][0]["source_material_title"] == "AI基础教材"
    assert data["questions"][0]["source_knowledge_unit_title"] == ku_title


@pytest.mark.asyncio
async def test_batch_create_from_raw_accepts_duplicate_stems():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/questions/batch/create-raw",
            json={
                "questions": [
                    {
                        "question_type": "single_choice",
                        "stem": "重复题目",
                        "options": {"A": "正确", "B": "错误"},
                        "correct_answer": "A",
                        "explanation": "解释1",
                        "difficulty": 3,
                    },
                    {
                        "question_type": "single_choice",
                        "stem": "重复题目",
                        "options": {"A": "正确", "B": "错误"},
                        "correct_answer": "A",
                        "explanation": "解释2",
                        "difficulty": 3,
                    },
                ]
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["generated"] == 2


@pytest.mark.asyncio
async def test_batch_create_from_raw_accepts_near_duplicates(monkeypatch):
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {},
        "overall_score": 4.0,
        "recommendation": "approve",
        "comments": "质量良好",
    })

    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/questions/batch/create-raw",
            json={
                "questions": [
                    {
                        "question_type": "single_choice",
                        "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                        "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                        "correct_answer": "A",
                        "explanation": "只保留必要字段符合最小化原则。",
                        "difficulty": 3,
                        "dimension": "AI伦理安全",
                        "knowledge_tags": ["隐私最小化", "推荐系统"],
                    },
                    {
                        "question_type": "single_choice",
                        "stem": "推荐系统上线之前，哪项做法最符合隐私最小化原则？",
                        "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                        "correct_answer": "A",
                        "explanation": "只保留必要字段符合最小化原则。",
                        "difficulty": 3,
                        "dimension": "AI伦理安全",
                        "knowledge_tags": ["隐私最小化", "推荐系统"],
                    },
                ]
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["generated"] == 2


@pytest.mark.asyncio
async def test_batch_create_from_raw_accepts_existing_near_duplicates(monkeypatch):
    monkeypatch.setattr(question_service, "ai_review_question", lambda *args, **kwargs: {
        "scores": {},
        "overall_score": 4.0,
        "recommendation": "approve",
        "comments": "质量良好",
    })

    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/questions",
            json={
                "question_type": "single_choice",
                "stem": "推荐系统上线之前，哪项做法最符合隐私最小化原则？",
                "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                "correct_answer": "A",
                "explanation": "只保留必要字段符合最小化原则。",
                "difficulty": 3,
                "dimension": "AI伦理安全",
                "knowledge_tags": ["隐私最小化", "推荐系统"],
            },
            headers=headers,
        )
        assert create_resp.status_code == 201

        resp = await client.post(
            "/api/v1/questions/batch/create-raw",
            json={
                "questions": [
                    {
                        "question_type": "single_choice",
                        "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                        "options": {"A": "只保留必要字段", "B": "扩大日志采集", "C": "长期保存原始数据", "D": "关闭访问审计"},
                        "correct_answer": "A",
                        "explanation": "只保留必要字段符合最小化原则。",
                        "difficulty": 3,
                        "dimension": "AI伦理安全",
                        "knowledge_tags": ["隐私最小化", "推荐系统"],
                    }
                ]
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["generated"] == 1


@pytest.mark.asyncio
async def test_generate_invalid_knowledge_unit():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post("/api/v1/questions/generate", json={
            "knowledge_unit_id": "00000000-0000-0000-0000-000000000000",
            "question_types": ["single_choice"],
            "count": 1,
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


# ---- Stats Test ----

@pytest.mark.asyncio
async def test_question_stats():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "统计测试题一",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "dimension": "AI基础",
        }, headers=headers)
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "统计测试题二",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "dimension": "AI基础",
            "bloom_level": "understand",
            "explanation": "用于统计测试的解析。",
        }, headers=headers)

        resp = await client.get("/api/v1/questions/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert "by_status" in data
    assert "by_type" in data
    assert data["by_bloom_level"]["understand"] == 1
    assert data["quality_metrics"]["missing_bloom_level_count"] == 1
    assert data["quality_metrics"]["missing_explanation_count"] == 1
    assert data["quality_metrics"]["source_linked_count"] == 0


@pytest.mark.asyncio
async def test_question_stats_filters_by_source_material():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(decode_access_token(token)["sub"])

        mid1, ku_id1 = await upload_and_parse_material(client, token, title="统计素材一", filename="stats_one.md")
        mid2, ku_id2 = await upload_and_parse_material(client, token, title="统计素材二", filename="stats_two.md")

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            session.add_all([
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="统计素材一题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    dimension="AI基础",
                    source_material_id=uuid.UUID(mid1),
                    source_knowledge_unit_id=uuid.UUID(ku_id1),
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="统计素材二题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    dimension="AI伦理安全",
                    source_material_id=uuid.UUID(mid2),
                    source_knowledge_unit_id=uuid.UUID(ku_id2),
                    bloom_level=BloomLevel.UNDERSTAND,
                    explanation="用于过滤统计的解析。",
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="统计自由题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    dimension="AI批判思维",
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
            ])
            await session.commit()
        await engine.dispose()

        resp = await client.get(
            f"/api/v1/questions/stats?source_material_id={mid1}",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["by_type"]["single_choice"] == 1
    assert data["quality_metrics"]["source_linked_count"] == 1
    assert data["quality_metrics"]["source_unlinked_count"] == 0


@pytest.mark.asyncio
async def test_question_stats_approved_by_dimension_includes_uncategorized():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(decode_access_token(token)["sub"])

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            session.add_all([
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="已通过且已分类题目",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    dimension="AI基础知识",
                    created_by=user_id,
                    status=QuestionStatus.APPROVED,
                ),
                Question(
                    question_type=QuestionType.TRUE_FALSE,
                    stem="已通过但未分类题目",
                    correct_answer="A",
                    options={"A": "正确", "B": "错误"},
                    dimension=None,
                    created_by=user_id,
                    status=QuestionStatus.APPROVED,
                ),
                Question(
                    question_type=QuestionType.SINGLE_CHOICE,
                    stem="草稿题目不应计入已通过统计",
                    correct_answer="A",
                    options={"A": "1", "B": "2"},
                    dimension="AI伦理安全",
                    created_by=user_id,
                    status=QuestionStatus.DRAFT,
                ),
            ])
            await session.commit()
        await engine.dispose()

        resp = await client.get("/api/v1/questions/stats?status=approved", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["by_status"] == {"approved": 2}
    assert data["by_dimension"]["AI基础知识"] == 1
    assert data["by_dimension"]["未分类"] == 1
    assert data["by_dimension"]["AI伦理安全"] == 0
