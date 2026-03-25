"""Unit tests for multi-model question generation comparison support."""

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

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

VALID_TEST_USER_PROMPT_TEMPLATE = (
    "题型={{question_types}}\n"
    "数量={{count}}\n"
    "{{difficulty_section}}\n"
    "{{diversity_rules}}\n"
    "{{question_plan_section}}\n"
    "{{custom_requirements}}\n"
    "{{content_section}}"
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


def test_build_question_plan_is_deterministic_for_same_seed():
    plan1 = question_agent.build_question_plan(
        content="【知识单元标题】\n隐私最小化\n\n【知识单元摘要】\n推荐系统上线前需检查脱敏与授权范围。\n\n【知识单元关键词】\n隐私最小化、授权范围、推荐系统\n\n【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice", "true_false"],
        count=2,
        difficulty=3,
        prompt_seed=42,
    )
    plan2 = question_agent.build_question_plan(
        content="【知识单元标题】\n隐私最小化\n\n【知识单元摘要】\n推荐系统上线前需检查脱敏与授权范围。\n\n【知识单元关键词】\n隐私最小化、授权范围、推荐系统\n\n【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice", "true_false"],
        count=2,
        difficulty=3,
        prompt_seed=42,
    )

    assert plan1 == plan2
    assert len(plan1) == 2
    assert plan1[0]["knowledge_point"]
    assert plan1[0]["evidence"]


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


def test_build_user_prompt_adds_type_hard_rules_for_strict_types():
    prompt = question_agent._build_user_prompt(
        content="推荐系统上线前需要完成隐私审查与数据脱敏。",
        question_types=["true_false", "fill_blank"],
        count=2,
        difficulty=3,
        prompt_seed=42,
    )

    assert "【题型硬约束——优先级高于多样性要求】" in prompt
    assert "判断题：题干必须写成可直接判断真假的完整陈述句" in prompt
    assert "填空题：题干必须包含明确空位标记" in prompt
    assert "若冲突，以题型硬约束为准" in prompt


def test_build_user_prompt_includes_question_plan_section():
    prompt = question_agent._build_user_prompt(
        content="【知识单元标题】\n隐私最小化\n\n【知识单元摘要】\n推荐系统上线前需检查脱敏与授权范围。\n\n【知识单元关键词】\n隐私最小化、授权范围、推荐系统\n\n【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        prompt_seed=42,
        question_plan=question_agent.build_question_plan(
            content="【知识单元标题】\n隐私最小化\n\n【知识单元摘要】\n推荐系统上线前需检查脱敏与授权范围。\n\n【知识单元关键词】\n隐私最小化、授权范围、推荐系统\n\n【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
            question_types=["single_choice"],
            count=1,
            difficulty=3,
            prompt_seed=42,
        ),
    )

    assert "【知识点出题规划】" in prompt
    assert "证据锚点" in prompt


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

    def fake_openai(
        model_config,
        api_key,
        system_prompt,
        user_prompt,
        max_tokens,
        count,
        empty_usage,
        response_format=None,
        parse_response_format=None,
        temperature=0.4,
    ):
        called["slug"] = model_config.slug
        called["api_key"] = api_key
        called["system_prompt"] = system_prompt
        called["user_prompt"] = user_prompt
        called["max_tokens"] = max_tokens
        called["count"] = count
        called["response_format"] = response_format
        called["parse_response_format"] = parse_response_format
        called["temperature"] = temperature
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
        count=2,
        empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )

    assert called == {
        "slug": "gemini",
        "api_key": "test-key",
        "system_prompt": "system",
        "user_prompt": "prompt",
        "max_tokens": 512,
        "count": 2,
        "response_format": None,
        "parse_response_format": None,
        "temperature": 0.4,
    }
    assert result["content"] == "[]"


def test_supports_structured_output_allows_local_qwen():
    assert question_agent._supports_structured_output(get_compare_models(["local_qwen"])[0]) is True
    assert question_agent._supports_structured_output(get_compare_models(["gemini"])[0]) is True


def test_supports_structured_output_allows_default_local_qwen():
    model = ModelConfig(
        slug="default",
        display_name="Local Qwen",
        provider="openai_compatible",
        model_name="Qwen/Qwen3.5-35B-A3B-FP8",
        default_base_url="http://127.0.0.1:8100/v1",
        default_api_key="token-not-needed",
    )
    assert question_agent._supports_structured_output(model) is True


def test_supports_structured_output_keeps_local_non_qwen_disabled():
    model = ModelConfig(
        slug="local_other",
        display_name="Local Other",
        provider="openai_compatible",
        model_name="SomeOtherModel",
        default_base_url="http://127.0.0.1:8100/v1",
        default_api_key="token-not-needed",
    )
    assert question_agent._supports_structured_output(model) is False


def test_openai_compatible_request_retries_without_response_format(monkeypatch):
    captured_calls = []

    class FakeUsage:
        prompt_tokens = 1
        completion_tokens = 2
        total_tokens = 3

    class FakeMessage:
        content = "[]"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = FakeUsage()
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured_calls.append(kwargs)
            if "response_format" in kwargs:
                raise Exception("response_format is not supported by this endpoint")
            return FakeResponse()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(question_agent, "OpenAI", FakeClient)

    result = question_agent._request_question_generation_openai_compatible(
        model_config=get_compare_models(["gemini"])[0],
        api_key="test-key",
        system_prompt="system",
        user_prompt="prompt",
        max_tokens=512,
        count=2,
        empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        response_format=question_agent._build_question_response_format(2, ["single_choice"]),
    )

    assert len(captured_calls) == 2
    assert "response_format" in captured_calls[0]
    assert "response_format" not in captured_calls[1]
    assert result["content"] == "[]"
    assert result["usage"]["total_tokens"] == 3


def test_openai_compatible_request_prefers_parse_response_when_available(monkeypatch):
    parse_calls = []
    create_calls = []

    class FakeUsage:
        prompt_tokens = 3
        completion_tokens = 4
        total_tokens = 7

    class FakeMessage:
        content = '[{"knowledge_point":"隐私最小化"}]'
        parsed = question_agent._QuestionPlanResponseModel([
            question_agent._QuestionPlanItemModel(
                knowledge_point="隐私最小化",
                evidence="上线前需要完成数据脱敏。",
                question_type="single_choice",
                stem_style="情景应用型",
                scenario="课堂学习场景",
                answer_focus="先做数据脱敏",
                distractor_focus="混入扩大采集等误解",
                knowledge_tags=["隐私最小化"],
                dimension="AI伦理安全",
            )
        ])

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = FakeUsage()
        choices = [FakeChoice()]

    class FakeCompletions:
        def parse(self, **kwargs):
            parse_calls.append(kwargs)
            return FakeResponse()

        def create(self, **kwargs):
            create_calls.append(kwargs)
            raise AssertionError("create should not be called when parse succeeds")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            completions = FakeCompletions()
            self.chat = type("Chat", (), {"completions": completions})()
            self.beta = type(
                "Beta",
                (),
                {"chat": type("Chat", (), {"completions": completions})()},
            )()

    monkeypatch.setattr(question_agent, "OpenAI", FakeClient)

    result = question_agent._request_question_generation_openai_compatible(
        model_config=get_compare_models(["local_qwen"])[0],
        api_key="test-key",
        system_prompt="system",
        user_prompt="prompt",
        max_tokens=512,
        count=1,
        empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        response_format=question_agent._build_question_plan_response_format(1),
        parse_response_format=question_agent._QuestionPlanResponseModel,
    )

    assert len(parse_calls) == 1
    assert not create_calls
    assert result["structured_mode"] == "parse"
    assert result["parsed"][0]["knowledge_point"] == "隐私最小化"
    assert result["usage"]["total_tokens"] == 7


def test_openai_compatible_request_does_not_fallback_to_text_on_parse_validation_error(monkeypatch):
    create_calls = []

    class FakeCompletions:
        def parse(self, **kwargs):
            raise ValueError("Field required: options")

        def create(self, **kwargs):
            create_calls.append(kwargs)
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            completions = FakeCompletions()
            self.chat = type("Chat", (), {"completions": completions})()
            self.beta = type(
                "Beta",
                (),
                {"chat": type("Chat", (), {"completions": completions})()},
            )()

    monkeypatch.setattr(question_agent, "OpenAI", FakeClient)

    with pytest.raises(ValueError, match="options"):
        question_agent._request_question_generation_openai_compatible(
            model_config=get_compare_models(["local_qwen"])[0],
            api_key="test-key",
            system_prompt="system",
            user_prompt="prompt",
            max_tokens=512,
            count=1,
            empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            response_format=question_agent._build_question_response_format(1, ["single_choice"]),
            parse_response_format=question_agent._GeneratedSingleChoiceResponseModel,
            allow_text_fallback_on_parse_error=False,
        )

    assert not create_calls


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
        user_prompt_template=(
            "题型={{question_types}} | 数量={{count}} | "
            "{{difficulty_section}} | {{diversity_rules}} | {{question_plan_section}} | {{custom_requirements}} | {{content_section}}"
        ),
    )

    assert "题型=单选题(single_choice)" in prompt
    assert "数量=2" in prompt
    assert "侧重工作场景" in prompt


def test_render_user_prompt_keeps_backslashes_in_replacement_values():
    rendered = question_agent.render_user_prompt(
        VALID_TEST_USER_PROMPT_TEMPLATE,
        {
            "question_types": "单选题(single_choice)",
            "count": "1",
            "difficulty_section": "难度=3",
            "diversity_rules": "多样性约束",
            "question_plan_section": "规划",
            "custom_requirements": "",
            "content_section": r"C:\\temp\\demo\\1.txt",
        },
    )

    assert r"C:\\temp\\demo\\1.txt" in rendered


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
    assert len(result["question_plan"]) == 1


def test_generate_question_plan_via_llm_falls_back_to_local_plan(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("planner timed out")),
    )

    result = question_agent.generate_question_plan_via_llm(
        content="【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is True
    assert "planner timed out" in result["error"]
    assert len(result["question_plan"]) == 1


def test_generate_question_plan_via_llm_prefers_parsed_payload(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: {
            "content": "not-json",
            "parsed": [
                {
                    "knowledge_point": "隐私最小化",
                    "evidence": "上线前需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化"],
                    "dimension": "AI伦理安全",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            "structured_mode": "parse",
        },
    )

    result = question_agent.generate_question_plan_via_llm(
        content="【知识单元正文】\n推荐系统上线前，需要完成数据脱敏。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["local_qwen"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is False
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"
    assert result["usage"]["total_tokens"] == 5


def test_generate_question_plan_batch_via_llm_aligns_slot_indexed_results(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: {
            "content": json.dumps([
                {
                    "slot_index": 2,
                    "knowledge_point": "访问审计",
                    "evidence": "高风险访问前需要审批控制。",
                    "question_type": "true_false",
                    "stem_style": "直接知识型",
                    "scenario": "职场工作场景",
                    "answer_focus": "高风险访问前需要审批控制",
                    "distractor_focus": "混入跳过审批的错误做法",
                    "knowledge_tags": ["访问审计"],
                    "dimension": "AI伦理安全",
                },
                {
                    "slot_index": 1,
                    "knowledge_point": "隐私最小化",
                    "evidence": "上线前需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化"],
                    "dimension": "AI伦理安全",
                },
            ]),
            "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
        },
    )

    result = question_agent.generate_question_plan_batch_via_llm(
        slot_requests=[
            {"slot_index": 1, "question_type": "single_choice", "content": "【知识单元正文】\n上线前需要完成数据脱敏。"},
            {"slot_index": 2, "question_type": "true_false", "content": "【知识单元正文】\n高风险访问前需要审批控制。"},
        ],
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is False
    assert result["usage"]["total_tokens"] == 18
    assert len(result["question_plan"]) == 2
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"
    assert result["question_plan"][0]["question_type"] == "single_choice"
    assert result["question_plan"][1]["knowledge_point"] == "访问审计"
    assert result["question_plan"][1]["question_type"] == "true_false"


def test_generate_question_plan_batch_via_llm_prefers_parsed_payload(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: {
            "content": "not-json",
            "parsed": [
                {
                    "slot_index": 2,
                    "knowledge_point": "访问审计",
                    "evidence": "高风险访问前需要审批控制。",
                    "question_type": "true_false",
                    "stem_style": "直接知识型",
                    "scenario": "职场工作场景",
                    "answer_focus": "高风险访问前需要审批控制",
                    "distractor_focus": "混入跳过审批的错误做法",
                    "knowledge_tags": ["访问审计"],
                    "dimension": "AI伦理安全",
                },
                {
                    "slot_index": 1,
                    "knowledge_point": "隐私最小化",
                    "evidence": "上线前需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化"],
                    "dimension": "AI伦理安全",
                },
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
            "structured_mode": "parse",
        },
    )

    result = question_agent.generate_question_plan_batch_via_llm(
        slot_requests=[
            {"slot_index": 1, "question_type": "single_choice", "content": "【知识单元正文】\n上线前需要完成数据脱敏。"},
            {"slot_index": 2, "question_type": "true_false", "content": "【知识单元正文】\n高风险访问前需要审批控制。"},
        ],
        difficulty=3,
        model_config=get_compare_models(["local_qwen"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is False
    assert result["usage"]["total_tokens"] == 10
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"
    assert result["question_plan"][1]["knowledge_point"] == "访问审计"


def test_generate_question_plan_batch_via_llm_rebalances_duplicate_knowledge_points(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")

    def fake_build_question_plan(**kwargs):
        content = kwargs["content"]
        if "访问审计" in content:
            topic = "访问审计"
        else:
            topic = "隐私最小化"
        return [{
            "knowledge_point": topic,
            "evidence": f"{topic}证据",
            "question_type": kwargs["question_types"][0],
            "stem_style": "直接知识型",
            "scenario": "课堂学习场景",
            "answer_focus": topic,
            "distractor_focus": f"{topic}误区",
            "knowledge_tags": [topic],
            "dimension": "AI伦理安全",
        }]

    monkeypatch.setattr(question_agent, "build_question_plan", fake_build_question_plan)
    monkeypatch.setattr(
        question_agent,
        "_request_question_generation",
        lambda *args, **kwargs: {
            "parsed": [
                {
                    "slot_index": 1,
                    "knowledge_point": "隐私最小化",
                    "evidence": "上线前需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化"],
                    "dimension": "AI伦理安全",
                },
                {
                    "slot_index": 2,
                    "knowledge_point": "隐私最小化",
                    "evidence": "上线前需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化"],
                    "dimension": "AI伦理安全",
                },
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
            "structured_mode": "parse",
        },
    )

    result = question_agent.generate_question_plan_batch_via_llm(
        slot_requests=[
            {"slot_index": 1, "question_type": "single_choice", "content": "【知识单元正文】\n上线前需要完成数据脱敏。"},
            {"slot_index": 2, "question_type": "single_choice", "content": "【知识单元正文】\n高风险访问前需要审批控制和访问审计。"},
        ],
        difficulty=3,
        model_config=get_compare_models(["local_qwen"])[0],
        prompt_seed=42,
    )

    assert result["fallback_used"] is False
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"
    assert result["question_plan"][1]["knowledge_point"] == "访问审计"


def test_generate_questions_via_llm_uses_llm_planner_and_accumulates_usage(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    responses = [
        {
            "content": json.dumps([
                {
                    "knowledge_point": "隐私最小化",
                    "evidence": "推荐系统上线前，需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "职场工作场景（如项目管理、数据分析、内容创作、客户服务）",
                    "answer_focus": "先做数据脱敏与用途评估",
                    "distractor_focus": "混入扩大采集或跳过审计等常见误解",
                    "knowledge_tags": ["隐私最小化", "推荐系统"],
                    "dimension": "AI伦理安全",
                }
            ]),
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {
            "content": json.dumps([
                {
                    "question_type": "single_choice",
                    "dimension": "AI伦理安全",
                    "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                    "options": {"A": "只保留必要字段", "B": "扩大原始日志采集", "C": "长期保存未脱敏数据", "D": "关闭访问审计"},
                    "correct_answer": "A",
                    "explanation": "隐私最小化要求只保留完成任务所必需的数据字段。",
                    "knowledge_tags": ["隐私最小化", "推荐系统"],
                }
            ]),
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        },
    ]
    calls = []

    def fake_request(*args, **kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    monkeypatch.setattr(question_agent, "_request_question_generation", fake_request)

    result = question_agent.generate_questions_via_llm(
        content="【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
    )

    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.2
    assert calls[1]["temperature"] == 0.4
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"]["type"] == "json_schema"
    assert result["usage"]["total_tokens"] == 43
    assert result["fallback_used"] is False
    assert result["planner_fallback_used"] is False
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"


def test_generate_questions_via_llm_uses_injected_question_plan_without_calling_planner(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")

    def fail_planner(**kwargs):
        raise AssertionError("planner should not be called when question_plan is injected")

    monkeypatch.setattr(question_agent, "generate_question_plan_via_llm", fail_planner)

    captured_calls = []

    def fake_request(*args, **kwargs):
        captured_calls.append(kwargs)
        return {
            "content": json.dumps([
                {
                    "question_type": "single_choice",
                    "dimension": "AI伦理安全",
                    "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                    "options": {"A": "只保留必要字段", "B": "扩大原始日志采集", "C": "长期保存未脱敏数据", "D": "关闭访问审计"},
                    "correct_answer": "A",
                    "explanation": "隐私最小化要求只保留完成任务所必需的数据字段。",
                    "knowledge_tags": ["隐私最小化", "推荐系统"],
                }
            ]),
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        }

    monkeypatch.setattr(question_agent, "_request_question_generation", fake_request)

    injected_plan = [
        {
            "knowledge_point": "隐私最小化",
            "evidence": "推荐系统上线前，需要完成数据脱敏。",
            "question_type": "single_choice",
            "stem_style": "情景应用型",
            "scenario": "职场工作场景",
            "answer_focus": "先做数据脱敏与用途评估",
            "distractor_focus": "混入扩大采集或跳过审计等常见误解",
            "knowledge_tags": ["隐私最小化", "推荐系统"],
            "dimension": "AI伦理安全",
        }
    ]

    result = question_agent.generate_questions_via_llm(
        content="【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
        question_plan=injected_plan,
    )

    assert len(captured_calls) == 1
    assert captured_calls[0]["temperature"] == 0.4
    assert result["usage"]["total_tokens"] == 28
    assert result["planner_fallback_used"] is False
    assert result["question_plan"][0]["knowledge_point"] == "隐私最小化"


def test_generate_questions_via_llm_prefers_parsed_payload(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "generate_question_plan_via_llm",
        lambda **kwargs: {
            "question_plan": [
                {
                    "knowledge_point": "隐私最小化",
                    "evidence": "推荐系统上线前，需要完成数据脱敏。",
                    "question_type": "single_choice",
                    "stem_style": "情景应用型",
                    "scenario": "课堂学习场景",
                    "answer_focus": "先做数据脱敏",
                    "distractor_focus": "混入扩大采集等常见误解",
                    "knowledge_tags": ["隐私最小化", "推荐系统"],
                    "dimension": "AI伦理安全",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "fallback_used": False,
            "error": None,
        },
    )

    captured_calls = []

    def fake_request(*args, **kwargs):
        captured_calls.append(kwargs)
        return {
            "content": "not-json",
            "parsed": [
                {
                    "question_type": "single_choice",
                    "dimension": "AI伦理安全",
                    "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                    "options": {"A": "只保留必要字段", "B": "扩大原始日志采集", "C": "长期保存未脱敏数据", "D": "关闭访问审计"},
                    "correct_answer": "A",
                    "explanation": "隐私最小化要求只保留完成任务所必需的数据字段。",
                    "knowledge_tags": ["隐私最小化", "推荐系统"],
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            "structured_mode": "parse",
        }

    monkeypatch.setattr(question_agent, "_request_question_generation", fake_request)

    result = question_agent.generate_questions_via_llm(
        content="【知识单元正文】\n推荐系统上线前，需要完成数据脱敏、用途评估和访问审计配置。",
        question_types=["single_choice"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["local_qwen"])[0],
        prompt_seed=42,
    )

    assert len(captured_calls) == 1
    assert captured_calls[0]["parse_response_format"] is question_agent._GeneratedSingleChoiceResponseModel
    assert result["fallback_used"] is False
    assert result["usage"]["total_tokens"] == 43
    assert result["questions"][0]["stem"] == "推荐系统上线前，哪项做法最符合隐私最小化原则？"


def test_build_generated_question_parse_model_requires_options_for_choice_types():
    model = question_agent._build_generated_question_parse_model(["single_choice"])

    with pytest.raises(ValidationError):
        model.model_validate([
            {
                "question_type": "single_choice",
                "dimension": "AI基础知识",
                "stem": "推荐系统上线前，哪项做法最符合隐私最小化原则？",
                "correct_answer": "A",
                "explanation": "解释",
                "knowledge_tags": ["隐私最小化"],
            }
        ])


def test_build_question_response_format_is_type_aware():
    true_false_schema = question_agent._build_question_response_format(1, ["true_false"])
    item_schema = true_false_schema["json_schema"]["schema"]["items"]

    assert item_schema["properties"]["question_type"]["const"] == "true_false"
    assert item_schema["properties"]["options"]["properties"]["A"]["const"] == "正确"
    assert item_schema["properties"]["correct_answer"]["enum"] == ["A", "B"]

    fill_blank_schema = question_agent._build_question_response_format(1, ["fill_blank"])
    fill_blank_item = fill_blank_schema["json_schema"]["schema"]["items"]
    assert fill_blank_item["properties"]["options"]["type"] == "null"
    assert fill_blank_item["properties"]["stem"]["pattern"]


def test_generate_questions_via_llm_retries_strict_type_with_feedback(monkeypatch):
    monkeypatch.setattr(question_agent, "resolve_api_key", lambda model: "test-key")
    monkeypatch.setattr(
        question_agent,
        "generate_question_plan_via_llm",
        lambda **kwargs: {
            "question_plan": [
                {
                    "knowledge_point": "隐私审查",
                    "evidence": "推荐系统上线前仍需完成隐私审查。",
                    "question_type": "true_false",
                    "stem_style": "直接知识型",
                    "scenario": "职场工作场景",
                    "answer_focus": "仍需完成隐私审查",
                    "distractor_focus": "混入跳过审查的错误做法",
                    "knowledge_tags": ["隐私审查"],
                    "dimension": "AI伦理安全",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "fallback_used": False,
            "error": None,
        },
    )

    responses = [
        {
            "content": json.dumps([
                {
                    "question_type": "true_false",
                    "dimension": "AI伦理安全",
                    "stem": "以下哪项说法是正确的？",
                    "options": {"A": "正确", "B": "错误"},
                    "correct_answer": "A",
                    "explanation": "仍需合规审查。",
                    "knowledge_tags": ["隐私审查"],
                }
            ]),
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        },
        {
            "content": json.dumps([
                {
                    "question_type": "true_false",
                    "dimension": "AI伦理安全",
                    "stem": "推荐系统上线前仍需完成隐私审查。",
                    "options": {"A": "正确", "B": "错误"},
                    "correct_answer": "A",
                    "explanation": "即使数据来自公共来源，也不能跳过审查。",
                    "knowledge_tags": ["隐私审查"],
                }
            ]),
            "usage": {"prompt_tokens": 13, "completion_tokens": 8, "total_tokens": 21},
        },
    ]
    captured_prompts = []

    def fake_request(*args, **kwargs):
        captured_prompts.append(args[3])
        return responses[len(captured_prompts) - 1]

    monkeypatch.setattr(question_agent, "_request_question_generation", fake_request)

    result = question_agent.generate_questions_via_llm(
        content="【知识单元正文】\n推荐系统上线前仍需完成隐私审查。",
        question_types=["true_false"],
        count=1,
        difficulty=3,
        model_config=get_compare_models(["gemini"])[0],
        prompt_seed=42,
    )

    assert len(captured_prompts) == 2
    assert "【上次输出问题——本次必须修正】" in captured_prompts[1]
    assert "判断题题干必须是陈述句" in captured_prompts[1]
    assert result["fallback_used"] is False
    assert result["questions"][0]["stem"] == "推荐系统上线前仍需完成隐私审查。"


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
