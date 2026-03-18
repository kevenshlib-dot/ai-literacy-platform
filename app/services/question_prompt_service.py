import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_agent import (
    DEFAULT_QUESTION_SYSTEM_PROMPT,
    DEFAULT_QUESTION_USER_PROMPT_TEMPLATE,
    QUESTION_PROMPT_TEMPLATE_PLACEHOLDERS,
    TYPE_LABELS,
    build_question_prompt_context,
    render_user_prompt,
    validate_user_prompt_template,
)
from app.models.material import KnowledgeUnit, Material
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


def _normalize_type_distribution(type_distribution: dict) -> list[tuple[str, int]]:
    normalized_items: list[tuple[str, int]] = []
    for question_type, raw_count in (type_distribution or {}).items():
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        normalized_items.append((question_type, count))

    if not normalized_items:
        raise ValueError("请至少设置一种题型的数量")

    return normalized_items


def _render_prompt_preview_item(
    *,
    prompt_config: dict,
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str],
    custom_prompt: Optional[str],
    prompt_seed: int,
    title: str,
) -> dict:
    context = build_question_prompt_context(
        content=content,
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
        prompt_seed=prompt_seed,
    )
    return {
        "title": title,
        "rendered_user_prompt": render_user_prompt(
            prompt_config["user_prompt_template"],
            context,
        ),
    }


async def _build_material_prompt_preview_items(
    *,
    db: AsyncSession,
    material_ids: list[uuid.UUID],
    type_distribution: list[tuple[str, int]],
    max_units: int,
    prompt_config: dict,
    difficulty: int,
    bloom_level: Optional[str],
    custom_prompt: Optional[str],
    prompt_seed: int,
) -> list[dict]:
    rendered_items: list[dict] = []

    for material_id in material_ids:
        material = await db.get(Material, material_id)
        if material is None:
            raise ValueError(f"素材 {material_id} 不存在")

        result = await db.execute(
            select(KnowledgeUnit)
            .where(KnowledgeUnit.material_id == material_id)
            .order_by(KnowledgeUnit.chunk_index)
            .limit(max_units)
        )
        units = list(result.scalars().all())
        if not units:
            raise ValueError(f"素材《{material.title}》没有可用于预览的知识单元，请先完成解析")

        num_units = len(units)
        for question_type, total_count in type_distribution:
            base = total_count // num_units
            remainder = total_count % num_units
            for index, unit in enumerate(units):
                count_for_unit = base + (1 if index < remainder else 0)
                if count_for_unit <= 0:
                    continue
                rendered_items.append(
                    _render_prompt_preview_item(
                        prompt_config=prompt_config,
                        content=unit.content,
                        question_types=[question_type],
                        count=count_for_unit,
                        difficulty=difficulty,
                        bloom_level=bloom_level,
                        custom_prompt=custom_prompt,
                        prompt_seed=prompt_seed,
                        title=(
                            f"素材《{material.title}》 / 知识单元 {index + 1} / "
                            f"{TYPE_LABELS.get(question_type, question_type)} / {count_for_unit} 题"
                        ),
                    )
                )

    return rendered_items


def _build_free_prompt_preview_items(
    *,
    type_distribution: list[tuple[str, int]],
    prompt_config: dict,
    difficulty: int,
    bloom_level: Optional[str],
    custom_prompt: Optional[str],
    prompt_seed: int,
) -> list[dict]:
    return [
        _render_prompt_preview_item(
            prompt_config=prompt_config,
            content="",
            question_types=[question_type],
            count=count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
            prompt_seed=prompt_seed,
            title=f"自由出题 / {TYPE_LABELS.get(question_type, question_type)} / {count} 题",
        )
        for question_type, count in type_distribution
    ]


async def render_generation_prompt_preview(
    db: AsyncSession,
    user_id: uuid.UUID,
    type_distribution: dict,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
    prompt_seed: Optional[int] = None,
    material_ids: Optional[list[uuid.UUID]] = None,
    max_units: int = 10,
) -> dict:
    prompt_config = await resolve_generation_prompts(
        db=db,
        user_id=user_id,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )
    effective_prompt_seed = prompt_seed if prompt_seed is not None else uuid.uuid4().int % (2**31 - 1)
    normalized_type_distribution = _normalize_type_distribution(type_distribution)

    if material_ids:
        rendered_items = await _build_material_prompt_preview_items(
            db=db,
            material_ids=material_ids,
            type_distribution=normalized_type_distribution,
            max_units=max_units,
            prompt_config=prompt_config,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
            prompt_seed=effective_prompt_seed,
        )
        preview_note = (
            f"本次生成将按实际调用顺序向模型发送 {len(rendered_items)} 条用户提示词。"
            "已选素材模式下，题目会按“素材 / 知识单元 / 题型”拆分调用。"
        )
    else:
        rendered_items = _build_free_prompt_preview_items(
            type_distribution=normalized_type_distribution,
            prompt_config=prompt_config,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
            prompt_seed=effective_prompt_seed,
        )
        preview_note = (
            f"本次生成将按实际调用顺序向模型发送 {len(rendered_items)} 条用户提示词。"
            "自由出题模式下，题目会按题型拆分调用。"
        )

    return {
        "system_prompt": prompt_config["system_prompt"],
        "user_prompt_template": prompt_config["user_prompt_template"],
        "rendered_user_prompt": rendered_items[0]["rendered_user_prompt"] if len(rendered_items) == 1 else "",
        "rendered_user_prompts": rendered_items,
        "placeholders": get_prompt_placeholders(),
        "preview_note": preview_note,
        "prompt_seed": effective_prompt_seed,
    }
