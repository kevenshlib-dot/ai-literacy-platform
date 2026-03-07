"""Diagnostic report service - generates five-dimensional literacy analysis.

Produces radar chart data, percentile ranking, and personalized recommendations.
"""
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.score import Score, ScoreDetail
from app.models.answer import AnswerSheet

# Five literacy dimensions
FIVE_DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]

# Dimension description mapping
DIMENSION_DESCRIPTIONS = {
    "AI基础知识": "对AI基本概念、发展历程、核心技术的理解",
    "AI技术应用": "在实际场景中选择和使用AI工具的能力",
    "AI伦理安全": "对AI伦理问题、隐私保护、安全风险的认识",
    "AI批判思维": "批判性评估AI输出、识别偏见和局限的能力",
    "AI创新实践": "利用AI进行创新解决问题的能力",
}


async def generate_diagnostic_report(
    db: AsyncSession,
    score_id: uuid.UUID,
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

    # Map question dimensions to five-dimension framework
    radar_data = _build_radar_data(score)

    # Calculate percentile
    percentile = await _calculate_percentile(db, score)
    score.percentile_rank = percentile
    await db.flush()

    # Build diagnostic report
    report = {
        "score_id": str(score.id),
        "total_score": score.total_score,
        "max_score": score.max_score,
        "ratio": round(score.total_score / score.max_score, 2) if score.max_score > 0 else 0,
        "level": score.level,
        "percentile_rank": percentile,
        "radar_data": radar_data,
        "dimension_analysis": _analyze_dimensions(radar_data),
        "strengths": _identify_strengths(radar_data),
        "weaknesses": _identify_weaknesses(radar_data),
        "recommendations": _generate_personalized_recommendations(radar_data),
        "comparison": _generate_comparison_data(radar_data),
    }

    score.report = report
    await db.flush()

    return report


def _build_radar_data(score: Score) -> list[dict]:
    """Build five-dimensional radar chart data from dimension scores."""
    dim_scores = score.dimension_scores or {}

    radar_items = []
    for dim in FIVE_DIMENSIONS:
        # Try to find matching dimension data
        matched = None
        for key, data in dim_scores.items():
            if key in dim or dim in key:
                matched = data
                break

        if matched:
            earned = matched.get("earned", 0)
            max_val = matched.get("max", 10)
            ratio = earned / max_val if max_val > 0 else 0
            score_val = round(ratio * 100, 1)
        else:
            # Default for unmatched dimensions
            overall_ratio = score.total_score / score.max_score if score.max_score > 0 else 0
            score_val = round(overall_ratio * 100, 1)

        radar_items.append({
            "dimension": dim,
            "score": score_val,
            "max": 100,
            "description": DIMENSION_DESCRIPTIONS.get(dim, ""),
            "level": _score_to_level(score_val),
        })

    return radar_items


def _score_to_level(score: float) -> str:
    if score >= 90:
        return "优秀"
    elif score >= 80:
        return "良好"
    elif score >= 60:
        return "合格"
    else:
        return "需提升"


async def _calculate_percentile(db: AsyncSession, score: Score) -> float:
    """Calculate percentile rank among all scores for the same exam."""
    # Get the exam_id from the answer sheet
    sheet = (await db.execute(
        select(AnswerSheet).where(AnswerSheet.id == score.answer_sheet_id)
    )).scalar_one_or_none()

    if not sheet:
        return 50.0

    # Count scores lower than this one for the same exam
    lower_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == sheet.exam_id,
            Score.total_score < score.total_score,
        )
    )).scalar() or 0

    total_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == sheet.exam_id)
    )).scalar() or 1

    percentile = round((lower_count / total_count) * 100, 1) if total_count > 0 else 50.0
    return percentile


def _analyze_dimensions(radar_data: list[dict]) -> dict:
    """Detailed analysis per dimension."""
    analysis = {}
    for item in radar_data:
        dim = item["dimension"]
        score = item["score"]
        analysis[dim] = {
            "score": score,
            "level": item["level"],
            "description": item["description"],
            "detail": _dimension_detail(dim, score),
        }
    return analysis


def _dimension_detail(dim: str, score: float) -> str:
    """Generate detailed dimension-specific feedback."""
    if score >= 90:
        return f"在{dim}维度表现优秀，建议继续保持并挑战更高难度。"
    elif score >= 80:
        return f"在{dim}维度表现良好，还有少量提升空间。"
    elif score >= 60:
        return f"在{dim}维度达到合格水平，建议通过专项练习进一步提升。"
    else:
        return f"在{dim}维度需要重点加强，建议系统学习相关知识。"


def _identify_strengths(radar_data: list[dict]) -> list[dict]:
    """Identify top-performing dimensions."""
    sorted_dims = sorted(radar_data, key=lambda x: x["score"], reverse=True)
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
    """Identify lowest-performing dimensions."""
    sorted_dims = sorted(radar_data, key=lambda x: x["score"])
    weaknesses = []
    for item in sorted_dims[:2]:
        if item["score"] < 80:
            weaknesses.append({
                "dimension": item["dimension"],
                "score": item["score"],
                "comment": f"{item['dimension']}需要加强",
            })
    return weaknesses


def _generate_personalized_recommendations(radar_data: list[dict]) -> list[dict]:
    """Generate specific learning recommendations per weak dimension."""
    recs = []
    for item in sorted(radar_data, key=lambda x: x["score"]):
        if item["score"] < 80:
            recs.append({
                "dimension": item["dimension"],
                "priority": "高" if item["score"] < 60 else "中",
                "suggestion": _get_suggestion(item["dimension"], item["score"]),
            })
    if not recs:
        recs.append({
            "dimension": "全部",
            "priority": "低",
            "suggestion": "各维度表现均衡，建议挑战进阶内容。",
        })
    return recs


def _get_suggestion(dim: str, score: float) -> str:
    """Get dimension-specific learning suggestion."""
    suggestions = {
        "AI基础知识": "建议学习AI发展史、机器学习基本原理、常见AI模型类型等基础知识。",
        "AI技术应用": "建议多实践使用各类AI工具，了解不同场景下的AI解决方案。",
        "AI伦理安全": "建议学习AI伦理准则、数据隐私法规、AI安全最佳实践。",
        "AI批判思维": "建议练习评估AI输出的准确性，了解常见的AI偏见和局限性。",
        "AI创新实践": "建议参与AI项目实践，学习使用提示工程等创新方法。",
    }
    return suggestions.get(dim, f"建议重点学习{dim}相关内容。")


def _generate_comparison_data(radar_data: list[dict]) -> dict:
    """Generate comparison bar chart data (user vs average)."""
    # Default average scores (can be replaced with actual data)
    default_avg = {
        "AI基础知识": 72,
        "AI技术应用": 68,
        "AI伦理安全": 65,
        "AI批判思维": 60,
        "AI创新实践": 55,
    }

    comparison = []
    for item in radar_data:
        comparison.append({
            "dimension": item["dimension"],
            "user_score": item["score"],
            "avg_score": default_avg.get(item["dimension"], 65),
            "diff": round(item["score"] - default_avg.get(item["dimension"], 65), 1),
        })

    return {
        "items": comparison,
        "above_average_count": sum(1 for c in comparison if c["diff"] > 0),
        "below_average_count": sum(1 for c in comparison if c["diff"] < 0),
    }
