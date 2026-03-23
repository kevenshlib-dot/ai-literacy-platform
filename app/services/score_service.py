"""Score service - handles scoring, grading, and report generation."""
import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.score import Score, ScoreDetail
from app.models.answer import AnswerSheet, Answer, AnswerSheetStatus
from app.models.exam import ExamQuestion
from app.models.question import Question
from app.agents.scoring_agent import score_subjective_answer
from app.services.report_storage import SCORE_REPORT_KEY, get_report_namespace, set_report_namespace

# Objective types that can be auto-scored
OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}


def _score_objective(
    question: Question,
    answer_content: str,
    max_score: float,
) -> dict:
    """Score an objective question by comparing answers."""
    correct = question.correct_answer.strip().upper()
    student = answer_content.strip().upper() if answer_content else ""

    qtype = question.question_type.value if hasattr(question.question_type, 'value') else question.question_type

    if qtype == "multiple_choice":
        correct_set = set(correct)
        student_set = set(student)
        if correct_set == student_set:
            return {"earned_score": max_score, "is_correct": True, "feedback": "正确"}
        elif student_set.issubset(correct_set) and len(student_set) > 0:
            # Partial credit for subset
            partial = round(max_score * len(student_set) / len(correct_set) * 0.5, 1)
            return {
                "earned_score": partial,
                "is_correct": False,
                "feedback": f"部分正确，漏选。正确答案：{correct}",
                "analysis": {
                    "earned_ratio": round(partial / max_score, 4) if max_score > 0 else 0.0,
                    "judgement": "部分正确，但存在漏选。",
                    "positive_points": ["答案命中了部分正确选项。"],
                    "missed_points": [f"遗漏正确选项：{''.join(sorted(correct_set - student_set))}"],
                    "error_reasons": ["incomplete_answer"],
                    "confidence": 1.0,
                    "evidence": [f"标准答案：{correct}", f"学生答案：{student}"],
                    "scoring_source": "rule",
                },
            }
        else:
            return {
                "earned_score": 0.0,
                "is_correct": False,
                "feedback": f"错误。正确答案：{correct}",
                "analysis": {
                    "earned_ratio": 0.0,
                    "judgement": "答案与标准答案不匹配。",
                    "positive_points": [],
                    "missed_points": [f"正确答案应为：{correct}"],
                    "error_reasons": ["concept_error"],
                    "confidence": 1.0,
                    "evidence": [f"标准答案：{correct}", f"学生答案：{student or '(未作答)'}"],
                    "scoring_source": "rule",
                },
            }
    else:
        if correct == student:
            return {
                "earned_score": max_score,
                "is_correct": True,
                "feedback": "正确",
                "analysis": {
                    "earned_ratio": 1.0,
                    "judgement": "答案正确。",
                    "positive_points": ["回答与标准答案一致。"],
                    "missed_points": [],
                    "error_reasons": [],
                    "confidence": 1.0,
                    "evidence": [f"标准答案：{correct}", f"学生答案：{student}"],
                    "scoring_source": "rule",
                },
            }
        else:
            return {
                "earned_score": 0.0,
                "is_correct": False,
                "feedback": f"错误。正确答案：{correct}",
                "analysis": {
                    "earned_ratio": 0.0,
                    "judgement": "答案错误。",
                    "positive_points": [],
                    "missed_points": [f"正确答案应为：{correct}"],
                    "error_reasons": ["concept_error"],
                    "confidence": 1.0,
                    "evidence": [f"标准答案：{correct}", f"学生答案：{student or '(未作答)'}"],
                    "scoring_source": "rule",
                },
            }


async def score_answer_sheet(
    db: AsyncSession,
    sheet_id: uuid.UUID,
) -> Score:
    """Score a submitted answer sheet."""
    # Load answer sheet with answers
    sheet = (await db.execute(
        select(AnswerSheet)
        .where(AnswerSheet.id == sheet_id)
        .options(selectinload(AnswerSheet.answers))
    )).scalar_one_or_none()

    if not sheet:
        raise ValueError("答题卡不存在")
    if sheet.status == AnswerSheetStatus.IN_PROGRESS:
        raise ValueError("考试尚未提交")

    # Check if already scored
    existing = (await db.execute(
        select(Score).where(Score.answer_sheet_id == sheet_id)
    )).scalar_one_or_none()
    if existing:
        raise ValueError("已评分，不能重复评分")

    # Load exam questions with question details
    eq_result = await db.execute(
        select(ExamQuestion, Question)
        .join(Question, ExamQuestion.question_id == Question.id)
        .where(ExamQuestion.exam_id == sheet.exam_id)
    )
    eq_map = {}  # question_id -> (ExamQuestion, Question)
    for eq, q in eq_result.all():
        eq_map[q.id] = (eq, q)

    # Build answer map
    answer_map = {}  # question_id -> Answer
    for ans in sheet.answers:
        answer_map[ans.question_id] = ans

    # Score each question
    details = []
    total_earned = 0.0
    total_max = 0.0
    dimension_scores = defaultdict(lambda: {"earned": 0.0, "max": 0.0, "count": 0})

    for qid, (eq, question) in eq_map.items():
        ans = answer_map.get(qid)
        answer_content = ans.answer_content if ans else ""
        max_score = eq.score

        qtype = question.question_type.value if hasattr(question.question_type, 'value') else question.question_type

        if qtype in OBJECTIVE_TYPES:
            result = _score_objective(question, answer_content, max_score)
        else:
            result = score_subjective_answer(
                stem=question.stem,
                correct_answer=question.correct_answer,
                student_answer=answer_content,
                question_type=qtype,
                max_score=max_score,
                rubric=question.rubric,
            )

        detail = ScoreDetail(
            question_id=qid,
            earned_score=result["earned_score"],
            max_score=max_score,
            is_correct=result.get("is_correct"),
            feedback=result.get("feedback", ""),
            analysis=result.get("analysis"),
        )
        details.append(detail)
        total_earned += result["earned_score"]
        total_max += max_score

        # Track dimension scores
        dim = question.dimension or "未分类"
        dimension_scores[dim]["earned"] += result["earned_score"]
        dimension_scores[dim]["max"] += max_score
        dimension_scores[dim]["count"] += 1

    # Determine level
    ratio = total_earned / total_max if total_max > 0 else 0
    if ratio >= 0.9:
        level = "优秀"
    elif ratio >= 0.8:
        level = "良好"
    elif ratio >= 0.6:
        level = "合格"
    else:
        level = "不合格"

    # Create score record
    score = Score(
        answer_sheet_id=sheet_id,
        total_score=round(total_earned, 1),
        max_score=total_max,
        dimension_scores={
            k: {"earned": round(v["earned"], 1), "max": v["max"], "count": v["count"]}
            for k, v in dimension_scores.items()
        },
        level=level,
    )
    db.add(score)
    await db.flush()

    # Add details
    for detail in details:
        detail.score_id = score.id
        db.add(detail)
    await db.flush()

    # Update answer sheet status
    sheet.status = AnswerSheetStatus.SCORED
    await db.flush()

    return score


async def get_score_by_sheet(
    db: AsyncSession,
    sheet_id: uuid.UUID,
    load_details: bool = False,
) -> Optional[Score]:
    stmt = select(Score).where(Score.answer_sheet_id == sheet_id)
    if load_details:
        stmt = stmt.options(selectinload(Score.details))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_score_by_id(
    db: AsyncSession,
    score_id: uuid.UUID,
    load_details: bool = False,
) -> Optional[Score]:
    stmt = select(Score).where(Score.id == score_id)
    if load_details:
        stmt = stmt.options(selectinload(Score.details))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def generate_report(
    db: AsyncSession,
    score_id: uuid.UUID,
    force_refresh: bool = False,
) -> dict:
    """Generate a score report with analysis."""
    score = await get_score_by_id(db, score_id, load_details=True)
    if not score:
        raise ValueError("成绩不存在")
    if not force_refresh:
        cached = get_report_namespace(score, SCORE_REPORT_KEY)
        if cached:
            return cached

    total_questions = len(score.details)
    correct_count = sum(1 for d in score.details if d.is_correct)
    ratio = score.total_score / score.max_score if score.max_score > 0 else 0

    # Dimension analysis
    dim_analysis = {}
    if score.dimension_scores:
        for dim, data in score.dimension_scores.items():
            dim_ratio = data["earned"] / data["max"] if data["max"] > 0 else 0
            dim_analysis[dim] = {
                "earned": data["earned"],
                "max": data["max"],
                "count": data["count"],
                "ratio": round(dim_ratio, 2),
                "level": "优秀" if dim_ratio >= 0.9 else "良好" if dim_ratio >= 0.8 else "合格" if dim_ratio >= 0.6 else "需提升",
            }

    # Weak dimensions
    weak_dims = [k for k, v in dim_analysis.items() if v["ratio"] < 0.6]

    report = {
        "score_id": str(score.id),
        "total_score": score.total_score,
        "max_score": score.max_score,
        "ratio": round(ratio, 2),
        "level": score.level,
        "total_questions": total_questions,
        "correct_count": correct_count,
        "accuracy": round(correct_count / total_questions, 2) if total_questions > 0 else 0,
        "dimension_analysis": dim_analysis,
        "weak_dimensions": weak_dims,
        "recommendations": _generate_recommendations(dim_analysis, weak_dims),
    }

    # Save report to score record
    set_report_namespace(score, SCORE_REPORT_KEY, report)
    await db.flush()

    return report


async def get_wrong_answer_details(
    db: AsyncSession,
    score_id: uuid.UUID,
) -> list[dict]:
    """Get wrong answer details with full question and user answer data for review."""
    score = await get_score_by_id(db, score_id, load_details=True)
    if not score:
        raise ValueError("成绩不存在")

    wrong_details = [d for d in score.details if not d.is_correct]
    if not wrong_details:
        return []

    wrong_qids = [d.question_id for d in wrong_details]

    # Batch-fetch questions
    result = await db.execute(
        select(Question).where(Question.id.in_(wrong_qids))
    )
    questions_map = {q.id: q for q in result.scalars().all()}

    # Batch-fetch user answers
    result = await db.execute(
        select(Answer).where(
            and_(
                Answer.answer_sheet_id == score.answer_sheet_id,
                Answer.question_id.in_(wrong_qids),
            )
        )
    )
    answers_map = {a.question_id: a for a in result.scalars().all()}

    items = []
    for detail in wrong_details:
        q = questions_map.get(detail.question_id)
        a = answers_map.get(detail.question_id)
        if not q:
            continue
        qtype = q.question_type.value if hasattr(q.question_type, 'value') else q.question_type
        items.append({
            "question_id": str(q.id),
            "question_type": qtype,
            "stem": q.stem,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "dimension": q.dimension,
            "difficulty": q.difficulty,
            "knowledge_tags": q.knowledge_tags,
            "user_answer": a.answer_content if a else "",
            "earned_score": detail.earned_score,
            "max_score": detail.max_score,
            "feedback": detail.feedback,
            "analysis": detail.analysis or {},
            "error_reasons": (detail.analysis or {}).get("error_reasons", []),
            "missed_points": (detail.analysis or {}).get("missed_points", []),
            "positive_points": (detail.analysis or {}).get("positive_points", []),
            "reference_answer": q.correct_answer,
        })
    return items


def serialize_score_detail(detail: ScoreDetail) -> dict:
    return {
        "question_id": str(detail.question_id),
        "earned_score": detail.earned_score,
        "max_score": detail.max_score,
        "is_correct": detail.is_correct,
        "feedback": detail.feedback,
        "analysis": detail.analysis or {},
    }


def _generate_recommendations(dim_analysis: dict, weak_dims: list) -> list[str]:
    """Generate learning recommendations based on performance."""
    recs = []
    if not weak_dims:
        recs.append("整体表现良好，建议继续保持并挑战更高难度。")
    else:
        for dim in weak_dims:
            recs.append(f"「{dim}」维度得分较低，建议重点复习相关知识。")

    for dim, data in dim_analysis.items():
        if data["ratio"] >= 0.9:
            recs.append(f"「{dim}」维度表现优秀。")

    return recs
