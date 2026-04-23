"""Diagnostic report service - generates five-dimensional literacy analysis."""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.diagnostic_report_agent import generate_structured_diagnostic_sections
from app.models.answer import Answer, AnswerSheet
from app.models.question import Question
from app.models.score import Score
from app.services.adaptive_learning_service import get_courses_for_dimensions
from app.services.report_storage import (
    DIAGNOSTIC_REPORT_KEY,
    get_report_namespace,
    set_report_namespace,
)
from app.services.score_service import get_wrong_answer_details

logger = logging.getLogger(__name__)
DIAGNOSTIC_LLM_TIMEOUT_SECONDS = 20.0

FIVE_DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]

DIMENSION_DESCRIPTIONS = {
    "AI基础知识": "对AI基本概念、发展历程、核心技术的理解",
    "AI技术应用": "在实际场景中选择和使用AI工具的能力",
    "AI伦理安全": "对AI伦理问题、隐私保护、安全风险的认识",
    "AI批判思维": "批判性评估AI输出、识别偏见和局限的能力",
    "AI创新实践": "利用AI进行创新解决问题的能力",
}


def _not_evaluated_dimension_text() -> str:
    return "本次测评在该维度没有题目覆盖，暂不评估。"


async def generate_diagnostic_report(
    db: AsyncSession,
    score_id: uuid.UUID,
    force_refresh: bool = False,
) -> dict:
    """Generate a comprehensive five-dimensional diagnostic report."""
    score = await db.execute(
        select(Score)
        .where(Score.id == score_id)
        .options(selectinload(Score.details))
    )
    score = score.scalar_one_or_none()
    if not score:
        raise ValueError("成绩不存在")

    if not force_refresh:
        cached = get_report_namespace(score, DIAGNOSTIC_REPORT_KEY)
        if cached:
            return cached

    fact_pack = await _build_diagnostic_fact_pack(db, score)
    fallback_sections = _build_fallback_sections(fact_pack)

    llm_sections = None
    try:
        llm_sections = await asyncio.wait_for(
            asyncio.to_thread(
                generate_structured_diagnostic_sections,
                _llm_fact_pack(fact_pack),
            ),
            timeout=DIAGNOSTIC_LLM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Structured diagnostic generation failed, fallback applied: %s", exc)

    sections = _merge_sections(
        fallback_sections,
        _validate_llm_sections(llm_sections or {}, fact_pack),
    )

    report = {
        "score_id": str(score.id),
        "total_score": score.total_score,
        "max_score": score.max_score,
        "ratio": round(score.total_score / score.max_score, 2) if score.max_score > 0 else 0,
        "level": score.level,
        "percentile_rank": fact_pack["overview"]["percentile_rank"],
        "radar_data": fact_pack["radar_data"],
        "dimension_analysis": _build_dimension_analysis_payload(
            fact_pack["dimension_metrics"],
            sections["dimension_analysis"],
        ),
        "strengths": _identify_strengths(fact_pack["radar_data"]),
        "weaknesses": _identify_weaknesses(fact_pack["radar_data"]),
        "comparison": fact_pack["comparison"],
        "wrong_answer_summary": sections["wrong_answer_summary"],
        "personalized_summary": sections["personalized_summary"],
        "improvement_priorities": sections["improvement_priorities"],
        "actionable_suggestions": sections["actionable_suggestions"],
        "recommended_resources": sections["recommended_resources"],
        "recommendations": [
            item.get("suggestion", "")
            for item in sections["actionable_suggestions"]
            if item.get("suggestion")
        ],
    }

    score.percentile_rank = fact_pack["overview"]["percentile_rank"]
    set_report_namespace(score, DIAGNOSTIC_REPORT_KEY, report)
    await db.flush()

    return report


async def _build_diagnostic_fact_pack(db: AsyncSession, score: Score) -> dict:
    sheet = (await db.execute(
        select(AnswerSheet).where(AnswerSheet.id == score.answer_sheet_id)
    )).scalar_one_or_none()
    if not sheet:
        raise ValueError("答题卡不存在")

    question_ids = [detail.question_id for detail in score.details]
    result = await db.execute(select(Question).where(Question.id.in_(question_ids)))
    questions_map = {q.id: q for q in result.scalars().all()}

    result = await db.execute(
        select(Answer).where(
            Answer.answer_sheet_id == score.answer_sheet_id,
            Answer.question_id.in_(question_ids),
        )
    )
    answers_map = {a.question_id: a for a in result.scalars().all()}

    percentile = await _calculate_percentile(db, score, sheet.exam_id)
    wrong_items = await get_wrong_answer_details(db, score.id)
    dimension_metrics = _build_dimension_metrics(score, questions_map, wrong_items)
    radar_data = _build_radar_data(dimension_metrics)
    type_metrics = _build_type_metrics(score, questions_map)
    comparison = await _generate_comparison_data(db, score, sheet.exam_id, radar_data)
    error_pattern_counts = Counter()
    for item in wrong_items:
        error_pattern_counts.update(item.get("error_reasons") or [])

    target_dimensions = [
        item["dimension"]
        for item in sorted(
            dimension_metrics.values(),
            key=lambda x: x["score"] if x["score"] is not None else 101,
        )
        if item["evaluated"] and item["score"] is not None and item["score"] < 80
    ][:3]
    courses_by_dim = await get_courses_for_dimensions(db, target_dimensions, limit_per_dimension=2)

    resource_candidates = []
    for dim in target_dimensions:
        for course in courses_by_dim.get(dim, []):
            resource_candidates.append({
                "course_id": str(course.id),
                "title": course.title,
                "dimension": dim,
                "difficulty": course.difficulty,
                "description": course.description or "",
            })

    return {
        "overview": {
            "score_id": str(score.id),
            "total_score": score.total_score,
            "max_score": score.max_score,
            "ratio": round(score.total_score / score.max_score, 2) if score.max_score > 0 else 0,
            "level": score.level,
            "percentile_rank": percentile,
            "question_count": len(score.details),
            "wrong_count": len(wrong_items),
        },
        "radar_data": radar_data,
        "dimension_metrics": dimension_metrics,
        "type_metrics": type_metrics,
        "wrong_items": _build_wrong_item_fact_pack(wrong_items, questions_map, answers_map),
        "comparison": comparison,
        "error_patterns": [
            {"reason": reason, "count": count}
            for reason, count in error_pattern_counts.most_common()
        ],
        "resource_candidates": resource_candidates,
    }


def _llm_fact_pack(fact_pack: dict) -> dict:
    return {
        "overview": fact_pack["overview"],
        "dimension_metrics": fact_pack["dimension_metrics"],
        "type_metrics": fact_pack["type_metrics"],
        "wrong_items": fact_pack["wrong_items"],
        "error_patterns": fact_pack["error_patterns"],
        "resource_candidates": fact_pack["resource_candidates"],
    }


def _build_wrong_item_fact_pack(
    wrong_items: list[dict],
    questions_map: dict,
    answers_map: dict,
) -> list[dict]:
    items = []
    for item in wrong_items:
        qid = item["question_id"]
        question = questions_map.get(uuid.UUID(qid)) if isinstance(qid, str) else None
        answer = answers_map.get(question.id) if question else None
        analysis = item.get("analysis") or {}
        items.append({
            "question_id": item["question_id"],
            "question_type": item["question_type"],
            "dimension": item.get("dimension"),
            "stem": item["stem"],
            "user_answer": item.get("user_answer", ""),
            "reference_answer": item.get("reference_answer") or item.get("correct_answer", ""),
            "explanation": item.get("explanation", ""),
            "earned_score": item["earned_score"],
            "max_score": item["max_score"],
            "feedback": item.get("feedback", ""),
            "judgement": analysis.get("judgement", ""),
            "error_reasons": analysis.get("error_reasons", []),
            "missed_points": analysis.get("missed_points", []),
            "positive_points": analysis.get("positive_points", []),
            "knowledge_tags": item.get("knowledge_tags") or [],
            "difficulty": item.get("difficulty"),
            "scoring_source": analysis.get("scoring_source"),
            "rubric": question.rubric if question else None,
            "submitted_answer": answer.answer_content if answer else item.get("user_answer", ""),
        })
    return items


def _build_type_metrics(score: Score, questions_map: dict[uuid.UUID, Question]) -> list[dict]:
    metrics = defaultdict(lambda: {"earned": 0.0, "max": 0.0, "count": 0, "correct": 0})
    for detail in score.details:
        question = questions_map.get(detail.question_id)
        if not question:
            continue
        qtype = question.question_type.value if hasattr(question.question_type, "value") else question.question_type
        metrics[qtype]["earned"] += detail.earned_score
        metrics[qtype]["max"] += detail.max_score
        metrics[qtype]["count"] += 1
        metrics[qtype]["correct"] += 1 if detail.is_correct else 0

    items = []
    for qtype, data in metrics.items():
        ratio = data["earned"] / data["max"] if data["max"] > 0 else 0
        items.append({
            "question_type": qtype,
            "earned": round(data["earned"], 1),
            "max": round(data["max"], 1),
            "count": data["count"],
            "correct_count": data["correct"],
            "ratio": round(ratio, 2),
        })
    return sorted(items, key=lambda x: x["question_type"])


def _build_dimension_metrics(
    score: Score,
    questions_map: dict[uuid.UUID, Question],
    wrong_items: list[dict],
) -> dict:
    metrics = {}
    wrong_by_dim = defaultdict(list)
    for item in wrong_items:
        dim = _match_framework_dimension(item.get("dimension"))
        if dim:
            wrong_by_dim[dim].append(item)

    for dim in FIVE_DIMENSIONS:
        matched_sources = []
        earned = 0.0
        max_score = 0.0
        count = 0
        for raw_dim, data in (score.dimension_scores or {}).items():
            matched_dim = _match_framework_dimension(raw_dim)
            if matched_dim == dim:
                matched_sources.append(raw_dim)
                earned += data.get("earned", 0.0)
                max_score += data.get("max", 0.0)
                count += data.get("count", 0)

        evaluated = count > 0 and max_score > 0
        if evaluated:
            ratio = earned / max_score
            score_val = round(ratio * 100, 1)
        else:
            ratio = None
            score_val = None

        dim_wrong_items = wrong_by_dim.get(dim, [])
        all_reasons = Counter()
        missed_points = []
        for item in dim_wrong_items:
            all_reasons.update(item.get("error_reasons") or [])
            missed_points.extend(item.get("missed_points") or [])

        metrics[dim] = {
            "dimension": dim,
            "score": score_val,
            "earned": round(earned, 1),
            "max": round(max_score, 1),
            "ratio": round(ratio, 2) if ratio is not None else None,
            "level": _score_to_level(score_val) if score_val is not None else "未评估",
            "description": DIMENSION_DESCRIPTIONS.get(dim, ""),
            "question_count": count,
            "wrong_count": len(dim_wrong_items),
            "source_dimensions": matched_sources,
            "common_error_reasons": [reason for reason, _ in all_reasons.most_common(3)],
            "missed_points": list(dict.fromkeys(missed_points))[:4],
            "evaluated": evaluated,
        }
    return metrics


def _match_framework_dimension(raw_dimension: str | None) -> str | None:
    if not raw_dimension:
        return None
    for dim in FIVE_DIMENSIONS:
        if raw_dimension in dim or dim in raw_dimension:
            return dim
    return None


def _build_radar_data(dimension_metrics: dict) -> list[dict]:
    radar_items = []
    for dim in FIVE_DIMENSIONS:
        metric = dimension_metrics[dim]
        score_val = metric["score"]

        radar_items.append({
            "dimension": dim,
            "score": score_val,
            "max": 100,
            "description": DIMENSION_DESCRIPTIONS.get(dim, ""),
            "level": metric["level"],
            "evaluated": metric["evaluated"],
        })
    return radar_items


def _score_to_level(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 80:
        return "良好"
    if score >= 60:
        return "合格"
    return "需提升"


async def _calculate_percentile(db: AsyncSession, score: Score, exam_id: uuid.UUID) -> float:
    lower_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == exam_id,
            Score.total_score < score.total_score,
        )
    )).scalar() or 0

    total_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == exam_id)
    )).scalar() or 1

    return round((lower_count / total_count) * 100, 1) if total_count > 0 else 50.0


async def _generate_comparison_data(
    db: AsyncSession,
    score: Score,
    exam_id: uuid.UUID,
    radar_data: list[dict],
) -> dict:
    result = await db.execute(
        select(Score)
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == exam_id)
    )
    cohort_scores = list(result.scalars().all())

    if not cohort_scores:
        cohort_scores = [score]

    averages = {dim: [] for dim in FIVE_DIMENSIONS}
    for cohort_score in cohort_scores:
        cohort_metrics = _build_dimension_metrics(cohort_score, {}, [])
        for item in _build_radar_data(cohort_metrics):
            if item["evaluated"] and item["score"] is not None:
                averages[item["dimension"]].append(item["score"])

    comparison = []
    for item in radar_data:
        avg_score = averages.get(item["dimension"], [])
        avg = round(sum(avg_score) / len(avg_score), 1) if avg_score else None
        diff = round(item["score"] - avg, 1) if item["evaluated"] and item["score"] is not None and avg is not None else None
        comparison.append({
            "dimension": item["dimension"],
            "user_score": item["score"],
            "avg_score": avg,
            "diff": diff,
            "evaluated": item["evaluated"],
        })

    return {
        "items": comparison,
        "above_average_count": sum(1 for c in comparison if c["diff"] is not None and c["diff"] > 0),
        "below_average_count": sum(1 for c in comparison if c["diff"] is not None and c["diff"] < 0),
    }


def _build_fallback_sections(fact_pack: dict) -> dict:
    wrong_items = fact_pack["wrong_items"]
    dimension_metrics = fact_pack["dimension_metrics"]

    wrong_answer_summary = {
        "overview": (
            f"本次测评共有{fact_pack['overview']['wrong_count']}道失分题。"
            if wrong_items else "本次测评未出现失分题。"
        ),
        "items": [
            {
                **item,
                "reason_summary": _summarize_wrong_reason(item),
                "improvement_tip": _wrong_item_tip(item),
            }
            for item in wrong_items
        ],
        "patterns": [
            _humanize_error_reason(item["reason"])
            for item in fact_pack["error_patterns"][:3]
        ],
    }

    dimension_analysis = {}
    for dim, metric in dimension_metrics.items():
        detail = _dimension_detail(dim, metric)
        if not metric["evaluated"]:
            priority = ""
            evidence = []
        else:
            priority = "high" if metric["score"] < 60 else "medium" if metric["score"] < 80 else "low"
            evidence = metric["missed_points"][:2] or metric["common_error_reasons"][:2]
        dimension_analysis[dim] = {
            "summary": detail,
            "evidence": evidence,
            "priority": priority,
        }

    weakest = [
        d
        for d in sorted(
            dimension_metrics.values(),
            key=lambda x: x["score"] if x["score"] is not None else 101,
        )
        if d["evaluated"] and d["score"] is not None and d["score"] < 80
    ][:3]
    actionable_suggestions = [
        {
            "dimension": metric["dimension"],
            "title": f"{metric['dimension']}专项提升",
            "suggestion": _dimension_suggestion(metric["dimension"], metric["score"]),
            "actions": _dimension_actions(metric["dimension"]),
        }
        for metric in weakest
    ]
    if not actionable_suggestions:
        actionable_suggestions = [{
            "dimension": "全部",
            "title": "保持优势并持续进阶",
            "suggestion": "当前各维度表现较均衡，建议通过更高难度任务巩固优势。",
            "actions": ["继续完成更复杂的综合场景练习", "定期复盘高分题的作答方式"],
        }]

    recommended_resources = []
    for course in fact_pack["resource_candidates"]:
        recommended_resources.append({
            "course_id": course["course_id"],
            "title": course["title"],
            "dimension": course["dimension"],
            "difficulty": course["difficulty"],
            "match_reason": f"该课程对应{course['dimension']}维度，可用于补强该维度的薄弱点。",
        })

    strengths = [item["dimension"] for item in _identify_strengths(fact_pack["radar_data"])]
    weaknesses = [item["dimension"] for item in _identify_weaknesses(fact_pack["radar_data"])]
    personalized_summary = {
        "summary": _personalized_summary_text(fact_pack, strengths, weaknesses),
        "highlights": strengths[:2],
        "cautions": weaknesses[:2],
    }

    improvement_priorities = [
        {
            "dimension": item["dimension"],
            "reason": f"{item['dimension']}得分{item['score']}分，且存在失分题，建议优先提升。",
            "actions": _dimension_actions(item["dimension"]),
        }
        for item in weakest[:3]
    ]

    return {
        "wrong_answer_summary": wrong_answer_summary,
        "dimension_analysis": dimension_analysis,
        "personalized_summary": personalized_summary,
        "improvement_priorities": improvement_priorities,
        "actionable_suggestions": actionable_suggestions,
        "recommended_resources": recommended_resources,
    }


def _merge_sections(fallback: dict, llm: dict) -> dict:
    merged = dict(fallback)
    if llm.get("wrong_answer_summary"):
        wrong = dict(fallback["wrong_answer_summary"])
        wrong.update({k: v for k, v in llm["wrong_answer_summary"].items() if v})
        llm_items = {item["question_id"]: item for item in wrong.get("items", []) if item.get("question_id")}
        fallback_items = []
        for item in fallback["wrong_answer_summary"]["items"]:
            overlay = llm_items.get(item["question_id"], {})
            merged_item = dict(item)
            merged_item.update({k: v for k, v in overlay.items() if v})
            fallback_items.append(merged_item)
        wrong["items"] = fallback_items
        merged["wrong_answer_summary"] = wrong

    for key in ("personalized_summary",):
        if llm.get(key):
            merged[key] = llm[key]

    for key in ("improvement_priorities", "actionable_suggestions", "recommended_resources"):
        if llm.get(key):
            merged[key] = llm[key]

    dim_analysis = dict(fallback["dimension_analysis"])
    for dim, payload in llm.get("dimension_analysis", {}).items():
        if dim in dim_analysis and isinstance(payload, dict):
            dim_analysis[dim].update({k: v for k, v in payload.items() if v})
    merged["dimension_analysis"] = dim_analysis
    return merged


def _validate_llm_sections(sections: dict, fact_pack: dict) -> dict:
    if not isinstance(sections, dict):
        return {}

    valid_dimensions = set(FIVE_DIMENSIONS)
    valid_question_ids = {item["question_id"] for item in fact_pack["wrong_items"]}
    valid_courses = {item["course_id"]: item for item in fact_pack["resource_candidates"]}
    validated = {}

    wrong = sections.get("wrong_answer_summary")
    if isinstance(wrong, dict):
        items = []
        for item in wrong.get("items", []):
            if not isinstance(item, dict):
                continue
            if item.get("question_id") not in valid_question_ids:
                continue
            items.append({
                "question_id": item["question_id"],
                "reason_summary": str(item.get("reason_summary", "")).strip(),
                "improvement_tip": str(item.get("improvement_tip", "")).strip(),
            })
        validated["wrong_answer_summary"] = {
            "overview": str(wrong.get("overview", "")).strip(),
            "items": items,
            "patterns": [str(x).strip() for x in wrong.get("patterns", []) if str(x).strip()][:4],
        }

    dim_analysis = {}
    for dim, payload in (sections.get("dimension_analysis") or {}).items():
        if dim not in valid_dimensions or not isinstance(payload, dict):
            continue
        priority = str(payload.get("priority", "")).strip().lower()
        if priority not in {"high", "medium", "low"}:
            priority = ""
        dim_analysis[dim] = {
            "summary": str(payload.get("summary", "")).strip(),
            "evidence": [str(x).strip() for x in payload.get("evidence", []) if str(x).strip()][:3],
            "priority": priority,
        }
    validated["dimension_analysis"] = dim_analysis

    personalized = sections.get("personalized_summary")
    if isinstance(personalized, dict):
        validated["personalized_summary"] = {
            "summary": str(personalized.get("summary", "")).strip(),
            "highlights": [str(x).strip() for x in personalized.get("highlights", []) if str(x).strip()][:3],
            "cautions": [str(x).strip() for x in personalized.get("cautions", []) if str(x).strip()][:3],
        }

    priorities = []
    for item in sections.get("improvement_priorities", []) or []:
        if not isinstance(item, dict) or item.get("dimension") not in valid_dimensions:
            continue
        priorities.append({
            "dimension": item["dimension"],
            "reason": str(item.get("reason", "")).strip(),
            "actions": [str(x).strip() for x in item.get("actions", []) if str(x).strip()][:3],
        })
    validated["improvement_priorities"] = priorities

    suggestions = []
    for item in sections.get("actionable_suggestions", []) or []:
        if not isinstance(item, dict):
            continue
        dim = item.get("dimension")
        if dim not in valid_dimensions and dim != "全部":
            continue
        suggestions.append({
            "dimension": dim,
            "title": str(item.get("title", "")).strip(),
            "suggestion": str(item.get("suggestion", "")).strip(),
            "actions": [str(x).strip() for x in item.get("actions", []) if str(x).strip()][:3],
        })
    validated["actionable_suggestions"] = suggestions

    resources = []
    for item in sections.get("recommended_resources", []) or []:
        if not isinstance(item, dict):
            continue
        course = valid_courses.get(item.get("course_id"))
        if not course:
            continue
        resources.append({
            "course_id": course["course_id"],
            "title": course["title"],
            "dimension": course["dimension"],
            "difficulty": course["difficulty"],
            "match_reason": str(item.get("match_reason", "")).strip(),
        })
    validated["recommended_resources"] = resources
    return validated


def _build_dimension_analysis_payload(metrics: dict, llm_payload: dict) -> dict:
    analysis = {}
    for dim, metric in metrics.items():
        llm_detail = llm_payload.get(dim, {}) if metric["evaluated"] else {}
        if metric["evaluated"]:
            fallback_evidence = metric["missed_points"][:2] or metric["common_error_reasons"][:2]
            fallback_priority = "high" if metric["score"] < 60 else "medium" if metric["score"] < 80 else "low"
        else:
            fallback_evidence = []
            fallback_priority = ""
        analysis[dim] = {
            "score": metric["score"],
            "level": metric["level"],
            "description": metric["description"],
            "detail": _dimension_detail(dim, metric),
            "summary": llm_detail.get("summary") or _dimension_detail(dim, metric),
            "evidence": llm_detail.get("evidence") or fallback_evidence,
            "priority": llm_detail.get("priority") or fallback_priority,
            "question_count": metric["question_count"],
            "wrong_count": metric["wrong_count"],
            "evaluated": metric["evaluated"],
        }
    return analysis


def _dimension_detail(dim: str, metric: dict) -> str:
    if not metric["evaluated"]:
        return _not_evaluated_dimension_text()
    score = metric["score"]
    if score >= 90:
        return f"{dim}维度表现优秀，相关题目掌握较为稳定。"
    if score >= 80:
        return f"{dim}维度整体表现良好，但仍存在少量可提升空间。"
    if score >= 60:
        return f"{dim}维度达到合格水平，建议结合失分点做专项补强。"
    return f"{dim}维度失分较多，建议优先补齐核心概念与应用方法。"


def _dimension_suggestion(dim: str, score: float) -> str:
    suggestions = {
        "AI基础知识": "建议系统复习核心概念、常见模型与基本原理，并对照错题整理概念卡片。",
        "AI技术应用": "建议结合具体场景练习工具选型、任务拆解和应用边界判断。",
        "AI伦理安全": "建议围绕隐私保护、偏见风险和安全规范做案例化学习。",
        "AI批判思维": "建议练习识别AI输出中的错误、偏差与证据不足情形。",
        "AI创新实践": "建议通过小型项目和提示词迭代训练解决真实问题的能力。",
    }
    suffix = "当前需优先提升。" if score < 60 else "建议继续做针对性强化。"
    return f"{suggestions.get(dim, f'建议重点强化{dim}相关能力。')}{suffix}"


def _dimension_actions(dim: str) -> list[str]:
    actions = {
        "AI基础知识": ["复盘错题中的概念误区", "按知识点补看基础课程"],
        "AI技术应用": ["针对典型场景做工具选型练习", "对比不同方案的适用边界"],
        "AI伦理安全": ["整理常见伦理与安全风险清单", "结合案例判断风险与应对方式"],
        "AI批判思维": ["练习核查AI输出依据", "遇到结论时先判断证据是否充分"],
        "AI创新实践": ["完成一个小型AI应用任务", "记录并迭代自己的提示词策略"],
    }
    return actions.get(dim, [f"围绕{dim}做专项练习", "完成一次复盘总结"])


def _summarize_wrong_reason(item: dict) -> str:
    reasons = item.get("error_reasons") or []
    if reasons:
        readable = "、".join(_humanize_error_reason(reason) for reason in reasons[:2])
        return f"该题主要问题是{readable}。"
    if item.get("missed_points"):
        return "该题存在关键要点遗漏。"
    return item.get("feedback") or "该题作答未达到标准答案要求。"


def _wrong_item_tip(item: dict) -> str:
    if item.get("missed_points"):
        return f"优先补上这些要点：{'；'.join(item['missed_points'][:2])}"
    return "建议对照参考答案复盘本题的关键判断依据。"


def _humanize_error_reason(reason: str) -> str:
    mapping = {
        "concept_error": "概念理解偏差",
        "incomplete_answer": "答案不完整",
        "logic_gap": "推理链条不完整",
        "scenario_misjudgment": "场景判断失误",
        "unsupported_claim": "结论缺少依据",
        "no_answer": "未作答",
    }
    return mapping.get(reason, reason)


def _personalized_summary_text(fact_pack: dict, strengths: list[str], weaknesses: list[str]) -> str:
    overview = fact_pack["overview"]
    strength_text = f"优势主要体现在{'、'.join(strengths)}。" if strengths else "当前暂无稳定优势维度。"
    weakness_text = f"仍需重点补强{'、'.join(weaknesses)}。" if weaknesses else "当前未发现明显短板。"
    return (
        f"本次测评总分为{overview['total_score']}/{overview['max_score']}，得分率"
        f"{int(overview['ratio'] * 100)}%，等级为{overview['level']}。"
        f"{strength_text}{weakness_text}"
    )


def _identify_strengths(radar_data: list[dict]) -> list[dict]:
    evaluated_dims = [item for item in radar_data if item["evaluated"] and item["score"] is not None]
    sorted_dims = sorted(evaluated_dims, key=lambda x: x["score"], reverse=True)
    strengths = []
    for item in sorted_dims[:2]:
        if item["score"] >= 60:
            strengths.append({
                "dimension": item["dimension"],
                "score": item["score"],
                "comment": f"{item['dimension']}表现{item['level']}",
            })
    return strengths


def _identify_weaknesses(radar_data: list[dict]) -> list[dict]:
    evaluated_dims = [item for item in radar_data if item["evaluated"] and item["score"] is not None]
    sorted_dims = sorted(evaluated_dims, key=lambda x: x["score"])
    weaknesses = []
    for item in sorted_dims[:2]:
        if item["score"] < 80:
            weaknesses.append({
                "dimension": item["dimension"],
                "score": item["score"],
                "comment": f"{item['dimension']}需要加强",
            })
    return weaknesses
