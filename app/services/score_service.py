"""Score service - handles scoring, grading, and report generation."""
import logging
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

logger = logging.getLogger(__name__)

# Objective types that can be auto-scored
OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}


def normalize_true_false_answer(answer: str | None) -> str:
    """Normalize true/false answer aliases to the canonical T/F format."""
    if answer is None:
        return ""

    value = str(answer).strip()
    if not value:
        return ""

    for prefix in ("参考答案：", "参考答案:", "正确答案：", "正确答案:", "答案：", "答案:", "答："):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break

    compact = value.replace(" ", "").replace("　", "")
    upper = compact.upper()

    true_values = {"A", "T", "TRUE", "Y", "YES", "正确", "对", "是", "√", "✓"}
    false_values = {"B", "F", "FALSE", "N", "NO", "错误", "错", "否", "×", "✗", "X"}

    if upper in true_values or compact in true_values:
        return "T"
    if upper in false_values or compact in false_values:
        return "F"

    if "正确" in compact or "√" in compact or "✓" in compact:
        return "T"
    if "错误" in compact or "错" in compact or "×" in compact or "✗" in compact:
        return "F"

    letters = [char for char in upper if char in {"A", "B", "T", "F"}]
    if letters:
        first = letters[0]
        return "T" if first in {"A", "T"} else "F"

    return upper


def _earned_ratio(earned_score: float, max_score: float) -> float:
    return round(earned_score / max_score, 4) if max_score > 0 else 0.0


def _score_status(earned_score: float, max_score: float, is_correct: Optional[bool]) -> str:
    if is_correct is None:
        return "manual_review"
    if max_score <= 0:
        return "full_score"
    if earned_score >= max_score:
        return "full_score"
    if earned_score <= 0:
        return "zero_score"
    return "partial_score"


def _objective_analysis(
    *,
    earned_score: float,
    max_score: float,
    judgement: str,
    positive_points: list[str] | None = None,
    missed_points: list[str] | None = None,
    error_reasons: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict:
    return {
        "earned_ratio": _earned_ratio(earned_score, max_score),
        "judgement": judgement,
        "positive_points": positive_points or [],
        "missed_points": missed_points or [],
        "error_reasons": error_reasons or [],
        "confidence": 1.0,
        "evidence": evidence or [],
        "scoring_source": "rule",
    }


def _score_objective(
    question: Question,
    answer_content: str,
    max_score: float,
    effective_type: str = "",
    correct_answer: str = "",
) -> dict:
    """Score an objective question by comparing answers."""
    raw_correct = correct_answer or question.correct_answer or ""
    correct = raw_correct.strip().upper()
    student = answer_content.strip().upper() if answer_content else ""

    # Use effective_type (which includes override) if provided; fall back to original
    qtype = effective_type or (question.question_type.value if hasattr(question.question_type, 'value') else question.question_type)

    if qtype == "true_false":
        correct = normalize_true_false_answer(raw_correct)
        student = normalize_true_false_answer(answer_content)

    # If correct answer is missing, cannot auto-score — flag for manual review
    if not correct:
        logger.warning(f"Question {question.id} ({qtype}) has no correct_answer, cannot auto-score")
        return {
            "earned_score": 0.0,
            "is_correct": None,
            "feedback": f"⚠️ 该题缺少标准答案，无法自动评分。考生作答：{student or '（未作答）'}",
            "analysis": _objective_analysis(
                earned_score=0.0,
                max_score=max_score,
                judgement="该题缺少标准答案，无法自动评分。",
                missed_points=["缺少标准答案，需人工复核。"],
                error_reasons=["manual_review_required"],
                evidence=[f"学生答案：{student or '(未作答)'}"],
            ),
        }

    if qtype == "multiple_choice":
        correct_set = set(correct)
        student_set = set(student)
        if correct_set == student_set:
            return {
                "earned_score": max_score,
                "is_correct": True,
                "feedback": "正确",
                "analysis": _objective_analysis(
                    earned_score=max_score,
                    max_score=max_score,
                    judgement="答案正确。",
                    positive_points=["选择项与标准答案完全一致。"],
                    evidence=[f"标准答案：{correct}", f"学生答案：{student}"],
                ),
            }
        elif student_set.issubset(correct_set) and len(student_set) > 0:
            # Partial credit for subset
            partial = round(max_score * len(student_set) / len(correct_set) * 0.5, 1)
            return {
                "earned_score": partial,
                "is_correct": False,
                "feedback": f"部分正确，漏选。正确答案：{correct}",
                "analysis": _objective_analysis(
                    earned_score=partial,
                    max_score=max_score,
                    judgement="部分正确，但存在漏选。",
                    positive_points=["答案命中了部分正确选项。"],
                    missed_points=[f"遗漏正确选项：{''.join(sorted(correct_set - student_set))}"],
                    error_reasons=["incomplete_answer"],
                    evidence=[f"标准答案：{correct}", f"学生答案：{student}"],
                ),
            }
        else:
            return {
                "earned_score": 0.0,
                "is_correct": False,
                "feedback": f"错误。正确答案：{correct}",
                "analysis": _objective_analysis(
                    earned_score=0.0,
                    max_score=max_score,
                    judgement="答案与标准答案不匹配。",
                    missed_points=[f"正确答案应为：{correct}"],
                    error_reasons=["concept_error"],
                    evidence=[f"标准答案：{correct}", f"学生答案：{student or '(未作答)'}"],
                ),
            }
    else:
        if correct == student:
            return {
                "earned_score": max_score,
                "is_correct": True,
                "feedback": "正确",
                "analysis": _objective_analysis(
                    earned_score=max_score,
                    max_score=max_score,
                    judgement="答案正确。",
                    positive_points=["回答与标准答案一致。"],
                    evidence=[f"标准答案：{correct}", f"学生答案：{student}"],
                ),
            }
        else:
            return {
                "earned_score": 0.0,
                "is_correct": False,
                "feedback": f"错误。正确答案：{correct}",
                "analysis": _objective_analysis(
                    earned_score=0.0,
                    max_score=max_score,
                    judgement="答案错误。",
                    missed_points=[f"正确答案应为：{correct}"],
                    error_reasons=["concept_error"],
                    evidence=[f"标准答案：{correct}", f"学生答案：{student or '(未作答)'}"],
                ),
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

        orig_type = question.question_type.value if hasattr(question.question_type, 'value') else question.question_type
        # Use question_type_override from exam_question if set
        qtype = eq.question_type_override or orig_type
        # Use correct_answer_override if set, otherwise fall back to original
        effective_correct_answer = eq.correct_answer_override or question.correct_answer or ""

        if qtype in OBJECTIVE_TYPES:
            result = _score_objective(question, answer_content, max_score, effective_type=qtype, correct_answer=effective_correct_answer)
        else:
            result = score_subjective_answer(
                stem=question.stem,
                correct_answer=effective_correct_answer,
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

    wrong_details = [d for d in score.details if d.earned_score < d.max_score]
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
        answer_text = a.answer_content if a else ""
        analysis = _normalized_detail_analysis(
            detail=detail,
            question=q,
            question_type=qtype,
            user_answer=answer_text,
        )
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
            "user_answer": answer_text,
            "earned_score": detail.earned_score,
            "max_score": detail.max_score,
            "is_correct": detail.is_correct,
            "has_deduction": detail.earned_score < detail.max_score,
            "score_status": _score_status(detail.earned_score, detail.max_score, detail.is_correct),
            "feedback": detail.feedback,
            "analysis": analysis,
            "error_reasons": analysis.get("error_reasons", []),
            "missed_points": analysis.get("missed_points", []),
            "positive_points": analysis.get("positive_points", []),
            "reference_answer": q.correct_answer,
        })
    return items


def _normalized_detail_analysis(
    *,
    detail: ScoreDetail,
    question: Question,
    question_type: str,
    user_answer: str,
) -> dict:
    analysis = dict(detail.analysis or {})
    earned_score = detail.earned_score
    max_score = detail.max_score

    if not analysis:
        judgement = _default_judgement(earned_score, max_score, detail.is_correct)
        analysis = {
            "earned_ratio": _earned_ratio(earned_score, max_score),
            "judgement": judgement,
            "positive_points": [],
            "missed_points": [],
            "error_reasons": [],
            "confidence": 1.0 if question_type in OBJECTIVE_TYPES else 0.5,
            "evidence": [],
            "scoring_source": "rule" if question_type in OBJECTIVE_TYPES else "unknown",
        }

    analysis.setdefault("earned_ratio", _earned_ratio(earned_score, max_score))
    analysis.setdefault("judgement", _default_judgement(earned_score, max_score, detail.is_correct))
    analysis.setdefault("positive_points", [])
    analysis.setdefault("missed_points", [])
    analysis.setdefault("error_reasons", [])
    analysis.setdefault("confidence", 1.0 if question_type in OBJECTIVE_TYPES else 0.5)
    analysis.setdefault("evidence", [])
    analysis.setdefault("scoring_source", "rule" if question_type in OBJECTIVE_TYPES else "unknown")

    if question_type in OBJECTIVE_TYPES:
        correct_answer = question.correct_answer or ""
        if earned_score >= max_score and max_score > 0:
            analysis["positive_points"] = analysis.get("positive_points") or ["回答与标准答案一致。"]
        elif earned_score < max_score and not analysis.get("missed_points") and correct_answer:
            analysis["missed_points"] = [f"正确答案应为：{correct_answer}"]
        if not analysis.get("evidence"):
            evidence = []
            if correct_answer:
                evidence.append(f"标准答案：{correct_answer}")
            evidence.append(f"学生答案：{user_answer or '(未作答)'}")
            analysis["evidence"] = evidence

    return analysis


def _default_judgement(
    earned_score: float,
    max_score: float,
    is_correct: Optional[bool],
) -> str:
    if is_correct is None:
        return "该题需要人工复核。"
    if max_score > 0 and earned_score >= max_score:
        return "本题获得满分。"
    if earned_score <= 0:
        return "本题未得分。"
    return "本题获得部分分数，仍存在扣分点。"


async def get_all_answer_details(
    db: AsyncSession,
    score_id: uuid.UUID,
) -> list[dict]:
    """Get ALL answer details (correct and wrong) with full question data, ordered by exam question order."""
    from app.models.exam import ExamQuestion

    score = await get_score_by_id(db, score_id, load_details=True)
    if not score:
        raise ValueError("成绩不存在")

    all_qids = [d.question_id for d in score.details]
    if not all_qids:
        return []

    # Batch-fetch questions
    result = await db.execute(
        select(Question).where(Question.id.in_(all_qids))
    )
    questions_map = {q.id: q for q in result.scalars().all()}

    # Batch-fetch user answers
    result = await db.execute(
        select(Answer).where(
            and_(
                Answer.answer_sheet_id == score.answer_sheet_id,
                Answer.question_id.in_(all_qids),
            )
        )
    )
    answers_map = {a.question_id: a for a in result.scalars().all()}

    # Get exam question ordering via answer_sheet -> exam_id
    sheet = (await db.execute(
        select(AnswerSheet).where(AnswerSheet.id == score.answer_sheet_id)
    )).scalar_one()

    eq_result = await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == sheet.exam_id)
    )
    order_map = {}
    override_map = {}
    for eq in eq_result.scalars().all():
        order_map[eq.question_id] = eq.order_num
        if eq.question_type_override:
            override_map[eq.question_id] = eq.question_type_override

    items = []
    for detail in score.details:
        q = questions_map.get(detail.question_id)
        a = answers_map.get(detail.question_id)
        if not q:
            continue
        qtype = override_map.get(q.id) or (q.question_type.value if hasattr(q.question_type, 'value') else q.question_type)
        answer_text = a.answer_content if a else ""
        analysis = _normalized_detail_analysis(
            detail=detail,
            question=q,
            question_type=qtype,
            user_answer=answer_text,
        )
        score_status = _score_status(detail.earned_score, detail.max_score, detail.is_correct)
        items.append({
            "score_detail_id": str(detail.id),
            "question_id": str(q.id),
            "question_type": qtype,
            "stem": q.stem,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "dimension": q.dimension,
            "difficulty": q.difficulty,
            "knowledge_tags": q.knowledge_tags,
            "user_answer": answer_text,
            "earned_score": detail.earned_score,
            "max_score": detail.max_score,
            "is_correct": detail.is_correct,
            "has_deduction": detail.earned_score < detail.max_score,
            "score_status": score_status,
            "feedback": detail.feedback,
            "analysis": analysis,
            "reference_answer": q.correct_answer,
            "order_num": order_map.get(q.id, 0),
        })

    items.sort(key=lambda x: x["order_num"])
    return items


async def create_complaint(
    db: AsyncSession,
    score_detail_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
):
    """Create a score complaint for a specific question."""
    from app.models.score import ScoreComplaint, ComplaintStatus, ScoreDetail as SD

    # Verify score_detail exists
    detail = (await db.execute(
        select(SD).where(SD.id == score_detail_id)
    )).scalar_one_or_none()
    if not detail:
        raise ValueError("评分详情不存在")

    # Check for duplicate pending complaint
    existing = (await db.execute(
        select(ScoreComplaint).where(
            and_(
                ScoreComplaint.score_detail_id == score_detail_id,
                ScoreComplaint.user_id == user_id,
                ScoreComplaint.status == ComplaintStatus.PENDING,
            )
        )
    )).scalar_one_or_none()
    if existing:
        raise ValueError("您已对该题提交过投诉，请等待处理")

    complaint = ScoreComplaint(
        score_detail_id=score_detail_id,
        user_id=user_id,
        reason=reason,
    )
    db.add(complaint)
    await db.flush()
    return complaint


async def list_complaints(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> tuple[list[dict], int]:
    """List all complaints with context (admin view)."""
    from app.models.score import ScoreComplaint, ScoreDetail as SD
    from app.models.user import User

    base = (
        select(
            ScoreComplaint,
            SD.question_id,
            SD.earned_score,
            SD.max_score,
            Question.stem,
            Question.question_type,
            User.username,
            User.full_name,
        )
        .join(SD, ScoreComplaint.score_detail_id == SD.id)
        .join(Question, SD.question_id == Question.id)
        .join(User, ScoreComplaint.user_id == User.id)
    )
    count_base = (
        select(func.count(ScoreComplaint.id))
        .select_from(ScoreComplaint)
    )

    if status_filter:
        base = base.where(ScoreComplaint.status == status_filter)
        count_base = count_base.where(ScoreComplaint.status == status_filter)

    total = (await db.execute(count_base)).scalar() or 0
    result = await db.execute(
        base.order_by(ScoreComplaint.created_at.desc()).offset(skip).limit(limit)
    )

    items = []
    for row in result.all():
        c = row[0]
        items.append({
            "id": str(c.id),
            "score_detail_id": str(c.score_detail_id),
            "user_id": str(c.user_id),
            "username": row.username,
            "full_name": row.full_name,
            "question_stem": row.stem[:80] if row.stem else "",
            "question_type": row.question_type.value if hasattr(row.question_type, 'value') else row.question_type,
            "earned_score": row.earned_score,
            "max_score": row.max_score,
            "reason": c.reason,
            "status": c.status.value if hasattr(c.status, 'value') else c.status,
            "reply": c.reply,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    return items, total


async def handle_complaint(
    db: AsyncSession,
    complaint_id: uuid.UUID,
    new_status: str,
    reply: str = "",
):
    """Handle a complaint: accept or reject with reply."""
    from app.models.score import ScoreComplaint, ComplaintStatus

    complaint = (await db.execute(
        select(ScoreComplaint).where(ScoreComplaint.id == complaint_id)
    )).scalar_one_or_none()
    if not complaint:
        raise ValueError("投诉不存在")

    try:
        complaint.status = ComplaintStatus(new_status)
    except ValueError:
        raise ValueError(f"无效的状态: {new_status}")

    complaint.reply = reply
    await db.flush()
    return complaint


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
