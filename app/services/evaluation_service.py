"""Evaluation level and motivational feedback service (T023).

Implements four-level evaluation with percentile ranking,
excellence ratio, and training recommendation push.
"""
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.score import Score
from app.models.answer import AnswerSheet


# Four evaluation levels
LEVELS = {
    "优秀": {"min_ratio": 0.9, "color": "#52c41a", "emoji": "🌟"},
    "良好": {"min_ratio": 0.8, "color": "#1890ff", "emoji": "👍"},
    "合格": {"min_ratio": 0.6, "color": "#faad14", "emoji": "✅"},
    "待提升": {"min_ratio": 0.0, "color": "#f5222d", "emoji": "📚"},
}

# Motivational messages per level
MOTIVATIONAL_MESSAGES = {
    "优秀": [
        "表现非常出色！你的AI素养已达到专家水平。",
        "继续保持，你已经走在前列！",
        "可以尝试挑战更高难度的内容来拓展视野。",
    ],
    "良好": [
        "表现很好！距离优秀只差一步。",
        "你已经展示了扎实的AI素养基础。",
        "在薄弱维度稍加努力即可达到更高水平。",
    ],
    "合格": [
        "已达到基本要求，还有很大的提升空间。",
        "建议针对薄弱维度进行系统学习。",
        "通过持续练习可以快速提升。",
    ],
    "待提升": [
        "需要加强AI素养基础知识的学习。",
        "建议从基础概念开始系统学习。",
        "不要灰心，AI素养可以通过学习和实践不断提升。",
    ],
}


def get_level_from_ratio(ratio: float) -> str:
    """Determine evaluation level from score ratio."""
    if ratio >= 0.9:
        return "优秀"
    elif ratio >= 0.8:
        return "良好"
    elif ratio >= 0.6:
        return "合格"
    return "待提升"


async def get_evaluation_feedback(
    db: AsyncSession,
    score_id: uuid.UUID,
) -> dict:
    """Generate evaluation level feedback with percentile and recommendations."""
    score = await db.execute(
        select(Score)
        .where(Score.id == score_id)
        .options(selectinload(Score.details))
    )
    score = score.scalar_one_or_none()
    if not score:
        raise ValueError("成绩不存在")

    ratio = score.total_score / score.max_score if score.max_score > 0 else 0
    level = get_level_from_ratio(ratio)

    # Get answer sheet for exam context
    sheet = (await db.execute(
        select(AnswerSheet).where(AnswerSheet.id == score.answer_sheet_id)
    )).scalar_one_or_none()

    # Calculate percentile and excellence ratio
    percentile = await _calculate_percentile_with_defaults(db, score, sheet)
    excellence_ratio = await _calculate_excellence_ratio(db, sheet)
    ranking_info = await _get_ranking_info(db, score, sheet)

    # Generate motivational feedback
    messages = MOTIVATIONAL_MESSAGES.get(level, MOTIVATIONAL_MESSAGES["待提升"])
    import random
    motivational_message = random.choice(messages)

    # Training recommendations based on weak areas
    training_recs = _generate_training_recommendations(score, level)

    return {
        "score_id": str(score.id),
        "total_score": score.total_score,
        "max_score": score.max_score,
        "ratio": round(ratio, 2),
        "level": level,
        "level_info": LEVELS[level],
        "percentile_rank": percentile,
        "excellence_ratio": excellence_ratio,
        "ranking": ranking_info,
        "motivational_message": motivational_message,
        "training_recommendations": training_recs,
        "next_level": _get_next_level_info(level, ratio, score.max_score),
    }


async def _calculate_percentile_with_defaults(
    db: AsyncSession, score: Score, sheet: Optional[AnswerSheet]
) -> float:
    """Calculate percentile with default values for small samples."""
    if not sheet:
        return 50.0

    # Count total scores for this exam
    total_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == sheet.exam_id)
    )).scalar() or 0

    if total_count < 5:
        # With few participants, use score-based estimation
        ratio = score.total_score / score.max_score if score.max_score > 0 else 0
        return round(ratio * 100, 1)

    lower_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == sheet.exam_id,
            Score.total_score < score.total_score,
        )
    )).scalar() or 0

    return round((lower_count / total_count) * 100, 1)


async def _calculate_excellence_ratio(
    db: AsyncSession, sheet: Optional[AnswerSheet]
) -> dict:
    """Calculate the percentage of participants at each level."""
    if not sheet:
        return {"优秀": 0, "良好": 0, "合格": 0, "待提升": 0, "total": 0}

    result = await db.execute(
        select(Score.total_score, Score.max_score)
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == sheet.exam_id)
    )
    all_scores = result.all()

    counts = {"优秀": 0, "良好": 0, "合格": 0, "待提升": 0}
    for total, max_val in all_scores:
        r = total / max_val if max_val > 0 else 0
        lvl = get_level_from_ratio(r)
        counts[lvl] += 1

    total = len(all_scores)
    ratios = {}
    for lvl, count in counts.items():
        ratios[lvl] = round(count / total * 100, 1) if total > 0 else 0

    return {**ratios, "total": total}


async def _get_ranking_info(
    db: AsyncSession, score: Score, sheet: Optional[AnswerSheet]
) -> dict:
    """Get ranking position."""
    if not sheet:
        return {"rank": 1, "total": 1}

    total = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.exam_id == sheet.exam_id)
    )).scalar() or 1

    higher_count = (await db.execute(
        select(func.count(Score.id))
        .join(AnswerSheet, Score.answer_sheet_id == AnswerSheet.id)
        .where(
            AnswerSheet.exam_id == sheet.exam_id,
            Score.total_score > score.total_score,
        )
    )).scalar() or 0

    return {"rank": higher_count + 1, "total": total}


def _generate_training_recommendations(score: Score, level: str) -> list[dict]:
    """Generate training recommendations based on weak dimensions."""
    recs = []
    dim_scores = score.dimension_scores or {}

    weak_dims = []
    for dim, data in dim_scores.items():
        ratio = data.get("earned", 0) / data.get("max", 1) if data.get("max", 0) > 0 else 0
        if ratio < 0.6:
            weak_dims.append((dim, ratio))

    weak_dims.sort(key=lambda x: x[1])

    for dim, ratio in weak_dims[:3]:
        recs.append({
            "dimension": dim,
            "current_score": round(ratio * 100, 1),
            "target_score": 80,
            "suggested_action": f"系统学习「{dim}」相关知识，完成专项练习",
            "priority": "高" if ratio < 0.4 else "中",
        })

    if not recs:
        if level in ("优秀", "良好"):
            recs.append({
                "dimension": "综合提升",
                "current_score": round(score.total_score / score.max_score * 100 if score.max_score > 0 else 0, 1),
                "target_score": 95,
                "suggested_action": "尝试更高难度的情境题和开放性题目",
                "priority": "低",
            })

    return recs


def _get_next_level_info(current_level: str, ratio: float, max_score: float) -> Optional[dict]:
    """Calculate what's needed to reach the next level."""
    level_order = ["待提升", "合格", "良好", "优秀"]
    current_idx = level_order.index(current_level) if current_level in level_order else 0

    if current_idx >= len(level_order) - 1:
        return None  # Already at highest level

    next_level = level_order[current_idx + 1]
    next_ratio = LEVELS[next_level]["min_ratio"]
    points_needed = round((next_ratio - ratio) * max_score, 1)

    return {
        "next_level": next_level,
        "points_needed": max(0, points_needed),
        "target_ratio": next_ratio,
        "message": f"再获得{max(0, points_needed)}分即可达到「{next_level}」等级",
    }
