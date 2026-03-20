"""Tests for question generation engine (T009)."""
import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.services import question_service
from app.models.material import Material, MaterialFormat, MaterialStatus, KnowledgeUnit
from app.services.user_service import create_user, init_roles
from app.agents.question_agent import generate_questions_via_llm, _template_fallback


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
    assert questions[0]["correct_answer"] in ("A", "B")


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


async def upload_and_parse_material(client, token):
    """Upload a markdown file, parse it, and return material_id and knowledge_unit_id."""
    md_content = "# AI基础认知\n\n" + "人工智能是计算机科学的一个分支。" * 50
    upload = await client.post(
        "/api/v1/materials",
        files={"file": ("ai_basics.md", md_content.encode(), "text/markdown")},
        data={"title": "AI基础教材"},
        headers={"Authorization": f"Bearer {token}"},
    )
    mid = upload.json()["id"]

    # Parse material
    await client.post(
        f"/api/v1/materials/{mid}/parse",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get knowledge units
    ku_resp = await client.get(
        f"/api/v1/materials/{mid}/knowledge-units",
        headers={"Authorization": f"Bearer {token}"},
    )
    ku_data = ku_resp.json()
    ku_id = ku_data["units"][0]["id"]
    return mid, ku_id


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
    assert count_placeholder["source"] == "题型分配合计数量"


@pytest.mark.asyncio
async def test_prompt_config_save_and_delete():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        headers = {"Authorization": f"Bearer {token}"}

        save_resp = await client.put(
            "/api/v1/questions/generation/prompt-config",
            json={
                "system_prompt": "自定义系统提示词",
                "user_prompt_template": "生成 {{count}} 道题目",
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
    assert get_resp.json()["user_prompt_template"] == "生成 {{count}} 道题目"
    assert delete_resp.json()["has_saved_config"] is False


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
                "user_prompt_template": "内容={{content_section}}",
                "material_ids": [material_id],
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rendered_user_prompts"]) == 1
    assert "【参考素材】" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "人工智能是计算机科学的一个分支" in data["rendered_user_prompts"][0]["rendered_user_prompt"]
    assert "按实际调用顺序向模型发送 1 条用户提示词" in data["preview_note"]


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
                "user_prompt_template": "内容={{content_section}}\n规则={{diversity_rules}}",
            },
            headers=headers,
        )
        seed = first_resp.json()["prompt_seed"]
        second_resp = await client.post(
            "/api/v1/questions/generation/prompt-preview",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "user_prompt_template": "内容={{content_section}}\n规则={{diversity_rules}}",
                "prompt_seed": seed,
            },
            headers=headers,
        )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    assert first_resp.json()["rendered_user_prompts"] == second_resp.json()["rendered_user_prompts"]


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
                "user_prompt_template": "保存的模板 {{count}}",
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
    assert captured["user_prompt_template"] == "保存的模板 {{count}}"


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
                "user_prompt_template": "保存的模板 {{count}}",
            },
            headers=headers,
        )

        resp = await client.post(
            "/api/v1/questions/preview/free",
            json={
                "type_distribution": {"single_choice": 1},
                "difficulty": 3,
                "system_prompt": "本次系统提示词",
                "user_prompt_template": "本次模板 {{count}}",
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert captured["system_prompt"] == "本次系统提示词"
    assert captured["user_prompt_template"] == "本次模板 {{count}}"


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

        # Create a question
        await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "统计测试题",
            "correct_answer": "A",
            "options": {"A": "1", "B": "2"},
            "dimension": "AI基础",
        }, headers=headers)

        resp = await client.get("/api/v1/questions/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "by_status" in data
    assert "by_type" in data
