"""Question quality analysis service - CTT and basic IRT metrics."""
import math
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.models.score import Score, ScoreDetail
from app.models.answer import AnswerSheet


async def analyze_question(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> dict:
    """Compute CTT metrics for a single question based on answer data."""
    # Get all score details for this question
    result = await db.execute(
        select(ScoreDetail)
        .where(ScoreDetail.question_id == question_id)
    )
    details = list(result.scalars().all())

    if not details:
        return {
            "question_id": str(question_id),
            "sample_size": 0,
            "message": "暂无答题数据",
        }

    n = len(details)
    correct_count = sum(1 for d in details if d.is_correct)
    difficulty_index = correct_count / n if n > 0 else 0

    # Discrimination: point-biserial correlation approximation
    # Split into top 27% and bottom 27% by total score
    discrimination = await _compute_discrimination(db, details, question_id)

    # Reliability placeholder (Cronbach's alpha requires multi-item analysis)
    reliability = await _compute_reliability_contribution(db, details, question_id)

    # Flag anomalies
    flags = []
    if difficulty_index < 0.2:
        flags.append("过难：正确率低于20%")
    elif difficulty_index > 0.95:
        flags.append("过易：正确率高于95%")
    if discrimination < 0.2:
        flags.append("区分度低：低于0.2")
    if discrimination < 0:
        flags.append("负区分度：需检查题目质量")

    # Update question record
    question = (await db.execute(
        select(Question).where(Question.id == question_id)
    )).scalar_one_or_none()
    if question:
        question.correct_rate = round(difficulty_index, 4)
        question.discrimination = round(discrimination, 4)

    return {
        "question_id": str(question_id),
        "sample_size": n,
        "ctt": {
            "difficulty_index": round(difficulty_index, 4),
            "discrimination": round(discrimination, 4),
            "correct_count": correct_count,
            "reliability_contribution": round(reliability, 4),
        },
        "irt": _estimate_irt_params(difficulty_index, discrimination),
        "flags": flags,
        "quality_level": _quality_level(difficulty_index, discrimination),
    }


async def analyze_exam_questions(
    db: AsyncSession,
    exam_id: uuid.UUID,
) -> dict:
    """Analyze all questions in an exam."""
    from app.models.exam import ExamQuestion
    result = await db.execute(
        select(ExamQuestion.question_id)
        .where(ExamQuestion.exam_id == exam_id)
    )
    question_ids = [r[0] for r in result.all()]

    if not question_ids:
        return {"exam_id": str(exam_id), "questions": [], "summary": {}}

    analyses = []
    for qid in question_ids:
        analysis = await analyze_question(db, qid)
        analyses.append(analysis)

    await db.flush()

    # Exam-level summary
    with_data = [a for a in analyses if a["sample_size"] > 0]
    flagged = [a for a in with_data if a.get("flags")]

    avg_difficulty = (
        sum(a["ctt"]["difficulty_index"] for a in with_data) / len(with_data)
        if with_data else 0
    )
    avg_discrimination = (
        sum(a["ctt"]["discrimination"] for a in with_data) / len(with_data)
        if with_data else 0
    )

    # Cronbach's alpha for the exam
    alpha = await _compute_cronbach_alpha(db, exam_id)

    return {
        "exam_id": str(exam_id),
        "total_questions": len(question_ids),
        "analyzed_questions": len(with_data),
        "questions": analyses,
        "summary": {
            "avg_difficulty": round(avg_difficulty, 4),
            "avg_discrimination": round(avg_discrimination, 4),
            "cronbach_alpha": round(alpha, 4) if alpha is not None else None,
            "flagged_count": len(flagged),
            "quality_distribution": _quality_distribution(with_data),
        },
    }


async def get_question_quality_report(
    db: AsyncSession,
    min_sample: int = 10,
) -> dict:
    """Generate a global quality report for all questions with enough data."""
    result = await db.execute(
        select(
            ScoreDetail.question_id,
            func.count(ScoreDetail.id).label("cnt"),
        )
        .group_by(ScoreDetail.question_id)
        .having(func.count(ScoreDetail.id) >= min_sample)
    )
    rows = result.all()

    analyses = []
    for qid, cnt in rows:
        analysis = await analyze_question(db, qid)
        analyses.append(analysis)

    await db.flush()

    flagged = [a for a in analyses if a.get("flags")]

    return {
        "total_analyzed": len(analyses),
        "min_sample_size": min_sample,
        "flagged_questions": len(flagged),
        "questions": analyses,
    }


async def _compute_discrimination(
    db: AsyncSession,
    details: list[ScoreDetail],
    question_id: uuid.UUID,
) -> float:
    """Compute discrimination index using top/bottom 27% method."""
    if len(details) < 4:
        # Too few responses for meaningful discrimination
        correct_count = sum(1 for d in details if d.is_correct)
        return correct_count / len(details) if details else 0

    # Get total scores for all answer sheets that contain this question
    score_ids = list(set(d.score_id for d in details))
    result = await db.execute(
        select(Score.id, Score.total_score, Score.max_score)
        .where(Score.id.in_(score_ids))
    )
    score_map = {r[0]: r[1] / r[2] if r[2] > 0 else 0 for r in result.all()}

    # Map each detail to total score ratio
    detail_scores = []
    for d in details:
        ratio = score_map.get(d.score_id, 0)
        detail_scores.append((d.is_correct, ratio))

    detail_scores.sort(key=lambda x: x[1])
    n = len(detail_scores)
    k = max(1, int(n * 0.27))

    bottom_group = detail_scores[:k]
    top_group = detail_scores[-k:]

    top_correct = sum(1 for c, _ in top_group if c)
    bottom_correct = sum(1 for c, _ in bottom_group if c)

    discrimination = (top_correct - bottom_correct) / k if k > 0 else 0
    return max(-1.0, min(1.0, discrimination))


async def _compute_reliability_contribution(
    db: AsyncSession,
    details: list[ScoreDetail],
    question_id: uuid.UUID,
) -> float:
    """Estimate this question's contribution to test reliability."""
    if len(details) < 2:
        return 0.0

    scores = [d.earned_score / d.max_score if d.max_score > 0 else 0 for d in details]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    return variance


async def _compute_cronbach_alpha(
    db: AsyncSession,
    exam_id: uuid.UUID,
) -> Optional[float]:
    """Compute Cronbach's alpha for exam reliability."""
    from app.models.exam import ExamQuestion

    # Get all question IDs in this exam
    result = await db.execute(
        select(ExamQuestion.question_id)
        .where(ExamQuestion.exam_id == exam_id)
    )
    question_ids = [r[0] for r in result.all()]
    if len(question_ids) < 2:
        return None

    # Get all answer sheets for this exam
    result = await db.execute(
        select(AnswerSheet.id)
        .where(AnswerSheet.exam_id == exam_id)
        .where(AnswerSheet.status == "scored")
    )
    sheet_ids = [r[0] for r in result.all()]
    if len(sheet_ids) < 2:
        return None

    # Get scores for this exam
    result = await db.execute(
        select(Score)
        .where(Score.answer_sheet_id.in_(sheet_ids))
    )
    score_objs = list(result.scalars().all())
    if len(score_objs) < 2:
        return None

    score_ids = [s.id for s in score_objs]

    # Get all score details
    result = await db.execute(
        select(ScoreDetail)
        .where(ScoreDetail.score_id.in_(score_ids))
        .where(ScoreDetail.question_id.in_(question_ids))
    )
    all_details = list(result.scalars().all())

    # Build score matrix: rows = examinees, cols = questions
    score_matrix = {}  # score_id -> {question_id -> ratio}
    for d in all_details:
        if d.score_id not in score_matrix:
            score_matrix[d.score_id] = {}
        score_matrix[d.score_id][d.question_id] = (
            d.earned_score / d.max_score if d.max_score > 0 else 0
        )

    if len(score_matrix) < 2:
        return None

    k = len(question_ids)

    # Compute item variances
    item_variances = []
    for qid in question_ids:
        values = [score_matrix[sid].get(qid, 0) for sid in score_matrix]
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        item_variances.append(var)

    sum_item_var = sum(item_variances)

    # Compute total score variance
    total_scores = []
    for sid in score_matrix:
        total = sum(score_matrix[sid].get(qid, 0) for qid in question_ids)
        total_scores.append(total)

    total_mean = sum(total_scores) / len(total_scores)
    total_var = sum((t - total_mean) ** 2 for t in total_scores) / len(total_scores)

    if total_var == 0:
        return 0.0

    alpha = (k / (k - 1)) * (1 - sum_item_var / total_var)
    return max(-1.0, min(1.0, alpha))


def _estimate_irt_params(difficulty_index: float, discrimination: float) -> dict:
    """Estimate basic IRT 2PL parameters from CTT metrics."""
    # Map CTT difficulty to IRT difficulty (b parameter)
    # IRT b is on logit scale: higher b = harder
    if difficulty_index <= 0:
        b = 4.0
    elif difficulty_index >= 1:
        b = -4.0
    else:
        b = -math.log(difficulty_index / (1 - difficulty_index))
    b = max(-4.0, min(4.0, b))

    # Map CTT discrimination to IRT discrimination (a parameter)
    # a is typically 0.5-2.5
    a = max(0.1, min(3.0, discrimination * 2.5))

    # Guessing parameter (c) - assume 0.25 for 4-option MCQ
    c = 0.25

    return {
        "difficulty_b": round(b, 4),
        "discrimination_a": round(a, 4),
        "guessing_c": c,
    }


def _quality_level(difficulty_index: float, discrimination: float) -> str:
    """Classify question quality based on CTT metrics."""
    if discrimination >= 0.4 and 0.3 <= difficulty_index <= 0.8:
        return "优质"
    elif discrimination >= 0.2 and 0.2 <= difficulty_index <= 0.9:
        return "合格"
    elif discrimination < 0:
        return "问题"
    else:
        return "待改进"


def _quality_distribution(analyses: list[dict]) -> dict:
    """Count questions by quality level."""
    dist = {"优质": 0, "合格": 0, "待改进": 0, "问题": 0}
    for a in analyses:
        level = a.get("quality_level", "待改进")
        dist[level] = dist.get(level, 0) + 1
    return dist
