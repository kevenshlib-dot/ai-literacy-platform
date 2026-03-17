"""Unit tests for multi-model question generation comparison support."""

import json
import uuid
from pathlib import Path

import pytest

from app.agents import question_agent
from app.agents.llm_utils import build_disable_thinking_extra_body
from app.agents.model_registry import (
    DEFAULT_COMPARE_MODEL_SLUGS,
    ModelConfig,
    get_compare_models,
)
from scripts.compare_question_generation import (
    ComparisonRunConfig,
    ModelRunResult,
    aggregate_question_counts_by_dimension,
    aggregate_question_counts_by_type,
    build_markdown_report,
    write_run_outputs,
)


def test_build_user_prompt_is_deterministic_for_same_seed():
    prompt1 = question_agent._build_user_prompt(
        content="人工智能帮助提升工作效率。",
        question_types=["single_choice", "true_false"],
        count=3,
        difficulty=3,
        bloom_level="apply",
        custom_prompt="侧重工作场景",
        prompt_seed=42,
    )
    prompt2 = question_agent._build_user_prompt(
        content="人工智能帮助提升工作效率。",
        question_types=["single_choice", "true_false"],
        count=3,
        difficulty=3,
        bloom_level="apply",
        custom_prompt="侧重工作场景",
        prompt_seed=42,
    )

    assert prompt1 == prompt2


def test_build_user_prompt_changes_when_seed_changes():
    prompt1 = question_agent._build_user_prompt(
        content="人工智能帮助提升工作效率。",
        question_types=["single_choice", "true_false"],
        count=3,
        difficulty=3,
        bloom_level="apply",
        prompt_seed=42,
    )
    prompt2 = question_agent._build_user_prompt(
        content="人工智能帮助提升工作效率。",
        question_types=["single_choice", "true_false"],
        count=3,
        difficulty=3,
        bloom_level="apply",
        prompt_seed=43,
    )

    assert prompt1 != prompt2


def test_build_user_prompt_material_generation_includes_material_only_rules():
    prompt = question_agent._build_user_prompt(
        content="大模型应用需要隐私脱敏与合规审查。",
        question_types=["single_choice", "true_false"],
        count=4,
        difficulty=3,
        bloom_level="apply",
        prompt_seed=42,
    )

    assert "禁止出现书名、作者、出版信息、章节编号" in prompt
    assert "同套题禁止重复知识点" in prompt
    assert "\"一位……\"开头的题干最多只能出现2题" in prompt
    assert "判断题题干必须是陈述句，禁止使用疑问句" in prompt
    assert "生成后必须先自检" in prompt


def test_build_user_prompt_free_generation_omits_material_only_rules():
    prompt = question_agent._build_user_prompt(
        content="",
        question_types=["single_choice", "true_false"],
        count=4,
        difficulty=3,
        bloom_level="apply",
        prompt_seed=42,
    )

    assert "禁止出现书名、作者、出版信息、章节编号" not in prompt
    assert "同套题禁止重复知识点" not in prompt
    assert "生成后必须先自检" not in prompt


def test_get_compare_models_defaults_to_all_supported_models():
    models = get_compare_models()

    assert [model.slug for model in models] == list(DEFAULT_COMPARE_MODEL_SLUGS)
    assert models[0].model_name == "gemini-3-pro-preview"
    assert models[0].provider == "openai_compatible"
    assert models[2].model_name == "doubao-seed-2-0-pro-260215"


def test_get_compare_models_filters_requested_subset():
    models = get_compare_models(["doubao", "local_qwen"])

    assert [model.slug for model in models] == ["doubao", "local_qwen"]


def test_get_compare_models_rejects_unknown_slug():
    with pytest.raises(ValueError, match="Unknown model slug"):
        get_compare_models(["unknown"])


def test_request_question_generation_routes_gemini_to_openai_compatible(monkeypatch):
    called = {}

    def fake_openai(model_config, api_key, system_prompt, user_prompt, max_tokens, empty_usage):
        called["slug"] = model_config.slug
        called["api_key"] = api_key
        called["system_prompt"] = system_prompt
        called["user_prompt"] = user_prompt
        called["max_tokens"] = max_tokens
        return {"content": "[]", "usage": empty_usage}

    monkeypatch.setattr(
        question_agent,
        "_request_question_generation_openai_compatible",
        fake_openai,
    )

    result = question_agent._request_question_generation(
        model_config=get_compare_models(["gemini"])[0],
        api_key="test-key",
        system_prompt="system",
        user_prompt="prompt",
        max_tokens=512,
        empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )

    assert called == {
        "slug": "gemini",
        "api_key": "test-key",
        "system_prompt": "system",
        "user_prompt": "prompt",
        "max_tokens": 512,
    }
    assert result["content"] == "[]"


def test_validate_user_prompt_template_rejects_unknown_placeholder():
    with pytest.raises(ValueError, match="未知占位符"):
        question_agent.validate_user_prompt_template("生成 {{unknown_field}} 道题")


def test_validate_user_prompt_template_rejects_malformed_placeholder():
    with pytest.raises(ValueError, match="未知占位符"):
        question_agent.validate_user_prompt_template("生成 {{COUNT}} 道题")


def test_build_user_prompt_supports_custom_template():
    prompt = question_agent._build_user_prompt(
        content="人工智能帮助提升工作效率。",
        question_types=["single_choice"],
        count=2,
        difficulty=3,
        custom_prompt="侧重工作场景",
        prompt_seed=42,
        user_prompt_template="题型={{question_types}} | 数量={{count}} | 要求={{custom_requirements}}",
    )

    assert "题型=单选题(single_choice)" in prompt
    assert "数量=2" in prompt
    assert "侧重工作场景" in prompt


def test_render_user_prompt_keeps_backslashes_in_replacement_values():
    rendered = question_agent.render_user_prompt(
        "内容={{content_section}}",
        {"content_section": r"C:\\temp\\demo\\1.txt"},
    )

    assert rendered == r"内容=C:\\temp\\demo\\1.txt"


def test_disable_thinking_extra_body_skips_gemini_hosts():
    assert build_disable_thinking_extra_body(
        model_name="gemini-3-pro-preview",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_slug="default",
    ) is None


def test_disable_thinking_extra_body_keeps_local_qwen():
    assert build_disable_thinking_extra_body(
        model_name="Qwen/Qwen3.5-35B-A3B-FP8",
        base_url="http://100.64.0.6:8100/v1",
        model_slug="default",
    ) == {"chat_template_kwargs": {"enable_thinking": False}}


def test_question_agent_does_not_expose_legacy_gemini_helpers():
    assert not hasattr(question_agent, "_request_question_generation_gemini")
    assert not hasattr(question_agent, "_build_gemini_client")
    assert not hasattr(question_agent, "_build_gemini_generate_content_url")


def test_generate_questions_via_llm_marks_fallback_errors(monkeypatch):
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    result = question_agent.generate_questions_via_llm(
        content="人工智能基础知识。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is True
    assert "timed out" in result["error"]
    assert len(result["questions"]) == 1


def test_validate_generated_question_set_rejects_material_metadata_duplicates_and_tf_format():
    questions = [
        {
            "question_type": "single_choice",
            "stem": "根据本文，书中提出的隐私脱敏流程首先要完成哪一步？",
            "options": {"A": "识别敏感字段", "B": "跳过清洗", "C": "直接发布", "D": "永久共享"},
            "correct_answer": "A",
            "explanation": "应先识别敏感字段。",
            "knowledge_tags": ["隐私脱敏"],
            "dimension": "AI伦理安全",
        },
        {
            "question_type": "single_choice",
            "stem": "一位产品经理准备上线推荐服务，以下哪项最符合隐私最小化原则？",
            "options": {"A": "只保留必要字段", "B": "收集全部日志", "C": "长期留存原始数据", "D": "共享未脱敏数据"},
            "correct_answer": "A",
            "explanation": "最小化原则要求只保留必要字段。",
            "knowledge_tags": ["隐私脱敏"],
            "dimension": "AI伦理安全",
        },
        {
            "question_type": "true_false",
            "stem": "一位产品经理能否直接把公共网络数据接入推荐服务？",
            "options": {"A": "是", "B": "否"},
            "correct_answer": "B",
            "explanation": "仍需合规审查。",
            "knowledge_tags": ["公共数据合规"],
            "dimension": "AI伦理安全",
        },
        {
            "question_type": "single_choice",
            "stem": "一位产品经理在设计推荐功能时，首要的合规动作是什么？",
            "options": {"A": "做用途评估", "B": "忽略授权", "C": "跳过审计", "D": "扩大采集"},
            "correct_answer": "A",
            "explanation": "应先明确用途并评估合规性。",
            "knowledge_tags": ["用途评估"],
            "dimension": "AI伦理安全",
        },
    ]

    result = question_agent._validate_generated_question_set(
        questions,
        strict_material_rules=True,
    )

    assert result["passed"] is False
    assert any("素材元信息" in reason for reason in result["reasons"])
    assert any("知识点重复" in reason for reason in result["reasons"])
    assert any("判断题" in reason for reason in result["reasons"])
    assert any("职业角色重复" in reason for reason in result["reasons"])


def test_validate_generated_question_set_accepts_valid_material_questions():
    questions = [
        {
            "question_type": "single_choice",
            "stem": "推荐系统上线前，哪项做法最能降低个人信息误用风险？",
            "options": {"A": "只保留必要字段", "B": "扩大原始日志采集", "C": "延长未脱敏数据留存", "D": "取消访问审计"},
            "correct_answer": "A",
            "explanation": "只保留必要字段符合最小化原则。",
            "knowledge_tags": ["数据最小化"],
            "dimension": "AI伦理安全",
        },
        {
            "question_type": "true_false",
            "stem": "公共来源的数据在接入推荐服务前，仍需完成隐私脱敏和合规审查。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "A",
            "explanation": "公共来源不等于可以免除合规义务。",
            "knowledge_tags": ["公共数据合规"],
            "dimension": "AI伦理安全",
        },
        {
            "question_type": "single_choice",
            "stem": "一位数据分析师在训练推荐模型前，最应优先核查哪项内容？",
            "options": {"A": "字段用途与授权范围是否一致", "B": "是否尽量收集更多个人信息", "C": "是否跳过样本清洗", "D": "是否忽略审计日志"},
            "correct_answer": "A",
            "explanation": "先核查用途与授权范围，才能判断数据是否可用。",
            "knowledge_tags": ["授权范围"],
            "dimension": "AI伦理安全",
        },
    ]

    result = question_agent._validate_generated_question_set(
        questions,
        strict_material_rules=True,
    )

    assert result["passed"] is True
    assert result["reasons"] == []


def test_aggregate_helpers_count_types_and_dimensions():
    questions = [
        {"question_type": "single_choice", "dimension": "AI基础知识"},
        {"question_type": "single_choice", "dimension": "AI基础知识"},
        {"question_type": "true_false", "dimension": "AI伦理安全"},
    ]

    assert aggregate_question_counts_by_type(questions) == {
        "single_choice": 2,
        "true_false": 1,
    }
    assert aggregate_question_counts_by_dimension(questions) == {
        "AI基础知识": 2,
        "AI伦理安全": 1,
    }


def test_build_markdown_report_includes_overview_and_material_sections():
    config = ComparisonRunConfig(
        material_ids=[uuid.UUID("11111111-1111-1111-1111-111111111111")],
        type_distribution={"single_choice": 2, "true_false": 1},
        difficulty=3,
        bloom_level="apply",
        custom_prompt="侧重应用",
        max_units=5,
        prompt_seed=42,
        model_slugs=["local_qwen"],
        output_dir=Path("artifacts/question-compare"),
    )
    model = ModelConfig(
        slug="local_qwen",
        display_name="Qwen Local",
        provider="openai_compatible",
        model_name="Qwen/Qwen3.5-35B-A3B-FP8",
        api_key_env="LOCAL_QWEN_API_KEY",
        base_url_env="LOCAL_QWEN_BASE_URL",
        default_api_key="token-not-needed",
    )
    result = ModelRunResult(
        model=model,
        materials=[
            {
                "material_id": "11111111-1111-1111-1111-111111111111",
                "material_title": "AI 基础教材",
                "questions": [
                    {
                        "question_type": "single_choice",
                        "dimension": "AI基础知识",
                        "stem": "题目一",
                        "options": {"A": "甲", "B": "乙"},
                        "correct_answer": "A",
                        "explanation": "解释一",
                        "source_material_id": "11111111-1111-1111-1111-111111111111",
                    }
                ],
                "stats": {
                    "total_tokens": 10,
                    "prompt_tokens": 4,
                    "completion_tokens": 6,
                    "duration_seconds": 1.2,
                    "type_counts": {"single_choice": 1},
                },
                "error": None,
            }
        ],
        questions=[
            {
                "question_type": "single_choice",
                "dimension": "AI基础知识",
                "stem": "题目一",
                "options": {"A": "甲", "B": "乙"},
                "correct_answer": "A",
                "explanation": "解释一",
                "source_material_id": "11111111-1111-1111-1111-111111111111",
            }
        ],
        stats={
            "total_tokens": 10,
            "prompt_tokens": 4,
            "completion_tokens": 6,
            "duration_seconds": 1.2,
            "type_counts": {"single_choice": 1},
            "dimension_counts": {"AI基础知识": 1},
        },
        errors=[],
    )

    report = build_markdown_report(config, [result])

    assert "多模型题库生成对比报告" in report
    assert "Qwen Local" in report
    assert "AI 基础教材" in report
    assert "题目一" in report


def test_write_run_outputs_creates_json_and_markdown(tmp_path: Path):
    config = ComparisonRunConfig(
        material_ids=[uuid.UUID("11111111-1111-1111-1111-111111111111")],
        type_distribution={"single_choice": 1},
        difficulty=3,
        bloom_level=None,
        custom_prompt=None,
        max_units=5,
        prompt_seed=7,
        model_slugs=["local_qwen"],
        output_dir=tmp_path,
    )
    model = ModelConfig(
        slug="local_qwen",
        display_name="Qwen Local",
        provider="openai_compatible",
        model_name="Qwen/Qwen3.5-35B-A3B-FP8",
        api_key_env="LOCAL_QWEN_API_KEY",
        base_url_env="LOCAL_QWEN_BASE_URL",
        default_api_key="token-not-needed",
    )
    result = ModelRunResult(
        model=model,
        materials=[],
        questions=[],
        stats={
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "duration_seconds": 0.0,
            "type_counts": {},
            "dimension_counts": {},
        },
        errors=[],
    )

    run_dir = write_run_outputs(config, [result])

    assert (run_dir / "comparison.md").exists()
    assert (run_dir / "run_config.json").exists()
    model_json = run_dir / "models" / "local_qwen.json"
    assert model_json.exists()
    payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert payload["model"]["slug"] == "local_qwen"
