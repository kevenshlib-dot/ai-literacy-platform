"""Question service - handles question CRUD, generation, and review."""
import asyncio
from difflib import SequenceMatcher
import logging
import re
import time
import uuid
from collections.abc import Hashable
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionType, QuestionStatus, BloomLevel, ReviewRecord
from app.models.material import Material, KnowledgeUnit, MaterialFormat
from app.models.material_generation import MaterialGenerationRun, MaterialGenerationRunUnit
from app.agents.question_agent import (
    MATERIAL_GENERATION_MAX_ATTEMPTS,
    _validate_generated_question_set,
    classify_dimension,
    generate_question_plan_batch_via_llm,
    generate_questions_via_llm,
)
from app.agents.model_registry import ModelConfig
from app.agents.review_agent import ai_review_question
from app.services.preview_review_store import preview_review_store

logger = logging.getLogger(__name__)
MATERIAL_PLACEHOLDER_MARKERS = ("待OCR处理", "待转录处理", "待ASR处理")
SELECTION_MODE_STABLE = "stable"
SELECTION_MODE_COVERAGE = "coverage"
SUPPORTED_SELECTION_MODES = {SELECTION_MODE_STABLE, SELECTION_MODE_COVERAGE}
COVERAGE_HISTORY_WINDOW_SIZE = 3
COVERAGE_RECENCY_PENALTIES = {
    1: 3.0,
    2: 1.5,
    3: 1.0,
}
COVERAGE_PENALTY_CAP = 4.0
PREVIEW_GENERATION_CONCURRENCY = 3
BLOOM_LEVEL_ORDER = {
    "remember": 0,
    "understand": 1,
    "apply": 2,
    "analyze": 3,
    "evaluate": 4,
    "create": 5,
}
BLOOM_LEVEL_LABELS = {
    "remember": "记忆",
    "understand": "理解",
    "apply": "应用",
    "analyze": "分析",
    "evaluate": "评价",
    "create": "创造",
}


def _coerce_uuid(value: Optional[uuid.UUID | str]) -> Optional[uuid.UUID]:
    """Accept UUID objects or strings from preview payloads."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def _material_format_value(material: Material) -> str:
    value = getattr(material, "format", None)
    return value.value if hasattr(value, "value") else str(value or "")


def _contains_generation_placeholder(text: Optional[str]) -> bool:
    return any(marker in (text or "") for marker in MATERIAL_PLACEHOLDER_MARKERS)


def _normalize_selection_mode(selection_mode: Optional[str]) -> str:
    normalized = (selection_mode or SELECTION_MODE_STABLE).strip().lower()
    if normalized not in SUPPORTED_SELECTION_MODES:
        raise ValueError("selection_mode 必须是 stable 或 coverage")
    return normalized


def _ensure_knowledge_unit_generation_ready(ku: KnowledgeUnit) -> None:
    if _contains_generation_placeholder(ku.content):
        raise ValueError("知识单元仍是占位解析结果，请先完成OCR/ASR后再生成试题")


def _ensure_material_generation_ready(material: Material, units: list[KnowledgeUnit]) -> None:
    material_format = _material_format_value(material)
    if material_format in (
        MaterialFormat.IMAGE.value,
        MaterialFormat.VIDEO.value,
        MaterialFormat.AUDIO.value,
    ):
        raise ValueError("当前素材仅有占位解析结果，请先完成OCR/ASR后再生成试题")
    if any(_contains_generation_placeholder(unit.content) for unit in units):
        raise ValueError("素材知识片段仍包含占位解析文本，请先完成OCR/ASR后再生成试题")


def _format_keywords(keywords: object) -> str:
    if not keywords:
        return ""
    if isinstance(keywords, dict):
        values = []
        for value in keywords.values():
            if isinstance(value, list):
                values.extend(str(item) for item in value if str(item).strip())
            elif str(value).strip():
                values.append(str(value))
        return "、".join(values)
    if isinstance(keywords, list):
        return "、".join(str(item) for item in keywords if str(item).strip())
    return str(keywords).strip()


def _build_knowledge_unit_prompt_content(ku: KnowledgeUnit) -> str:
    parts: list[str] = []
    if ku.title:
        parts.append(f"【知识单元标题】\n{ku.title}")
    if ku.summary:
        parts.append(f"【知识单元摘要】\n{ku.summary}")
    keyword_text = _format_keywords(ku.keywords)
    if keyword_text:
        parts.append(f"【知识关键词】\n{keyword_text}")
    parts.append(f"【知识单元正文】\n{ku.content}")
    return "\n\n".join(part for part in parts if part.strip())


def _build_knowledge_unit_planner_content(ku: KnowledgeUnit, body_limit: int = 360) -> str:
    parts: list[str] = []
    if ku.title:
        parts.append(f"【知识单元标题】\n{ku.title}")
    if ku.summary:
        parts.append(f"【知识单元摘要】\n{ku.summary}")
    keyword_text = _format_keywords(ku.keywords)
    if keyword_text:
        parts.append(f"【知识关键词】\n{keyword_text}")
    body = (ku.content or "").strip()
    if len(body) > body_limit:
        body = f"{body[:body_limit].rstrip()}..."
    parts.append(f"【知识单元正文】\n{body}")
    return "\n\n".join(part for part in parts if part.strip())


def _knowledge_unit_signature(ku: KnowledgeUnit) -> str:
    base = " ".join(
        part.strip()
        for part in [
            ku.title or "",
            ku.summary or "",
            (ku.content or "")[:160],
        ]
        if part and part.strip()
    )
    normalized = re.sub(r"\s+", "", base.lower())
    normalized = re.sub(r"[，。！？；：、“”‘’\"'（）()、,.!?;:\-_/]", "", normalized)
    return normalized[:160]


def _knowledge_unit_keyword_count(keywords: object) -> int:
    if not keywords:
        return 0
    if isinstance(keywords, dict):
        total = 0
        for value in keywords.values():
            if isinstance(value, list):
                total += sum(1 for item in value if str(item).strip())
            elif str(value).strip():
                total += 1
        return total
    if isinstance(keywords, list):
        return sum(1 for item in keywords if str(item).strip())
    return 1 if str(keywords).strip() else 0


def _knowledge_unit_information_score(ku: KnowledgeUnit) -> float:
    content = (ku.content or "").strip()
    content_length = len(content)
    sentence_count = len(re.findall(r"[。！？.!?]", content))
    keyword_count = _knowledge_unit_keyword_count(ku.keywords)

    score = 1.0
    score += min(content_length, 1600) / 240
    score += min(sentence_count, 8) * 0.15
    if ku.title:
        score += 1.0
    if ku.summary:
        score += 1.25
    score += min(keyword_count, 6) * 0.35
    if ku.difficulty:
        score += max(0, ku.difficulty - 2) * 0.2
    if content_length < 120:
        score *= 0.65
    return max(score, 0.1)


def _select_generation_units(
    units: list[KnowledgeUnit],
    max_units: Optional[int] = None,
    selection_mode: str = SELECTION_MODE_STABLE,
    coverage_penalties: Optional[dict[uuid.UUID, float]] = None,
) -> list[KnowledgeUnit]:
    if not units:
        return []

    normalized_selection_mode = _normalize_selection_mode(selection_mode)
    penalty_map = coverage_penalties or {}
    deduped: dict[str, tuple[float, float, KnowledgeUnit]] = {}
    for ku in units:
        base_score = _knowledge_unit_information_score(ku)
        penalty = 0.0
        if normalized_selection_mode == SELECTION_MODE_COVERAGE:
            penalty = max(float(penalty_map.get(ku.id, 0.0)), 0.0)
        score = base_score - penalty
        signature = _knowledge_unit_signature(ku) or f"ku:{ku.id}"
        existing = deduped.get(signature)
        if existing is None or (score, base_score) > (existing[0], existing[1]):
            deduped[signature] = (score, base_score, ku)

    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            -item[0],
            -item[1],
            item[2].chunk_index if item[2].chunk_index is not None else 10**9,
            str(item[2].id),
        ),
    )
    limited = ranked[:max_units] if max_units else ranked
    selected = [ku for _, _, ku in limited]
    return sorted(
        selected,
        key=lambda ku: (
            ku.chunk_index if ku.chunk_index is not None else 10**9,
            str(ku.id),
        ),
    )


async def _load_material_generation_penalties(
    db: AsyncSession,
    material_id: uuid.UUID,
    history_window_size: int = COVERAGE_HISTORY_WINDOW_SIZE,
) -> tuple[dict[uuid.UUID, float], int]:
    run_result = await db.execute(
        select(MaterialGenerationRun.id)
        .where(MaterialGenerationRun.material_id == material_id)
        .order_by(MaterialGenerationRun.created_at.desc(), MaterialGenerationRun.id.desc())
        .limit(history_window_size)
    )
    recent_run_ids = list(run_result.scalars().all())
    if not recent_run_ids:
        return {}, 0

    run_recency_rank = {
        run_id: index + 1
        for index, run_id in enumerate(recent_run_ids)
    }
    unit_result = await db.execute(
        select(
            MaterialGenerationRunUnit.run_id,
            MaterialGenerationRunUnit.knowledge_unit_id,
        ).where(MaterialGenerationRunUnit.run_id.in_(recent_run_ids))
    )

    penalties: dict[uuid.UUID, float] = {}
    for run_id, knowledge_unit_id in unit_result.all():
        recency_rank = run_recency_rank.get(run_id)
        if recency_rank is None:
            continue
        penalties[knowledge_unit_id] = penalties.get(knowledge_unit_id, 0.0) + (
            COVERAGE_RECENCY_PENALTIES.get(recency_rank, 0.0)
        )

    return (
        {
            knowledge_unit_id: min(penalty, COVERAGE_PENALTY_CAP)
            for knowledge_unit_id, penalty in penalties.items()
            if penalty > 0
        },
        len(recent_run_ids),
    )


async def _select_material_generation_units(
    db: AsyncSession,
    material_id: uuid.UUID,
    units: list[KnowledgeUnit],
    max_units: Optional[int] = None,
    selection_mode: str = SELECTION_MODE_STABLE,
) -> tuple[list[KnowledgeUnit], dict[str, int | str]]:
    normalized_selection_mode = _normalize_selection_mode(selection_mode)
    penalties: dict[uuid.UUID, float] = {}
    history_run_count = 0
    if normalized_selection_mode == SELECTION_MODE_COVERAGE:
        penalties, history_run_count = await _load_material_generation_penalties(
            db=db,
            material_id=material_id,
        )

    selected = _select_generation_units(
        units,
        max_units=max_units,
        selection_mode=normalized_selection_mode,
        coverage_penalties=penalties,
    )
    return selected, {
        "selection_mode": normalized_selection_mode,
        "history_window_size": COVERAGE_HISTORY_WINDOW_SIZE if normalized_selection_mode == SELECTION_MODE_COVERAGE else 0,
        "cooled_unit_count": len(penalties),
        "history_run_count": history_run_count,
    }


def _count_requested_questions(
    type_distribution: dict[str, int] | list[tuple[str, int]],
) -> int:
    items = type_distribution.items() if isinstance(type_distribution, dict) else type_distribution
    return sum(count for _, count in items if count > 0)


def _estimate_suggested_question_target(total_units: int, total_content_length: int) -> int:
    if total_units <= 0:
        return 0
    if total_units <= 3:
        total_questions = min(max(total_units * 3, 6), 12)
    elif total_units <= 8:
        total_questions = min(total_units * 3, 25)
    else:
        total_questions = min(total_units * 3, 40)

    if total_content_length > 5000:
        total_questions = min(total_questions + 5, 40)
    return total_questions


def _effective_material_generation_max_units(
    max_units: Optional[int],
    requested_total: int,
) -> Optional[int]:
    if requested_total <= 0:
        return max_units
    if max_units is None:
        return requested_total
    return max(max_units, requested_total)


def _ensure_material_unique_generation_capacity(
    units: list[KnowledgeUnit],
    requested_total: int,
) -> None:
    if requested_total <= 0:
        return
    unique_unit_count = len(units)
    if unique_unit_count < requested_total:
        raise ValueError(
            f"当前素材去重后仅有 {unique_unit_count} 个可用知识点，不足以生成 {requested_total} 道互不重复知识点的题目"
        )


async def _prepare_material_generation_units(
    *,
    db: AsyncSession,
    material: Material,
    units: list[KnowledgeUnit],
    requested_total: int,
    max_units: Optional[int],
    selection_mode: str,
) -> tuple[list[KnowledgeUnit], dict[str, int | str]]:
    selected_units, selection_stats = await _select_material_generation_units(
        db=db,
        material_id=material.id,
        units=units,
        max_units=_effective_material_generation_max_units(max_units, requested_total),
        selection_mode=selection_mode,
    )
    if not selected_units:
        raise ValueError("该素材没有知识单元，请先解析素材")
    _ensure_material_generation_ready(material, selected_units)
    _ensure_material_unique_generation_capacity(selected_units, requested_total)
    return selected_units, selection_stats


async def _record_material_generation_run(
    db: AsyncSession,
    *,
    material_id: uuid.UUID,
    knowledge_unit_ids: list[uuid.UUID | str],
    selection_mode: str = SELECTION_MODE_STABLE,
    created_by: Optional[uuid.UUID] = None,
) -> Optional[MaterialGenerationRun]:
    normalized_selection_mode = _normalize_selection_mode(selection_mode)
    ordered_unit_ids: list[uuid.UUID] = []
    seen_unit_ids: set[uuid.UUID] = set()
    for raw_unit_id in knowledge_unit_ids:
        unit_id = _coerce_uuid(raw_unit_id)
        if unit_id is None or unit_id in seen_unit_ids:
            continue
        ordered_unit_ids.append(unit_id)
        seen_unit_ids.add(unit_id)

    if not ordered_unit_ids:
        return None

    run = MaterialGenerationRun(
        material_id=material_id,
        selection_mode=normalized_selection_mode,
        created_by=created_by,
    )
    db.add(run)
    await db.flush()

    for selected_order, knowledge_unit_id in enumerate(ordered_unit_ids):
        db.add(
            MaterialGenerationRunUnit(
                run_id=run.id,
                knowledge_unit_id=knowledge_unit_id,
                selected_order=selected_order,
            )
        )
    await db.flush()
    return run


def _build_material_generation_slots(
    units: list[KnowledgeUnit],
    type_distribution: dict[str, int],
    unit_type_plan: dict[uuid.UUID, dict[str, int]],
) -> list[dict]:
    slots: list[dict] = []
    for question_type, total_count in type_distribution.items():
        if total_count <= 0:
            continue
        for ku in units:
            count_for_unit = unit_type_plan.get(ku.id, {}).get(question_type, 0)
            if count_for_unit <= 0:
                continue
            for slot_offset in range(count_for_unit):
                slots.append({
                    "slot_index": len(slots) + 1,
                    "question_type": question_type,
                    "knowledge_unit_id": ku.id,
                    "knowledge_unit": ku,
                    "planner_content": _build_knowledge_unit_planner_content(ku),
                    "generator_content": _build_knowledge_unit_prompt_content(ku),
                    "slot_offset": slot_offset,
                })
    return slots


def _build_slot_batch_generator_content(slots: list[dict]) -> str:
    sections: list[str] = []
    for slot in slots:
        sections.append(
            f"【题目槽位 {slot['slot_index']} 参考素材】\n"
            f"{slot['generator_content']}"
        )
    return "\n\n".join(sections)


async def _run_generation_jobs(
    jobs: list[dict],
    max_concurrency: int = PREVIEW_GENERATION_CONCURRENCY,
) -> list[dict]:
    if not jobs:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[Optional[dict]] = [None] * len(jobs)

    async def _run(index: int, kwargs: dict) -> None:
        async with semaphore:
            results[index] = await asyncio.to_thread(generate_questions_via_llm, **kwargs)

    await asyncio.gather(*(_run(index, kwargs) for index, kwargs in enumerate(jobs)))
    return [result or {} for result in results]


def _material_generation_weight(units: list[KnowledgeUnit]) -> float:
    return sum(_knowledge_unit_information_score(ku) for ku in units) or float(len(units) or 1)


def _allocate_counts_by_weights(
    weighted_items: list[tuple[Hashable, float, tuple]],
    total_count: int,
) -> dict[Hashable, int]:
    if total_count <= 0 or not weighted_items:
        return {key: 0 for key, _, _ in weighted_items}

    normalized_items = [
        (key, max(float(weight), 0.1), tie_breaker)
        for key, weight, tie_breaker in weighted_items
    ]
    total_weight = sum(weight for _, weight, _ in normalized_items)
    raw_allocations = [
        (key, (total_count * weight / total_weight), tie_breaker)
        for key, weight, tie_breaker in normalized_items
    ]
    allocations = {key: int(raw) for key, raw, _ in raw_allocations}
    remainder = total_count - sum(allocations.values())
    ranked_remainders = sorted(
        raw_allocations,
        key=lambda item: (-(item[1] - int(item[1])), item[2]),
    )
    for key, _, _ in ranked_remainders[:remainder]:
        allocations[key] += 1
    return allocations


def _plan_unit_type_distribution(
    units: list[KnowledgeUnit],
    type_distribution: dict[str, int],
) -> dict[uuid.UUID, dict[str, int]]:
    plan = {ku.id: {} for ku in units}
    positive_distribution = [
        (question_type, total_count)
        for question_type, total_count in type_distribution.items()
        if total_count > 0
    ]
    if not units or not positive_distribution:
        return plan

    unit_scores = {
        ku.id: _knowledge_unit_information_score(ku)
        for ku in units
    }
    weighted_items = [
        (
            ku.id,
            unit_scores[ku.id],
            (
                -unit_scores[ku.id],
                ku.chunk_index if ku.chunk_index is not None else 10**9,
                str(ku.id),
            ),
        )
        for ku in units
    ]

    remaining_by_type = {
        question_type: total_count
        for question_type, total_count in positive_distribution
    }
    type_order = [question_type for question_type, _ in positive_distribution]
    available_unit_ids: set[uuid.UUID] = {ku.id for ku in units}

    while any(count > 0 for count in remaining_by_type.values()) and available_unit_ids:
        progressed = False
        for question_type in type_order:
            if remaining_by_type[question_type] <= 0:
                continue

            chosen_unit_id = next(
                (
                    ku_id
                    for ku_id, _, _ in weighted_items
                    if ku_id in available_unit_ids
                ),
                None,
            )
            if chosen_unit_id is None:
                continue

            plan[chosen_unit_id][question_type] = 1
            available_unit_ids.remove(chosen_unit_id)
            remaining_by_type[question_type] -= 1
            progressed = True

        if not progressed:
            break

    return plan


def _normalize_stem_for_dedupe(stem: str) -> str:
    normalized = (stem or "").strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[，。！？；：、“”‘’\"'（）()、,.!?;:\-_/]", "", normalized)
    return normalized


def _collect_duplicate_stems(raw_questions: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for raw in raw_questions:
        stem = str(raw.get("stem", "") or "").strip()
        signature = _normalize_stem_for_dedupe(stem)
        if not signature:
            continue
        if signature in seen:
            duplicates.append(stem or seen[signature])
        else:
            seen[signature] = stem
    return list(dict.fromkeys(duplicates))


def _question_tag_set(question: dict) -> set[str]:
    tags = question.get("knowledge_tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        _normalize_stem_for_dedupe(str(tag))
        for tag in tags
        if str(tag).strip()
    }


def _question_tag_overlap(left: dict, right: dict) -> float:
    left_tags = _question_tag_set(left)
    right_tags = _question_tag_set(right)
    if not left_tags or not right_tags:
        return 0.0
    return len(left_tags & right_tags) / len(left_tags | right_tags)


def _question_similarity(left: dict, right: dict) -> float:
    left_stem = _normalize_stem_for_dedupe(str(left.get("stem", "") or ""))
    right_stem = _normalize_stem_for_dedupe(str(right.get("stem", "") or ""))
    if not left_stem or not right_stem:
        return 0.0

    stem_ratio = SequenceMatcher(None, left_stem, right_stem).ratio()
    tag_overlap = _question_tag_overlap(left, right)

    same_type_bonus = 0.05 if left.get("question_type") == right.get("question_type") else 0.0
    same_source_bonus = 0.08 if (
        left.get("source_knowledge_unit_id")
        and left.get("source_knowledge_unit_id") == right.get("source_knowledge_unit_id")
    ) else 0.0
    same_material_bonus = 0.04 if (
        left.get("source_material_id")
        and left.get("source_material_id") == right.get("source_material_id")
    ) else 0.0

    return max(
        stem_ratio,
        (
            (stem_ratio * 0.75)
            + (tag_overlap * 0.25)
            + same_type_bonus
            + same_source_bonus
            + same_material_bonus
        ),
    )


def _is_near_duplicate_pair(left: dict, right: dict, similarity: Optional[float] = None) -> bool:
    similarity = similarity if similarity is not None else _question_similarity(left, right)
    tag_overlap = _question_tag_overlap(left, right)
    return similarity >= 0.84 or (similarity >= 0.72 and tag_overlap >= 0.5)


def _truncate_text(text: str, limit: int = 28) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


def _collect_near_duplicate_pairs(raw_questions: list[dict]) -> list[str]:
    warnings: list[str] = []
    for left_index in range(len(raw_questions)):
        for right_index in range(left_index + 1, len(raw_questions)):
            left = raw_questions[left_index]
            right = raw_questions[right_index]
            similarity = _question_similarity(left, right)
            if _is_near_duplicate_pair(left, right, similarity):
                warnings.append(
                    f"第{left_index + 1}题与第{right_index + 1}题疑似近重复（相似度 {similarity:.2f}）"
                )
    return list(dict.fromkeys(warnings))


async def _collect_existing_duplicate_stems(
    db: AsyncSession,
    raw_questions: list[dict],
) -> list[str]:
    stems = sorted(
        {
            str(raw.get("stem", "") or "").strip()
            for raw in raw_questions
            if str(raw.get("stem", "") or "").strip()
        }
    )
    if not stems:
        return []
    result = await db.execute(select(Question.stem).where(Question.stem.in_(stems)))
    return sorted({stem for stem, in result.all() if stem})


async def _load_existing_question_candidates(
    db: AsyncSession,
    raw_questions: list[dict],
) -> dict[str, list[dict]]:
    requested_types: set[QuestionType] = set()
    for raw in raw_questions:
        raw_type = str(raw.get("question_type", "") or "").strip()
        if not raw_type:
            continue
        try:
            requested_types.add(QuestionType(raw_type))
        except ValueError:
            continue

    if not requested_types:
        return {}

    result = await db.execute(
        select(
            Question.id,
            Question.stem,
            Question.question_type,
            Question.dimension,
            Question.knowledge_tags,
            Question.source_material_id,
            Question.source_knowledge_unit_id,
        ).where(Question.question_type.in_(sorted(requested_types, key=lambda item: item.value)))
    )

    candidates_by_type: dict[str, list[dict]] = {}
    for row in result.all():
        question_type = row.question_type.value if hasattr(row.question_type, "value") else str(row.question_type)
        candidates_by_type.setdefault(question_type, []).append({
            "id": row.id,
            "stem": row.stem,
            "question_type": question_type,
            "dimension": row.dimension,
            "knowledge_tags": row.knowledge_tags,
            "source_material_id": str(row.source_material_id) if row.source_material_id else None,
            "source_knowledge_unit_id": str(row.source_knowledge_unit_id) if row.source_knowledge_unit_id else None,
        })
    return candidates_by_type


async def _collect_existing_near_duplicate_pairs(
    db: AsyncSession,
    raw_questions: list[dict],
) -> list[str]:
    candidates_by_type = await _load_existing_question_candidates(db, raw_questions)
    if not candidates_by_type:
        return []

    warnings: list[str] = []
    exact_signatures = {
        _normalize_stem_for_dedupe(str(raw.get("stem", "") or ""))
        for raw in raw_questions
        if str(raw.get("stem", "") or "").strip()
    }

    for index, raw in enumerate(raw_questions, start=1):
        question_type = str(raw.get("question_type", "") or "").strip()
        if not question_type:
            continue

        for candidate in candidates_by_type.get(question_type, []):
            candidate_signature = _normalize_stem_for_dedupe(candidate.get("stem", ""))
            if candidate_signature in exact_signatures:
                continue

            similarity = _question_similarity(raw, candidate)
            if not _is_near_duplicate_pair(raw, candidate, similarity):
                continue

            warnings.append(
                "第"
                f"{index}题与题库已有题目“{_truncate_text(candidate['stem'])}”"
                f"疑似近重复（相似度 {similarity:.2f}）"
            )
            break

    return list(dict.fromkeys(warnings))


def _normalize_review_overall_score(review: dict) -> float:
    try:
        return float(review.get("overall_score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_bloom_level(value: object) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in BLOOM_LEVEL_ORDER else None


def _label_bloom_level(value: Optional[str]) -> str:
    if not value:
        return "未标注"
    return BLOOM_LEVEL_LABELS.get(value, value)


def _estimate_bloom_level(question: dict) -> tuple[str, list[str]]:
    stem = str(question.get("stem", "") or "").strip()
    question_type = str(question.get("question_type", "") or "").strip()
    correct_answer = str(question.get("correct_answer", "") or "").strip()
    reasons: list[str] = []

    keyword_rules = [
        ("create", ("设计", "制定", "提出", "构建", "撰写", "生成", "规划")),
        ("evaluate", ("评价", "评估", "最合适", "最合理", "最佳", "优先", "是否合理", "是否恰当", "利弊")),
        ("analyze", ("分析", "比较", "原因", "影响", "区别", "推断", "拆解", "关联")),
        ("apply", ("场景", "案例", "做法", "措施", "处理", "操作", "应用", "结合", "如何", "根据")),
        ("understand", ("解释", "说明", "概括", "意味着", "表明", "理解")),
        ("remember", ("是什么", "哪项", "下列", "以下", "简称", "定义", "判断")),
    ]
    for level, keywords in keyword_rules:
        if any(keyword in stem for keyword in keywords):
            reasons.append(f"题干包含“{next(keyword for keyword in keywords if keyword in stem)}”等 { _label_bloom_level(level) } 线索")
            return level, reasons

    if question_type == "true_false":
        reasons.append("判断题默认更接近记忆/理解层次")
        return "remember", reasons
    if question_type == "fill_blank":
        reasons.append("填空题默认更接近记忆层次")
        return "remember", reasons
    if question_type == "multiple_choice":
        reasons.append("多选题默认更接近应用层次")
        return "apply", reasons
    if question_type == "short_answer":
        reasons.append("简答题默认更接近分析层次")
        return "analyze", reasons
    if question_type == "essay":
        reasons.append("论述题默认更接近评价层次")
        return "evaluate", reasons
    if question_type == "sjt":
        reasons.append("情境判断题默认更接近应用层次")
        return "apply", reasons
    if correct_answer and len(correct_answer) > 12:
        reasons.append("答案较长，默认上调到理解层次")
        return "understand", reasons

    reasons.append("题型与题干未出现高阶认知线索，按理解层次估计")
    return "understand", reasons


def _estimate_question_difficulty(
    question: dict,
    estimated_bloom_level: Optional[str] = None,
) -> tuple[int, list[str]]:
    stem = str(question.get("stem", "") or "").strip()
    question_type = str(question.get("question_type", "") or "").strip()
    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    option_values = [str(value).strip() for value in options.values() if str(value).strip()]
    correct_answer = str(question.get("correct_answer", "") or "").strip()
    reasons: list[str] = []

    base_map = {
        "true_false": 1.0,
        "single_choice": 2.0,
        "fill_blank": 2.0,
        "multiple_choice": 3.0,
        "short_answer": 4.0,
        "essay": 5.0,
        "sjt": 4.0,
    }
    score = base_map.get(question_type, 3.0)
    reasons.append(f"{question_type or 'unknown'} 题型基线难度为 {score:.0f}")

    if len(stem) >= 32:
        score += 0.4
        reasons.append("题干较长，理解成本更高")
    if any(keyword in stem for keyword in ("场景", "案例", "分析", "比较", "原因", "影响", "最合适", "最合理", "为什么", "如何", "综合", "步骤", "策略")):
        score += 0.8
        reasons.append("题干包含推理或场景判断要求")
    if option_values:
        average_option_length = sum(len(value) for value in option_values) / max(len(option_values), 1)
        if len(option_values) >= 4 and average_option_length >= 8:
            score += 0.3
            reasons.append("选项较长且数量完整")
    if question_type == "multiple_choice":
        unique_answers = {char for char in correct_answer if char.isalpha()}
        if len(unique_answers) >= 3:
            score += 0.4
            reasons.append("多选题正确选项较多")
    if question_type == "true_false" and len(stem) < 18:
        score -= 0.4
        reasons.append("判断题题干较短，整体偏易")
    if question_type in ("short_answer", "essay") and len(correct_answer) >= 30:
        score += 0.4
        reasons.append("主观题参考答案较长")

    estimated_bloom_level = _normalize_bloom_level(estimated_bloom_level)
    if estimated_bloom_level in ("analyze", "evaluate", "create"):
        score += 0.5
        reasons.append("认知层次估计偏高，难度上调")
    elif estimated_bloom_level == "remember":
        score -= 0.3
        reasons.append("认知层次估计偏低，难度下调")

    return max(1, min(5, round(score))), reasons


def _review_preview_calibration(raw_questions: list[dict]) -> dict:
    warnings: list[str] = []
    reviewed_count = 0
    calibration_warning_count = 0
    difficulty_mismatch_count = 0
    difficulty_severe_mismatch_count = 0
    bloom_mismatch_count = 0
    bloom_severe_mismatch_count = 0

    for index, question in enumerate(raw_questions, start=1):
        reviewed_count += 1
        requested_difficulty = int(question.get("difficulty", 3) or 3)
        requested_bloom_level = _normalize_bloom_level(question.get("bloom_level"))
        estimated_bloom_level, bloom_reasons = _estimate_bloom_level(question)
        estimated_difficulty, difficulty_reasons = _estimate_question_difficulty(
            question,
            estimated_bloom_level=estimated_bloom_level,
        )

        difficulty_gap = abs(estimated_difficulty - requested_difficulty)
        difficulty_warning = None
        if difficulty_gap >= 2:
            difficulty_mismatch_count += 1
            difficulty_severe_mismatch_count += 1
            difficulty_warning = (
                f"声明难度 {requested_difficulty} 与估计难度 {estimated_difficulty} 偏差较大"
            )
        elif difficulty_gap == 1:
            difficulty_mismatch_count += 1
            difficulty_warning = (
                f"声明难度 {requested_difficulty} 与估计难度 {estimated_difficulty} 有偏差"
            )

        bloom_gap = None
        bloom_warning = None
        if requested_bloom_level and estimated_bloom_level:
            bloom_gap = abs(
                BLOOM_LEVEL_ORDER[requested_bloom_level] - BLOOM_LEVEL_ORDER[estimated_bloom_level]
            )
            if bloom_gap >= 2:
                bloom_mismatch_count += 1
                bloom_severe_mismatch_count += 1
                bloom_warning = (
                    f"声明认知层次“{_label_bloom_level(requested_bloom_level)}”与估计层次“{_label_bloom_level(estimated_bloom_level)}”偏差较大"
                )
            elif bloom_gap == 1:
                bloom_mismatch_count += 1
                bloom_warning = (
                    f"声明认知层次“{_label_bloom_level(requested_bloom_level)}”与估计层次“{_label_bloom_level(estimated_bloom_level)}”存在偏差"
                )

        warning_items = [item for item in (difficulty_warning, bloom_warning) if item]
        if warning_items:
            calibration_warning_count += 1
            warnings.append(f"第{index}题 后验校准提示：{'；'.join(warning_items)}")

        severity = "ok"
        if difficulty_gap >= 2 or (bloom_gap is not None and bloom_gap >= 2):
            severity = "severe"
        elif warning_items:
            severity = "warn"

        question["calibration_review"] = {
            "requested_difficulty": requested_difficulty,
            "estimated_difficulty": estimated_difficulty,
            "difficulty_gap": difficulty_gap,
            "requested_bloom_level": requested_bloom_level,
            "estimated_bloom_level": estimated_bloom_level,
            "bloom_gap": bloom_gap,
            "severity": severity,
            "warnings": warning_items,
            "difficulty_reasons": difficulty_reasons,
            "bloom_reasons": bloom_reasons,
        }

    return {
        "reviewed_count": reviewed_count,
        "warning_count": calibration_warning_count,
        "difficulty_mismatch_count": difficulty_mismatch_count,
        "difficulty_severe_mismatch_count": difficulty_severe_mismatch_count,
        "bloom_mismatch_count": bloom_mismatch_count,
        "bloom_severe_mismatch_count": bloom_severe_mismatch_count,
        "warnings": warnings,
    }


def _review_preview_questions(raw_questions: list[dict]) -> dict:
    warnings: list[str] = []
    blocked_items: list[str] = []
    reviewed_count = 0

    for index, question in enumerate(raw_questions, start=1):
        review = ai_review_question(
            stem=question.get("stem", ""),
            options=question.get("options"),
            correct_answer=question.get("correct_answer", ""),
            explanation=question.get("explanation"),
            question_type=question.get("question_type", "single_choice"),
            difficulty=question.get("difficulty", 3),
            dimension=question.get("dimension"),
        )
        question["quality_review"] = review
        reviewed_count += 1

        recommendation = str(review.get("recommendation", "") or "").lower()
        overall_score = _normalize_review_overall_score(review)
        comments = str(review.get("comments", "") or "").strip()

        if recommendation == "reject" or overall_score < 2.5:
            blocked_items.append(f"第{index}题 AI质检建议拒绝（{overall_score:.1f}分）")
        elif recommendation == "revise" or overall_score < 3.5:
            warnings.append(f"第{index}题 AI质检建议修改（{overall_score:.1f}分）：{comments or '题目质量需人工复核'}")

    return {
        "reviewed_count": reviewed_count,
        "blocked_items": blocked_items,
        "warnings": warnings,
    }


def _attach_preview_item_ids(raw_questions: list[dict]) -> list[dict]:
    for question in raw_questions:
        preview_item_id = question.get("preview_item_id")
        if preview_item_id:
            question["preview_item_id"] = str(preview_item_id)
            continue
        question["preview_item_id"] = str(uuid.uuid4())
    return raw_questions


def _build_preview_review_items(raw_questions: list[dict]) -> list[dict]:
    items: list[dict] = []
    for question in raw_questions:
        preview_item_id = question.get("preview_item_id")
        if not preview_item_id:
            continue
        items.append({
            "preview_item_id": str(preview_item_id),
            "quality_review": question.get("quality_review"),
        })
    return items


def create_preview_review_batch(raw_questions: list[dict], stats: dict) -> Optional[uuid.UUID]:
    if not raw_questions:
        return None
    _attach_preview_item_ids(raw_questions)
    return preview_review_store.create_batch(raw_questions, stats)


def get_preview_review_batch(batch_id: uuid.UUID | str) -> Optional[dict]:
    payload = preview_review_store.get_batch(batch_id)
    if not payload:
        return None
    return {
        "preview_batch_id": payload.get("preview_batch_id"),
        "pending": payload.get("pending", False),
        "completed": payload.get("completed", False),
        "failed": payload.get("failed", False),
        "error": payload.get("error"),
        "questions": _build_preview_review_items(payload.get("questions", [])),
        "stats": payload.get("stats"),
    }


async def populate_preview_ai_review(batch_id: uuid.UUID | str) -> None:
    payload = preview_review_store.get_batch(batch_id)
    if not payload or not payload.get("pending"):
        return

    raw_questions = payload.get("questions", [])
    stats = dict(payload.get("stats") or {})
    if not raw_questions:
        stats["ai_review_pending"] = False
        stats["ai_review_completed"] = True
        preview_review_store.update_batch(
            batch_id,
            stats=stats,
            pending=False,
            completed=True,
            failed=False,
            error=None,
        )
        return

    try:
        review_summary = await asyncio.to_thread(_review_preview_questions, raw_questions)
        warnings = list(
            dict.fromkeys(
                [
                    *(stats.get("warnings") or []),
                    *review_summary["warnings"],
                    *review_summary["blocked_items"],
                ]
            )
        )
        stats.update({
            "quality_review_count": review_summary["reviewed_count"],
            "quality_review_blocked": len(review_summary["blocked_items"]),
            "quality_gate_failed": bool(stats.get("quality_gate_failed")) or bool(review_summary["blocked_items"]),
            "ai_review_pending": False,
            "ai_review_completed": True,
            "warnings": warnings,
        })
        preview_review_store.update_batch(
            batch_id,
            questions=raw_questions,
            stats=stats,
            pending=False,
            completed=True,
            failed=False,
            error=None,
        )
    except Exception as exc:
        logger.exception("Preview AI review failed for batch %s", batch_id)
        warnings = list(
            dict.fromkeys(
                [
                    *(stats.get("warnings") or []),
                    f"AI质检回填失败：{exc}",
                ]
            )
        )
        stats.update({
            "ai_review_pending": False,
            "ai_review_completed": False,
            "warnings": warnings,
        })
        preview_review_store.update_batch(
            batch_id,
            stats=stats,
            pending=False,
            completed=False,
            failed=True,
            error=str(exc),
        )


async def enrich_question_source_titles(
    db: AsyncSession,
    questions: list[Question],
) -> list[Question]:
    """Attach source titles to question objects for API serialization."""
    if not questions:
        return questions

    knowledge_unit_ids = {
        q.source_knowledge_unit_id
        for q in questions
        if q.source_knowledge_unit_id is not None
    }
    material_ids = {
        q.source_material_id
        for q in questions
        if q.source_material_id is not None
    }

    knowledge_unit_map: dict[uuid.UUID, dict[str, Optional[uuid.UUID | str]]] = {}
    if knowledge_unit_ids:
        result = await db.execute(
            select(KnowledgeUnit.id, KnowledgeUnit.title, KnowledgeUnit.material_id)
            .where(KnowledgeUnit.id.in_(knowledge_unit_ids))
        )
        for ku_id, ku_title, material_id in result.all():
            knowledge_unit_map[ku_id] = {
                "title": ku_title,
                "material_id": material_id,
            }
            if material_id is not None:
                material_ids.add(material_id)

    material_title_map: dict[uuid.UUID, str] = {}
    if material_ids:
        result = await db.execute(
            select(Material.id, Material.title).where(Material.id.in_(material_ids))
        )
        material_title_map = {material_id: title for material_id, title in result.all()}

    for question in questions:
        knowledge_unit = knowledge_unit_map.get(question.source_knowledge_unit_id)
        knowledge_unit_title = knowledge_unit["title"] if knowledge_unit else None
        material_id = (
            knowledge_unit["material_id"]
            if knowledge_unit and knowledge_unit.get("material_id") is not None
            else question.source_material_id
        )
        material_title = material_title_map.get(material_id) if material_id else None
        setattr(question, "source_knowledge_unit_title", knowledge_unit_title)
        setattr(question, "source_material_title", material_title)

    return questions


def _build_material_retry_prompt(
    custom_prompt: Optional[str],
    reasons: list[str],
    attempt: int,
) -> Optional[str]:
    sections = []
    if custom_prompt:
        sections.append(custom_prompt.strip())

    reason_lines = "\n".join(f"- {reason}" for reason in reasons[:8])
    sections.append(
        f"【第{attempt}次重生要求】\n"
        "上一轮整套题自检未通过，请重新生成整套题，不要沿用上轮题干、角色或重复知识点。\n"
        f"{reason_lines}"
    )
    return "\n\n".join(section for section in sections if section)


async def create_question(
    db: AsyncSession,
    question_type: str,
    stem: str,
    correct_answer: str,
    options: Optional[dict] = None,
    explanation: Optional[str] = None,
    rubric: Optional[dict] = None,
    difficulty: int = 3,
    dimension: Optional[str] = None,
    knowledge_tags: Optional[list] = None,
    bloom_level: Optional[str] = None,
    source_material_id: Optional[uuid.UUID] = None,
    source_knowledge_unit_id: Optional[uuid.UUID] = None,
    created_by: Optional[uuid.UUID] = None,
) -> Question:
    """Create a single question."""
    q = Question(
        question_type=QuestionType(question_type),
        stem=stem,
        correct_answer=correct_answer,
        options=options,
        explanation=explanation,
        rubric=rubric,
        difficulty=difficulty,
        dimension=dimension,
        knowledge_tags=knowledge_tags,
        bloom_level=BloomLevel(bloom_level) if bloom_level else None,
        source_material_id=source_material_id,
        source_knowledge_unit_id=source_knowledge_unit_id,
        created_by=created_by,
        status=QuestionStatus.DRAFT,
    )
    db.add(q)
    await db.flush()
    return q


async def get_question_by_id(
    db: AsyncSession, question_id: uuid.UUID
) -> Optional[Question]:
    result = await db.execute(
        select(Question).where(Question.id == question_id)
    )
    return result.scalar_one_or_none()


async def list_questions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    question_type: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: Optional[int] = None,
    keyword: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    exclude_ids: Optional[list[uuid.UUID]] = None,
) -> tuple[list[Question], int]:
    """List questions with filters and pagination."""
    conditions = []
    if status:
        conditions.append(Question.status == QuestionStatus(status))
    if question_type:
        conditions.append(Question.question_type == QuestionType(question_type))
    if dimension:
        conditions.append(Question.dimension == dimension)
    if difficulty:
        conditions.append(Question.difficulty == difficulty)
    if keyword:
        conditions.append(Question.stem.ilike(f"%{keyword}%"))
    if created_by:
        conditions.append(Question.created_by == created_by)
    if exclude_ids:
        conditions.append(Question.id.notin_(exclude_ids))

    where_clause = and_(*conditions) if conditions else True

    # Count
    count_q = select(func.count(Question.id)).where(where_clause)
    total = (await db.execute(count_q)).scalar()

    # Items
    items_q = (
        select(Question)
        .where(where_clause)
        .order_by(Question.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(items_q)
    items = list(result.scalars().all())

    return items, total


async def update_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    **kwargs,
) -> Optional[Question]:
    """Update a question's fields."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(q, key):
            if key == "bloom_level":
                setattr(q, key, BloomLevel(value))
            else:
                setattr(q, key, value)

    await db.flush()
    return q


async def delete_question(
    db: AsyncSession, question_id: uuid.UUID
) -> bool:
    q = await get_question_by_id(db, question_id)
    if not q:
        return False
    await db.delete(q)
    await db.flush()
    return True


async def batch_delete(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> int:
    """Batch delete questions. Returns count of actually deleted."""
    deleted = 0
    for qid in question_ids:
        ok = await delete_question(db, qid)
        if ok:
            deleted += 1
    return deleted


async def review_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    action: str,
    reviewer_id: uuid.UUID,
    comment: Optional[str] = None,
) -> Optional[Question]:
    """Approve or reject a question, with audit trail."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None

    if action == "approve":
        q.status = QuestionStatus.APPROVED
    elif action == "reject":
        q.status = QuestionStatus.REJECTED
    else:
        raise ValueError(f"Invalid review action: {action}")

    q.reviewed_by = reviewer_id
    q.review_comment = comment
    await db.flush()

    # Create audit record
    record = ReviewRecord(
        question_id=question_id,
        reviewer_id=reviewer_id,
        action=action,
        comment=comment,
    )
    db.add(record)
    await db.flush()

    return q


async def ai_check_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict:
    """Run AI quality check on a question. Returns scores and recommendation."""
    q = await get_question_by_id(db, question_id)
    if not q:
        raise ValueError(f"Question {question_id} not found")

    result = ai_review_question(
        stem=q.stem,
        options=q.options,
        correct_answer=q.correct_answer,
        explanation=q.explanation,
        question_type=q.question_type.value if hasattr(q.question_type, 'value') else q.question_type,
        difficulty=q.difficulty,
        dimension=q.dimension,
    )

    # Save AI check as review record
    record = ReviewRecord(
        question_id=question_id,
        reviewer_id=reviewer_id,
        action="ai_check",
        comment=result.get("comments"),
        ai_scores=result.get("scores"),
    )
    db.add(record)
    await db.flush()

    return result


async def get_review_history(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> list[ReviewRecord]:
    """Get review history for a question."""
    result = await db.execute(
        select(ReviewRecord)
        .where(ReviewRecord.question_id == question_id)
        .order_by(ReviewRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def get_pending_reviews(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Question], int]:
    """Get questions pending review."""
    return await list_questions(db, skip=skip, limit=limit, status="pending_review")


async def batch_submit_for_review(
    db: AsyncSession,
    question_ids: list[uuid.UUID],
) -> list[Question]:
    """Submit multiple draft questions for review. Skips non-draft questions."""
    submitted = []
    for qid in question_ids:
        try:
            q = await submit_for_review(db, qid)
            if q:
                submitted.append(q)
        except ValueError:
            # Skip questions that aren't in draft status
            continue
    return submitted


async def batch_review(
    db: AsyncSession,
    question_ids: list[uuid.UUID],
    action: str,
    reviewer_id: uuid.UUID,
    comment: Optional[str] = None,
) -> list[Question]:
    """Batch approve or reject questions."""
    reviewed = []
    for qid in question_ids:
        q = await review_question(db, qid, action, reviewer_id, comment)
        if q:
            reviewed.append(q)
    return reviewed


async def submit_for_review(
    db: AsyncSession, question_id: uuid.UUID
) -> Optional[Question]:
    """Submit a draft question for review."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None
    if q.status != QuestionStatus.DRAFT:
        raise ValueError(f"Only draft questions can be submitted, current status: {q.status.value}")
    q.status = QuestionStatus.PENDING_REVIEW
    await db.flush()
    return q


async def generate_from_knowledge_unit(
    db: AsyncSession,
    knowledge_unit_id: uuid.UUID,
    question_types: list[str],
    count: int = 3,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
    question_plan: Optional[list[dict]] = None,
) -> list[Question]:
    """Generate questions from a knowledge unit using LLM."""
    # Fetch KU
    result = await db.execute(
        select(KnowledgeUnit).where(KnowledgeUnit.id == knowledge_unit_id)
    )
    ku = result.scalar_one_or_none()
    if not ku:
        raise ValueError(f"Knowledge unit {knowledge_unit_id} not found")
    _ensure_knowledge_unit_generation_ready(ku)

    # Generate via LLM/template
    llm_result = generate_questions_via_llm(
        content=_build_knowledge_unit_prompt_content(ku),
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
        model_config=model_config,
        prompt_seed=prompt_seed,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        question_plan=question_plan,
    )
    raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
    usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}

    # Create question records (with per-question error handling)
    questions = []
    for raw in raw_questions:
        try:
            # Validate question_type is a valid enum value
            qt = raw.get("question_type", question_types[0])
            try:
                QuestionType(qt)
            except ValueError:
                logger.warning(f"Invalid question_type '{qt}', skipping")
                continue

            # Ensure knowledge_tags is a list (DB column is JSONB)
            tags = raw.get("knowledge_tags")
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                tags = None

            # 维度：优先KU维度，其次LLM输出，最后自动分类
            dim = ku.dimension or raw.get("dimension")
            if not dim:
                dim = classify_dimension(raw.get("stem", ""), tags)

            q = await create_question(
                db=db,
                question_type=qt,
                stem=raw.get("stem", ""),
                correct_answer=raw.get("correct_answer", ""),
                options=raw.get("options"),
                explanation=raw.get("explanation", ""),
                difficulty=difficulty,
                dimension=dim,
                knowledge_tags=tags,
                bloom_level=bloom_level,
                source_material_id=ku.material_id,
                source_knowledge_unit_id=ku.id,
                created_by=created_by,
            )
            questions.append(q)
        except Exception as e:
            logger.error(
                f"Failed to create question from KU {knowledge_unit_id}: {e}",
                exc_info=True,
            )
            continue

    return {"questions": questions, "usage": usage}


async def batch_generate_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    question_types: list[str],
    count_per_unit: int = 2,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    selection_mode: str = SELECTION_MODE_STABLE,
    created_by: Optional[uuid.UUID] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> list[Question]:
    """Generate questions from all knowledge units of a material."""
    # Verify material exists
    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"Material {material_id} not found")

    # Fetch knowledge units
    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units, _ = await _select_material_generation_units(
        db=db,
        material_id=material_id,
        units=list(ku_result.scalars().all()),
        max_units=max_units,
        selection_mode=selection_mode,
    )

    if not units:
        raise ValueError(f"Material {material_id} has no knowledge units. Parse the material first.")
    _ensure_material_generation_ready(material, units)

    all_questions = []
    for ku in units:
        try:
            result = await generate_from_knowledge_unit(
                db=db,
                knowledge_unit_id=ku.id,
                question_types=question_types,
                count=count_per_unit,
                difficulty=difficulty,
                bloom_level=bloom_level,
                created_by=created_by,
                prompt_seed=prompt_seed,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
            )
            questions = result.get("questions", result) if isinstance(result, dict) else result
            all_questions.extend(questions)
        except Exception as e:
            logger.error(
                f"Batch generation failed for KU {ku.id} in material {material_id}: {e}"
            )
            continue

    return all_questions


async def build_question_bank_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    selection_mode: str = SELECTION_MODE_STABLE,
    created_by: Optional[uuid.UUID] = None,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> list[Question]:
    """Build question bank from a material with specific type distribution.

    type_distribution maps question_type -> desired count, e.g.:
    {"single_choice": 10, "true_false": 5, "short_answer": 3}
    Questions are distributed evenly across knowledge units.
    """
    from app.models.material import MaterialStatus

    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    mat_status = material.status.value if hasattr(material.status, 'value') else material.status
    if mat_status not in ("parsed", "vectorized"):
        raise ValueError(f"素材尚未解析完成，当前状态: {mat_status}")

    requested_total = _count_requested_questions(type_distribution)
    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    await _prepare_material_generation_units(
        db=db,
        material=material,
        units=list(ku_result.scalars().all()),
        requested_total=requested_total,
        max_units=max_units,
        selection_mode=selection_mode,
    )

    preview_result = await preview_question_bank_from_material(
        db=db,
        material_id=material_id,
        type_distribution=type_distribution,
        difficulty=difficulty,
        bloom_level=bloom_level,
        max_units=max_units,
        selection_mode=selection_mode,
        custom_prompt=custom_prompt,
        model_config=model_config,
        created_by=created_by,
        prompt_seed=prompt_seed,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )
    preview_stats = preview_result.get("stats") or {}
    questions = await batch_create_from_raw(
        db=db,
        raw_questions=preview_result.get("questions", []),
        created_by=created_by,
    )
    return {"questions": questions, "stats": preview_stats}


async def suggest_question_distribution(
    db: AsyncSession,
    material_id: uuid.UUID,
    max_units: Optional[int] = None,
    selection_mode: str = SELECTION_MODE_STABLE,
) -> dict:
    """Analyze a material and suggest optimal question type distribution."""
    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    all_units = list(ku_result.scalars().all())
    units, selection_stats = await _select_material_generation_units(
        db=db,
        material_id=material_id,
        units=all_units,
        max_units=max_units,
        selection_mode=selection_mode,
    )
    total_units = len(units)

    if total_units == 0:
        raise ValueError("该素材没有知识单元，请先解析素材")
    _ensure_material_generation_ready(material, units)

    configured_max_units = max_units or 0
    effective_max_units = max_units

    for _ in range(3):
        total_content_length = sum(len(u.content or "") for u in units)
        total_questions = _estimate_suggested_question_target(total_units, total_content_length)
        next_effective_max_units = _effective_material_generation_max_units(max_units, total_questions)
        if next_effective_max_units == effective_max_units:
            break
        effective_max_units = next_effective_max_units
        units, selection_stats = await _select_material_generation_units(
            db=db,
            material_id=material_id,
            units=all_units,
            max_units=effective_max_units,
            selection_mode=selection_mode,
        )
        total_units = len(units)
        if total_units == 0:
            raise ValueError("该素材没有知识单元，请先解析素材")
        _ensure_material_generation_ready(material, units)

    total_content_length = sum(len(u.content or "") for u in units)
    total_questions = min(
        _estimate_suggested_question_target(total_units, total_content_length),
        total_units,
    )

    # Distribute by type ratios: single 40%, true_false 20%, multiple 15%, short_answer 15%, fill_blank 10%
    dist = _allocate_counts_by_weights(
        [
            ("single_choice", 0.40, (0, "single_choice")),
            ("true_false", 0.20, (1, "true_false")),
            ("multiple_choice", 0.15, (2, "multiple_choice")),
            ("short_answer", 0.15, (3, "short_answer")),
            ("fill_blank", 0.10, (4, "fill_blank")),
        ],
        total_questions,
    )

    # Determine average difficulty from knowledge units
    difficulties = [u.difficulty for u in units if u.difficulty]
    avg_difficulty = round(sum(difficulties) / len(difficulties)) if difficulties else 3

    actual_total = sum(dist.values())

    return {
        "material_id": str(material_id),
        "material_title": material.title,
        "total_units": total_units,
        "configured_max_units": configured_max_units,
        "effective_max_units": total_units,
        "suggested_distribution": dist,
        "suggested_total": actual_total,
        "difficulty": avg_difficulty,
        "selection_mode": selection_stats["selection_mode"],
    }


async def generate_questions_free(
    db: AsyncSession,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> list[Question]:
    """Generate questions without material, using LLM's own knowledge."""
    all_questions: list[Question] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {}
    start_time = time.time()

    for qtype, count in type_distribution.items():
        if count <= 0:
            continue
        llm_result = generate_questions_via_llm(
            content="",
            question_types=[qtype],
            count=count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
            model_config=model_config,
            prompt_seed=prompt_seed,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
        )
        raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
        usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)
        for raw in raw_questions:
            try:
                qt = raw.get("question_type", qtype)
                try:
                    QuestionType(qt)
                except ValueError:
                    logger.warning(f"Free generate: invalid question_type '{qt}', skipping")
                    continue

                tags = raw.get("knowledge_tags")
                if isinstance(tags, str):
                    tags = [tags]
                if not isinstance(tags, list):
                    tags = None

                # 维度：优先使用LLM输出的dimension，否则自动分类
                dim = raw.get("dimension")
                if not dim:
                    dim = classify_dimension(raw.get("stem", ""), tags)

                q = await create_question(
                    db=db,
                    question_type=qt,
                    stem=raw.get("stem", ""),
                    correct_answer=raw.get("correct_answer", ""),
                    options=raw.get("options"),
                    explanation=raw.get("explanation", ""),
                    difficulty=difficulty,
                    dimension=dim,
                    knowledge_tags=tags,
                    bloom_level=bloom_level,
                    source_material_id=None,
                    source_knowledge_unit_id=None,
                    created_by=created_by,
                )
                all_questions.append(q)
            except Exception as e:
                logger.error(f"Free generate: failed to create question: {e}")
                continue

        type_counts[qtype] = len([q for q in all_questions if q.question_type.value == qtype or q.question_type == qtype])

    duration = round(time.time() - start_time, 2)
    stats = {**total_usage, "duration_seconds": duration, "type_counts": type_counts}
    return {"questions": all_questions, "stats": stats}


async def preview_question_bank_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    selection_mode: str = SELECTION_MODE_STABLE,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    created_by: Optional[uuid.UUID] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> dict:
    """Preview question bank generation WITHOUT saving to DB.

    Same LLM logic as build_question_bank_from_material but returns raw dicts.
    """
    from app.models.material import MaterialStatus

    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    mat_status = material.status.value if hasattr(material.status, 'value') else material.status
    if mat_status not in ("parsed", "vectorized"):
        raise ValueError(f"素材尚未解析完成，当前状态: {mat_status}")

    requested_total = _count_requested_questions(type_distribution)
    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units, selection_stats = await _prepare_material_generation_units(
        db=db,
        material=material,
        units=list(ku_result.scalars().all()),
        requested_total=requested_total,
        max_units=max_units,
        selection_mode=selection_mode,
    )
    unit_type_plan = _plan_unit_type_distribution(units, type_distribution)
    planned_total = sum(
        sum(type_counts.values())
        for type_counts in unit_type_plan.values()
    )
    _ensure_material_unique_generation_capacity(units, requested_total)
    if planned_total < requested_total:
        raise ValueError(
            f"当前素材去重后仅有 {planned_total} 个可用知识点，不足以生成 {requested_total} 道互不重复知识点的题目"
        )
    planned_unit_ids = [
        ku.id
        for ku in units
        if any(count > 0 for count in unit_type_plan.get(ku.id, {}).values())
    ]
    last_result: dict | None = None
    last_reasons: list[str] = []

    for attempt in range(1, MATERIAL_GENERATION_MAX_ATTEMPTS + 1):
        attempt_prompt = custom_prompt
        if last_reasons:
            attempt_prompt = _build_material_retry_prompt(custom_prompt, last_reasons, attempt)

        all_preview: list[dict] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        type_counts: dict[str, int] = {
            question_type: 0
            for question_type, total_count in type_distribution.items()
            if total_count > 0
        }
        errors: list[str] = []
        fallback_count = 0
        start_time = time.time()
        generation_slots = _build_material_generation_slots(
            units,
            type_distribution,
            unit_type_plan,
        )
        planner_result = generate_question_plan_batch_via_llm(
            slot_requests=[
                {
                    "slot_index": slot["slot_index"],
                    "question_type": slot["question_type"],
                    "content": slot["planner_content"],
                }
                for slot in generation_slots
            ],
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=attempt_prompt,
            model_config=model_config,
            prompt_seed=prompt_seed,
        )
        planner_usage = planner_result.get("usage", {}) if isinstance(planner_result, dict) else {}
        for key in total_usage:
            total_usage[key] += planner_usage.get(key, 0)

        planned_items = planner_result.get("question_plan", []) if isinstance(planner_result, dict) else []
        if planner_result.get("fallback_used") and planner_result.get("error"):
            errors.append(f"planner: {planner_result['error']}")
        slots_by_type: dict[str, list[dict]] = {}
        for slot_index, slot in enumerate(generation_slots):
            question_plan = [planned_items[slot_index]] if slot_index < len(planned_items) else None
            slot_with_plan = {**slot, "question_plan": question_plan}
            slots_by_type.setdefault(slot["question_type"], []).append(slot_with_plan)

        generation_batches: list[tuple[str, list[dict]]] = [
            (qtype, slots)
            for qtype, slots in slots_by_type.items()
        ]
        generation_results = await _run_generation_jobs(
            [
                {
                    "content": _build_slot_batch_generator_content(slots),
                    "question_types": [qtype],
                    "count": len(slots),
                    "difficulty": difficulty,
                    "bloom_level": bloom_level,
                    "custom_prompt": attempt_prompt,
                    "model_config": model_config,
                    "prompt_seed": prompt_seed,
                    "system_prompt": system_prompt,
                    "user_prompt_template": user_prompt_template,
                    "question_plan": [
                        slot["question_plan"][0]
                        for slot in slots
                        if slot.get("question_plan")
                    ] if all(slot.get("question_plan") for slot in slots) else None,
                }
                for qtype, slots in generation_batches
            ]
        )

        for (qtype, slots), llm_result in zip(generation_batches, generation_results):
            raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
            usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
            if isinstance(llm_result, dict) and llm_result.get("fallback_used"):
                fallback_count += 1
                if llm_result.get("error"):
                    errors.append(str(llm_result["error"]))
            if len(raw_questions) != len(slots):
                errors.append(
                    f"{qtype}: 计划生成 {len(slots)} 道，实际返回 {len(raw_questions)} 道"
                )
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)

            for raw, slot in zip(raw_questions, slots):
                ku = slot["knowledge_unit"]
                tags = raw.get("knowledge_tags")
                if isinstance(tags, str):
                    tags = [tags]
                if not isinstance(tags, list):
                    tags = None

                dim = ku.dimension or raw.get("dimension")
                if not dim:
                    dim = classify_dimension(raw.get("stem", ""), tags)

                all_preview.append({
                    "question_type": raw.get("question_type", qtype),
                    "stem": raw.get("stem", ""),
                    "options": raw.get("options"),
                    "correct_answer": raw.get("correct_answer", ""),
                    "explanation": raw.get("explanation", ""),
                    "difficulty": difficulty,
                    "dimension": dim,
                    "knowledge_tags": tags,
                    "bloom_level": bloom_level,
                    "source_material_id": str(ku.material_id),
                    "source_knowledge_unit_id": str(ku.id),
                    "source_material_title": material.title,
                    "source_knowledge_unit_title": ku.title,
                })
                type_counts[qtype] = type_counts.get(qtype, 0) + 1

        validation = _validate_generated_question_set(
            all_preview,
            strict_material_rules=True,
        )
        existing_duplicates = await _collect_existing_duplicate_stems(db, all_preview)
        existing_duplicate_warnings = [
            f"题库中已存在同题干题目：{_truncate_text(stem, limit=36)}"
            for stem in existing_duplicates[:5]
        ]
        near_duplicate_warnings = _collect_near_duplicate_pairs(all_preview)
        existing_near_duplicate_warnings = await _collect_existing_near_duplicate_pairs(db, all_preview)
        calibration_summary = _review_preview_calibration(all_preview)
        generated_total = len(all_preview)
        quality_gate_failed = (
            bool(validation["reasons"])
            or bool(existing_duplicates)
            or bool(near_duplicate_warnings)
            or bool(existing_near_duplicate_warnings)
            or fallback_count > 0
            or generated_total < requested_total
        )
        save_blocked = False
        warnings: list[str] = []
        if generated_total < requested_total:
            warnings.append(f"实际仅生成 {generated_total} 道题，少于目标 {requested_total} 道")
        if fallback_count > 0:
            warnings.append("本次生成触发了降级模板，请关注结果中的风险提示")
        if validation["reasons"]:
            warnings.extend(validation["reasons"])
        warnings.extend(existing_duplicate_warnings)
        warnings.extend(near_duplicate_warnings)
        warnings.extend(existing_near_duplicate_warnings)
        warnings.extend(calibration_summary["warnings"])
        duration = round(time.time() - start_time, 2)
        stats = {
            **total_usage,
            "duration_seconds": duration,
            "type_counts": type_counts,
            "fallback_count": fallback_count,
            "errors": errors,
            "generation_attempts": attempt,
            "validation_reasons": validation["reasons"],
            "requested_total": requested_total,
            "generated_total": generated_total,
            "quality_gate_failed": quality_gate_failed,
            "save_blocked": save_blocked,
            "quality_review_count": 0,
            "quality_review_blocked": 0,
            "near_duplicate_count": len(near_duplicate_warnings),
            "existing_near_duplicate_count": len(existing_near_duplicate_warnings),
            "calibration_review_count": calibration_summary["reviewed_count"],
            "calibration_warning_count": calibration_summary["warning_count"],
            "difficulty_mismatch_count": calibration_summary["difficulty_mismatch_count"],
            "difficulty_severe_mismatch_count": calibration_summary["difficulty_severe_mismatch_count"],
            "bloom_mismatch_count": calibration_summary["bloom_mismatch_count"],
            "bloom_severe_mismatch_count": calibration_summary["bloom_severe_mismatch_count"],
            "selection_mode": selection_stats["selection_mode"],
            "configured_max_units": max_units,
            "effective_max_units": len(units),
            "selected_unit_count": len(units),
            "history_window_size": selection_stats["history_window_size"],
            "cooled_unit_count": selection_stats["cooled_unit_count"],
            "ai_review_pending": generated_total > 0,
            "ai_review_completed": False,
            "warnings": list(dict.fromkeys(warnings)),
        }
        last_result = {
            "preview_batch_id": None,
            "questions": all_preview,
            "stats": stats,
        }
        if validation["passed"] and not quality_gate_failed:
            if generated_total > 0 and planned_unit_ids:
                await _record_material_generation_run(
                    db=db,
                    material_id=material_id,
                    knowledge_unit_ids=planned_unit_ids,
                    selection_mode=selection_stats["selection_mode"],
                    created_by=created_by,
                )
            last_result["preview_batch_id"] = create_preview_review_batch(all_preview, stats)
            return last_result

        last_reasons = validation["reasons"]
        logger.warning(
            "Material %s question generation failed validation on attempt %s: %s",
            material_id,
            attempt,
            "; ".join(last_reasons),
        )

    if last_result and last_result.get("questions") and planned_unit_ids:
        await _record_material_generation_run(
            db=db,
            material_id=material_id,
            knowledge_unit_ids=planned_unit_ids,
            selection_mode=selection_stats["selection_mode"],
            created_by=created_by,
        )
        last_result["preview_batch_id"] = create_preview_review_batch(
            last_result.get("questions", []),
            last_result.get("stats", {}),
        )
    return last_result or {
        "preview_batch_id": None,
        "questions": [],
        "stats": {
            "validation_reasons": last_reasons,
            "ai_review_pending": False,
            "ai_review_completed": False,
        },
    }


async def preview_questions_free(
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> dict:
    """Preview question generation without material. No DB involvement."""
    all_preview: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {
        qtype: count
        for qtype, count in type_distribution.items()
        if count > 0
    }
    errors: list[str] = []
    fallback_count = 0
    start_time = time.time()
    requested_total = sum(count for count in type_distribution.values() if count > 0)

    generation_batches = [
        (qtype, count)
        for qtype, count in type_distribution.items()
        if count > 0
    ]
    generation_results = await _run_generation_jobs(
        [
            {
                "content": "",
                "question_types": [qtype],
                "count": count,
                "difficulty": difficulty,
                "bloom_level": bloom_level,
                "custom_prompt": custom_prompt,
                "model_config": model_config,
                "prompt_seed": prompt_seed,
                "system_prompt": system_prompt,
                "user_prompt_template": user_prompt_template,
            }
            for qtype, count in generation_batches
        ]
    )

    for (qtype, count), llm_result in zip(generation_batches, generation_results):
        raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
        usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
        if isinstance(llm_result, dict) and llm_result.get("fallback_used"):
            fallback_count += 1
            if llm_result.get("error"):
                errors.append(str(llm_result["error"]))
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)

        type_generated = 0
        for raw in raw_questions:
            tags = raw.get("knowledge_tags")
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                tags = None

            dim = raw.get("dimension")
            if not dim:
                dim = classify_dimension(raw.get("stem", ""), tags)

            all_preview.append({
                "question_type": raw.get("question_type", qtype),
                "stem": raw.get("stem", ""),
                "options": raw.get("options"),
                "correct_answer": raw.get("correct_answer", ""),
                "explanation": raw.get("explanation", ""),
                "difficulty": difficulty,
                "dimension": dim,
                "knowledge_tags": tags,
                "bloom_level": bloom_level,
                "source_material_id": None,
                "source_knowledge_unit_id": None,
            })
            type_generated += 1

        type_counts[qtype] = type_generated

    duration = round(time.time() - start_time, 2)
    generated_total = len(all_preview)
    near_duplicate_warnings = _collect_near_duplicate_pairs(all_preview)
    calibration_summary = _review_preview_calibration(all_preview)
    warnings: list[str] = []
    if generated_total < requested_total:
        warnings.append(f"实际仅生成 {generated_total} 道题，少于目标 {requested_total} 道")
    if fallback_count > 0:
        warnings.append("本次生成触发了降级模板，请关注结果中的风险提示")
    warnings.extend(near_duplicate_warnings)
    warnings.extend(calibration_summary["warnings"])
    quality_gate_failed = (
        fallback_count > 0
        or generated_total < requested_total
        or bool(near_duplicate_warnings)
    )
    save_blocked = False
    stats = {
        **total_usage,
        "duration_seconds": duration,
        "type_counts": type_counts,
        "fallback_count": fallback_count,
        "errors": errors,
        "requested_total": requested_total,
        "generated_total": generated_total,
        "quality_gate_failed": quality_gate_failed,
        "save_blocked": save_blocked,
        "quality_review_count": 0,
        "quality_review_blocked": 0,
        "near_duplicate_count": len(near_duplicate_warnings),
        "calibration_review_count": calibration_summary["reviewed_count"],
        "calibration_warning_count": calibration_summary["warning_count"],
        "difficulty_mismatch_count": calibration_summary["difficulty_mismatch_count"],
        "difficulty_severe_mismatch_count": calibration_summary["difficulty_severe_mismatch_count"],
        "bloom_mismatch_count": calibration_summary["bloom_mismatch_count"],
        "bloom_severe_mismatch_count": calibration_summary["bloom_severe_mismatch_count"],
        "configured_max_units": 0,
        "effective_max_units": 0,
        "selected_unit_count": 0,
        "ai_review_pending": generated_total > 0,
        "ai_review_completed": False,
        "warnings": list(dict.fromkeys(warnings)),
    }
    preview_batch_id = create_preview_review_batch(all_preview, stats)
    return {
        "preview_batch_id": preview_batch_id,
        "questions": all_preview,
        "stats": stats,
    }


async def batch_create_from_raw(
    db: AsyncSession,
    raw_questions: list[dict],
    created_by: Optional[uuid.UUID] = None,
) -> list:
    """Batch save preview question dicts to DB. Used after user review."""
    payload_duplicates = _collect_duplicate_stems(raw_questions)
    near_duplicates = _collect_near_duplicate_pairs(raw_questions)
    existing_duplicates = await _collect_existing_duplicate_stems(db, raw_questions)
    existing_near_duplicates = await _collect_existing_near_duplicate_pairs(db, raw_questions)

    material_linked_questions = [
        raw for raw in raw_questions
        if raw.get("source_material_id") or raw.get("source_knowledge_unit_id")
    ]
    validation = {"passed": True, "reasons": []}
    if material_linked_questions:
        validation = _validate_generated_question_set(
            material_linked_questions,
            strict_material_rules=True,
        )

    quality_signals: list[str] = []
    if payload_duplicates:
        quality_signals.append(f"重复题干 {len(payload_duplicates)} 个")
    if near_duplicates:
        quality_signals.append(f"批内近重复 {len(near_duplicates)} 个")
    if existing_duplicates:
        quality_signals.append(f"题库同题干重复 {len(existing_duplicates)} 个")
    if existing_near_duplicates:
        quality_signals.append(f"题库近重复 {len(existing_near_duplicates)} 个")
    if validation["reasons"]:
        quality_signals.append(f"素材严格校验命中 {len(validation['reasons'])} 条")
    if quality_signals:
        logger.warning(
            "Saving preview questions with quality warnings: %s",
            "；".join(quality_signals),
        )

    questions = []
    for raw in raw_questions:
        try:
            qt = raw.get("question_type", "single_choice")
            try:
                QuestionType(qt)
            except ValueError:
                logger.warning(f"batch_create_from_raw: invalid type '{qt}', skipping")
                continue

            q = await create_question(
                db=db,
                question_type=qt,
                stem=raw.get("stem", ""),
                correct_answer=raw.get("correct_answer", ""),
                options=raw.get("options"),
                explanation=raw.get("explanation", ""),
                difficulty=raw.get("difficulty", 3),
                dimension=raw.get("dimension"),
                knowledge_tags=raw.get("knowledge_tags"),
                bloom_level=raw.get("bloom_level"),
                source_material_id=_coerce_uuid(raw.get("source_material_id")),
                source_knowledge_unit_id=_coerce_uuid(raw.get("source_knowledge_unit_id")),
                created_by=created_by,
            )
            questions.append(q)
        except Exception as e:
            logger.error(f"batch_create_from_raw: failed: {e}", exc_info=True)
            continue
    return questions


async def get_question_stats(
    db: AsyncSession,
    dimension: Optional[str] = None,
    status: Optional[str] = None,
    question_type: Optional[str] = None,
    difficulty: Optional[int] = None,
    keyword: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
) -> dict:
    """Get question bank statistics."""
    conditions = []
    if dimension:
        conditions.append(Question.dimension == dimension)
    if status:
        conditions.append(Question.status == QuestionStatus(status))
    if question_type:
        conditions.append(Question.question_type == QuestionType(question_type))
    if difficulty:
        conditions.append(Question.difficulty == difficulty)
    if keyword:
        conditions.append(Question.stem.ilike(f"%{keyword}%"))
    if created_by:
        conditions.append(Question.created_by == created_by)

    where_clause = and_(*conditions) if conditions else True

    total = (await db.execute(
        select(func.count(Question.id)).where(where_clause)
    )).scalar()

    # Count by status
    status_q = (
        select(Question.status, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.status)
    )
    status_result = await db.execute(status_q)
    by_status = {row[0].value: row[1] for row in status_result.all()}

    # Count by type
    type_q = (
        select(Question.question_type, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.question_type)
    )
    type_result = await db.execute(type_q)
    by_type = {row[0].value: row[1] for row in type_result.all()}

    # Count by difficulty
    diff_q = (
        select(Question.difficulty, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.difficulty)
    )
    diff_result = await db.execute(diff_q)
    by_difficulty = {str(row[0]): row[1] for row in diff_result.all()}

    bloom_q = (
        select(Question.bloom_level, func.count(Question.id))
        .where(and_(where_clause, Question.bloom_level.isnot(None)))
        .group_by(Question.bloom_level)
    )
    bloom_result = await db.execute(bloom_q)
    by_bloom_level = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in bloom_result.all()
    }

    missing_dimension_count = (
        await db.execute(
            select(func.count(Question.id)).where(
                and_(
                    where_clause,
                    or_(Question.dimension.is_(None), Question.dimension == ""),
                )
            )
        )
    ).scalar() or 0
    missing_bloom_level_count = (
        await db.execute(
            select(func.count(Question.id)).where(
                and_(where_clause, Question.bloom_level.is_(None))
            )
        )
    ).scalar() or 0
    missing_explanation_count = (
        await db.execute(
            select(func.count(Question.id)).where(
                and_(
                    where_clause,
                    or_(Question.explanation.is_(None), Question.explanation == ""),
                )
            )
        )
    ).scalar() or 0
    source_linked_count = (
        await db.execute(
            select(func.count(Question.id)).where(
                and_(
                    where_clause,
                    or_(
                        Question.source_material_id.isnot(None),
                        Question.source_knowledge_unit_id.isnot(None),
                    ),
                )
            )
        )
    ).scalar() or 0

    return {
        "total": total,
        "by_status": by_status,
        "by_type": by_type,
        "by_difficulty": by_difficulty,
        "by_bloom_level": by_bloom_level,
        "quality_metrics": {
            "missing_dimension_count": missing_dimension_count,
            "missing_bloom_level_count": missing_bloom_level_count,
            "missing_explanation_count": missing_explanation_count,
            "source_linked_count": source_linked_count,
            "source_unlinked_count": max(int(total or 0) - int(source_linked_count or 0), 0),
        },
    }
