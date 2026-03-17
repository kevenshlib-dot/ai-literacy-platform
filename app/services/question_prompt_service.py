import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_agent import (
    DEFAULT_QUESTION_SYSTEM_PROMPT,
    DEFAULT_QUESTION_USER_PROMPT_TEMPLATE,
    QUESTION_PROMPT_TEMPLATE_PLACEHOLDERS,
    validate_user_prompt_template,
)
from app.models.question_prompt_profile import QuestionPromptProfile

PROMPT_TEXT_MAX_LENGTH = 20000


def get_default_prompt_config() -> dict:
    return {
        "system_prompt": DEFAULT_QUESTION_SYSTEM_PROMPT,
        "user_prompt_template": DEFAULT_QUESTION_USER_PROMPT_TEMPLATE,
    }


def get_prompt_placeholders() -> list[dict]:
    return QUESTION_PROMPT_TEMPLATE_PLACEHOLDERS


def _normalize_prompt_text(value: str, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    if len(normalized) > PROMPT_TEXT_MAX_LENGTH:
        raise ValueError(f"{field_name} 不能超过 {PROMPT_TEXT_MAX_LENGTH} 个字符")
    return normalized


def validate_prompt_config(system_prompt: str, user_prompt_template: str) -> dict:
    normalized_system_prompt = _normalize_prompt_text(system_prompt, "system_prompt")
    normalized_user_prompt_template = _normalize_prompt_text(
        user_prompt_template,
        "user_prompt_template",
    )
    validate_user_prompt_template(normalized_user_prompt_template)
    return {
        "system_prompt": normalized_system_prompt,
        "user_prompt_template": normalized_user_prompt_template,
    }


async def get_prompt_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Optional[QuestionPromptProfile]:
    result = await db.execute(
        select(QuestionPromptProfile).where(QuestionPromptProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_effective_prompt_config(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    defaults = get_default_prompt_config()
    profile = await get_prompt_profile(db, user_id)
    if not profile:
        return {
            **defaults,
            "has_saved_config": False,
            "defaults": defaults,
            "placeholders": get_prompt_placeholders(),
        }

    return {
        "system_prompt": profile.system_prompt,
        "user_prompt_template": profile.user_prompt_template,
        "has_saved_config": True,
        "defaults": defaults,
        "placeholders": get_prompt_placeholders(),
    }


async def save_prompt_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    system_prompt: str,
    user_prompt_template: str,
) -> QuestionPromptProfile:
    validated = validate_prompt_config(system_prompt, user_prompt_template)
    profile = await get_prompt_profile(db, user_id)
    if profile is None:
        profile = QuestionPromptProfile(user_id=user_id, **validated)
        db.add(profile)
    else:
        profile.system_prompt = validated["system_prompt"]
        profile.user_prompt_template = validated["user_prompt_template"]
    await db.flush()
    return profile


async def delete_prompt_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    profile = await get_prompt_profile(db, user_id)
    if profile is None:
        return False
    await db.delete(profile)
    await db.flush()
    return True


async def resolve_generation_prompts(
    db: AsyncSession,
    user_id: uuid.UUID,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> dict:
    if system_prompt is not None or user_prompt_template is not None:
        effective = await get_effective_prompt_config(db, user_id)
        resolved_system_prompt = (
            system_prompt if system_prompt is not None else effective["system_prompt"]
        )
        resolved_user_prompt_template = (
            user_prompt_template
            if user_prompt_template is not None
            else effective["user_prompt_template"]
        )
        return validate_prompt_config(
            resolved_system_prompt,
            resolved_user_prompt_template,
        )

    effective = await get_effective_prompt_config(db, user_id)
    return {
        "system_prompt": effective["system_prompt"],
        "user_prompt_template": effective["user_prompt_template"],
    }
