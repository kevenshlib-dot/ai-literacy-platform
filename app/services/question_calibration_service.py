"""Question calibration service - auto-retire and recalibrate questions."""
import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionStatus
from app.models.score import ScoreDetail
from app.services.question_analysis_service import analyze_question


async def auto_flag_low_quality(
    db: AsyncSession,
    min_sample: int = 10,
    discrimination_threshold: float = 0.15,
    difficulty_low: float = 0.1,
    difficulty_high: float = 0.95,
) -> dict:
    """Scan all questions and flag low-quality ones for review.

    Returns a report with flagged, archived, and recalibrated questions.
    """
    # Find questions with enough answer data
    result = await db.execute(
        select(
            ScoreDetail.question_id,
            func.count(ScoreDetail.id).label("cnt"),
        )
        .group_by(ScoreDetail.question_id)
        .having(func.count(ScoreDetail.id) >= min_sample)
    )
    rows = result.all()

    flagged = []
    archived = []
    recalibrated = []

    for qid, count in rows:
        analysis = await analyze_question(db, qid)
        if analysis["sample_size"] == 0:
            continue

        ctt = analysis["ctt"]
        flags = analysis.get("flags", [])
        quality = analysis.get("quality_level", "")

        question = (await db.execute(
            select(Question).where(Question.id == qid)
        )).scalar_one_or_none()

        if not question:
            continue

        # Auto-archive questions with negative discrimination
        if ctt["discrimination"] < 0 and question.status != QuestionStatus.ARCHIVED.value:
            question.status = QuestionStatus.ARCHIVED
            archived.append({
                "question_id": str(qid),
                "reason": "负区分度",
                "discrimination": ctt["discrimination"],
                "difficulty_index": ctt["difficulty_index"],
            })
        # Flag low quality for review
        elif quality == "问题" or quality == "待改进":
            flagged.append({
                "question_id": str(qid),
                "quality_level": quality,
                "flags": flags,
                "discrimination": ctt["discrimination"],
                "difficulty_index": ctt["difficulty_index"],
            })

        # Recalibrate difficulty based on actual performance
        new_difficulty = _recalibrate_difficulty(ctt["difficulty_index"])
        if new_difficulty != question.difficulty:
            old_diff = question.difficulty
            question.difficulty = new_difficulty
            recalibrated.append({
                "question_id": str(qid),
                "old_difficulty": old_diff,
                "new_difficulty": new_difficulty,
                "actual_difficulty_index": ctt["difficulty_index"],
            })

    await db.flush()

    return {
        "scanned": len(rows),
        "flagged": flagged,
        "flagged_count": len(flagged),
        "archived": archived,
        "archived_count": len(archived),
        "recalibrated": recalibrated,
        "recalibrated_count": len(recalibrated),
    }


async def calibrate_question_difficulty(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> dict:
    """Recalibrate a single question's difficulty based on actual data."""
    analysis = await analyze_question(db, question_id)
    if analysis["sample_size"] == 0:
        return {"question_id": str(question_id), "calibrated": False, "reason": "暂无答题数据"}

    question = (await db.execute(
        select(Question).where(Question.id == question_id)
    )).scalar_one_or_none()

    if not question:
        return {"question_id": str(question_id), "calibrated": False, "reason": "题目不存在"}

    ctt = analysis["ctt"]
    new_difficulty = _recalibrate_difficulty(ctt["difficulty_index"])
    old_difficulty = question.difficulty

    if new_difficulty != old_difficulty:
        question.difficulty = new_difficulty
        await db.flush()
        return {
            "question_id": str(question_id),
            "calibrated": True,
            "old_difficulty": old_difficulty,
            "new_difficulty": new_difficulty,
            "actual_difficulty_index": ctt["difficulty_index"],
            "sample_size": analysis["sample_size"],
        }
    else:
        return {
            "question_id": str(question_id),
            "calibrated": False,
            "reason": "难度无需调整",
            "current_difficulty": old_difficulty,
            "actual_difficulty_index": ctt["difficulty_index"],
        }


async def find_similar_questions(
    db: AsyncSession,
    threshold: float = 0.9,
    limit: int = 50,
) -> list[dict]:
    """Find potentially duplicate questions using text similarity.

    Uses a simplified text overlap approach (Jaccard similarity on character n-grams)
    since we don't have vector embeddings set up.
    """
    result = await db.execute(
        select(Question)
        .where(Question.status != QuestionStatus.ARCHIVED)
        .order_by(Question.created_at.desc())
        .limit(limit * 2)
    )
    questions = list(result.scalars().all())

    if len(questions) < 2:
        return []

    similar_pairs = []
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            sim = _text_similarity(questions[i].stem, questions[j].stem)
            if sim >= threshold:
                similar_pairs.append({
                    "question_a": {
                        "id": str(questions[i].id),
                        "stem": questions[i].stem[:100],
                        "dimension": questions[i].dimension,
                    },
                    "question_b": {
                        "id": str(questions[j].id),
                        "stem": questions[j].stem[:100],
                        "dimension": questions[j].dimension,
                    },
                    "similarity": round(sim, 4),
                    "suggestion": "合并" if sim >= 0.95 else "检查",
                })

    similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return similar_pairs[:limit]


def _recalibrate_difficulty(difficulty_index: float) -> int:
    """Map CTT difficulty index to 1-5 difficulty scale.

    difficulty_index: 0 = hardest (nobody gets right), 1 = easiest (everyone gets right)
    """
    if difficulty_index >= 0.9:
        return 1  # Very easy
    elif difficulty_index >= 0.7:
        return 2  # Easy
    elif difficulty_index >= 0.5:
        return 3  # Medium
    elif difficulty_index >= 0.3:
        return 4  # Hard
    else:
        return 5  # Very hard


def _text_similarity(text_a: str, text_b: str) -> float:
    """Compute text similarity using character n-gram Jaccard similarity."""
    if not text_a or not text_b:
        return 0.0

    n = 3  # trigrams
    ngrams_a = set(_ngrams(text_a, n))
    ngrams_b = set(_ngrams(text_b, n))

    if not ngrams_a or not ngrams_b:
        return 0.0

    intersection = ngrams_a & ngrams_b
    union = ngrams_a | ngrams_b

    return len(intersection) / len(union) if union else 0.0


def _ngrams(text: str, n: int) -> list[str]:
    """Generate character n-grams from text."""
    cleaned = text.replace(" ", "").replace("\n", "")
    return [cleaned[i:i+n] for i in range(len(cleaned) - n + 1)]
