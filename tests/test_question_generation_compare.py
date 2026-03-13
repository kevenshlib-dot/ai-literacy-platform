"""Unit tests for multi-model question generation comparison support."""

import json
import uuid
from pathlib import Path

import pytest

from app.agents import question_agent
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

    def fake_openai(model_config, api_key, user_prompt, max_tokens, empty_usage):
        called["slug"] = model_config.slug
        called["api_key"] = api_key
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
        user_prompt="prompt",
        max_tokens=512,
        empty_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )

    assert called == {
        "slug": "gemini",
        "api_key": "test-key",
        "user_prompt": "prompt",
        "max_tokens": 512,
    }
    assert result["content"] == "[]"


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
