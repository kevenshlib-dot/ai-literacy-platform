"""Registry for supported question-generation models."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Optional, Sequence

from app.core.config import settings

DEFAULT_COMPARE_MODEL_SLUGS = ("gemini", "qwen_max", "doubao", "local_qwen")


@dataclass(frozen=True)
class ModelConfig:
    slug: str
    display_name: str
    provider: str
    model_name: str
    api_key_env: Optional[str] = None
    base_url_env: Optional[str] = None
    default_base_url: Optional[str] = None
    default_api_key: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


COMPARE_MODELS: dict[str, ModelConfig] = {
    "gemini": ModelConfig(
        slug="gemini",
        display_name="Gemini 3 Pro Preview",
        provider="openai_compatible",
        model_name="gemini-3-pro-preview",
        api_key_env="GEMINI_API_KEY",
        base_url_env="GEMINI_BASE_URL",
    ),
    "qwen_max": ModelConfig(
        slug="qwen_max",
        display_name="Qwen3 Max 2026-01-23",
        provider="openai_compatible",
        model_name="qwen3-max-2026-01-23",
        api_key_env="DASHSCOPE_API_KEY",
        base_url_env="DASHSCOPE_BASE_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "doubao": ModelConfig(
        slug="doubao",
        display_name="Doubao Seed 2.0 Pro",
        provider="openai_compatible",
        model_name="doubao-seed-2-0-pro-260215",
        api_key_env="VOLCES_API_KEY",
        base_url_env="VOLCES_BASE_URL",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
    ),
    "local_qwen": ModelConfig(
        slug="local_qwen",
        display_name="Qwen3.5 35B A3B FP8 Local",
        provider="openai_compatible",
        model_name="Qwen/Qwen3.5-35B-A3B-FP8",
        api_key_env="LOCAL_QWEN_API_KEY",
        base_url_env="LOCAL_QWEN_BASE_URL",
        default_base_url="http://100.64.0.6:8100/v1",
        default_api_key="token-not-needed",
    ),
}


def _read_setting(name: Optional[str], default: Optional[str] = None) -> Optional[str]:
    if not name:
        return default
    value = getattr(settings, name, None)
    if value not in (None, ""):
        return value
    return os.getenv(name, default)


def get_default_model_config() -> ModelConfig:
    """Build the legacy single-model configuration from current app settings."""
    return ModelConfig(
        slug="default",
        display_name=settings.LLM_MODEL,
        provider="openai_compatible",
        model_name=settings.LLM_MODEL,
        default_base_url=settings.LLM_BASE_URL,
        default_api_key=settings.LLM_API_KEY,
    )


def get_compare_models(model_slugs: Optional[Sequence[str]] = None) -> list[ModelConfig]:
    """Return compare models in requested order."""
    slugs = list(model_slugs or DEFAULT_COMPARE_MODEL_SLUGS)
    models: list[ModelConfig] = []
    for slug in slugs:
        model = COMPARE_MODELS.get(slug)
        if not model:
            raise ValueError(f"Unknown model slug: {slug}")
        models.append(model)
    return models


def resolve_api_key(model: ModelConfig) -> Optional[str]:
    """Resolve API key for a model from settings/env/defaults."""
    return _read_setting(model.api_key_env, model.default_api_key)


def resolve_base_url(model: ModelConfig) -> Optional[str]:
    """Resolve base URL for a model from settings/env/defaults."""
    return _read_setting(model.base_url_env, model.default_base_url)
