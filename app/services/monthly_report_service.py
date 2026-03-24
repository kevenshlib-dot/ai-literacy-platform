"""Monthly report service - auto-generate platform operations reports."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionStatus
from app.models.material import Material
from app.models.exam import Exam
from app.models.answer import AnswerSheet, AnswerSheetStatus
from app.models.score import Score, ScoreDetail
from app.models.user import User
from app.models.report import Report
from app.services.question_service import get_question_stats


async def generate_monthly_report(
    db: AsyncSession,
    year: int,
    month: int,
) -> dict:
    """Generate a monthly operations report for the given period."""
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    # Gather all metrics
    test_stats = await _test_volume_stats(db, start_date, end_date)
    score_stats = await _scoring_stats(db, start_date, end_date)
    previous_report = await _get_previous_monthly_report(db, start_date)
    question_health = await _question_bank_health(db, previous_report=previous_report)
    material_stats = await _material_stats(db, start_date, end_date)
    user_stats = await _user_stats(db, start_date, end_date)
    recommendations = _generate_recommendations(
        test_stats, score_stats, question_health, material_stats
    )

    report_data = {
        "period": f"{year}-{month:02d}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_statistics": test_stats,
        "scoring_statistics": score_stats,
        "question_bank_health": question_health,
        "material_statistics": material_stats,
        "user_statistics": user_stats,
        "recommendations": recommendations,
    }

    # Save report record
    report = Report(
        title=f"{year}年{month}月平台运行月报",
        report_type="monthly",
        content=report_data,
        period_start=start_date,
        period_end=end_date,
    )
    db.add(report)
    await db.flush()

    report_data["report_id"] = str(report.id)
    return report_data


async def list_reports(
    db: AsyncSession,
    report_type: Optional[str] = None,
) -> list[dict]:
    """List generated reports."""
    conditions = []
    if report_type:
        conditions.append(Report.report_type == report_type)

    query = select(Report).order_by(Report.created_at.desc())
    if conditions:
        query = query.where(*conditions)

    result = await db.execute(query)
    reports = list(result.scalars().all())

    return [
        {
            "id": str(r.id),
            "title": r.title,
            "report_type": r.report_type,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


async def get_report_detail(
    db: AsyncSession,
    report_id: uuid.UUID,
) -> Optional[dict]:
    """Get full report content."""
    report = (await db.execute(
        select(Report).where(Report.id == report_id)
    )).scalar_one_or_none()

    if not report:
        return None

    return {
        "id": str(report.id),
        "title": report.title,
        "report_type": report.report_type,
        "content": report.content,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def _test_volume_stats(db: AsyncSession, start: datetime, end: datetime) -> dict:
    """Statistics on test/exam activity."""
    # Total answer sheets in period
    result = await db.execute(
        select(func.count(AnswerSheet.id))
        .where(and_(AnswerSheet.created_at >= start, AnswerSheet.created_at < end))
    )
    total_sessions = result.scalar() or 0

    # Submitted
    result = await db.execute(
        select(func.count(AnswerSheet.id))
        .where(and_(
            AnswerSheet.created_at >= start,
            AnswerSheet.created_at < end,
            AnswerSheet.status == AnswerSheetStatus.SUBMITTED,
        ))
    )
    submitted = result.scalar() or 0

    # Scored
    result = await db.execute(
        select(func.count(AnswerSheet.id))
        .where(and_(
            AnswerSheet.created_at >= start,
            AnswerSheet.created_at < end,
            AnswerSheet.status == AnswerSheetStatus.SCORED,
        ))
    )
    scored = result.scalar() or 0

    # Exams created
    result = await db.execute(
        select(func.count(Exam.id))
        .where(and_(Exam.created_at >= start, Exam.created_at < end))
    )
    exams_created = result.scalar() or 0

    return {
        "total_sessions": total_sessions,
        "submitted": submitted,
        "scored": scored,
        "completion_rate": round(submitted / total_sessions, 4) if total_sessions > 0 else 0,
        "exams_created": exams_created,
    }


async def _scoring_stats(db: AsyncSession, start: datetime, end: datetime) -> dict:
    """Scoring consistency and distribution statistics."""
    result = await db.execute(
        select(Score)
        .where(and_(Score.scored_at >= start, Score.scored_at < end))
    )
    scores = list(result.scalars().all())

    if not scores:
        return {
            "total_scores": 0,
            "avg_score_ratio": 0,
            "score_distribution": {},
            "avg_score": 0,
        }

    ratios = [s.total_score / s.max_score if s.max_score > 0 else 0 for s in scores]
    avg_ratio = sum(ratios) / len(ratios)

    # Distribution by level
    level_dist = {}
    for s in scores:
        level = s.level or "未知"
        level_dist[level] = level_dist.get(level, 0) + 1

    # Pearson correlation placeholder (need at least 2 scoring sources)
    avg_score = sum(s.total_score for s in scores) / len(scores)

    return {
        "total_scores": len(scores),
        "avg_score_ratio": round(avg_ratio, 4),
        "avg_score": round(avg_score, 2),
        "score_distribution": level_dist,
        "highest_ratio": round(max(ratios), 4),
        "lowest_ratio": round(min(ratios), 4),
    }


async def _get_previous_monthly_report(
    db: AsyncSession,
    current_start: datetime,
) -> Optional[Report]:
    """Get the previous monthly report for trend comparison."""
    result = await db.execute(
        select(Report)
        .where(
            and_(
                Report.report_type == "monthly",
                Report.period_end != None,
                Report.period_end <= current_start,
            )
        )
        .order_by(Report.period_end.desc(), Report.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _quality_issue_total(metrics: dict) -> int:
    """Aggregate outstanding metadata quality issues for trend comparison."""
    return (
        metrics.get("missing_dimension_count", 0)
        + metrics.get("missing_bloom_level_count", 0)
        + metrics.get("missing_explanation_count", 0)
    )


def _report_period_label(report: Optional[Report]) -> Optional[str]:
    """Build a stable YYYY-MM period label for a stored report."""
    if not report:
        return None
    content = report.content or {}
    if isinstance(content, dict) and content.get("period"):
        return content["period"]
    if report.period_start:
        return report.period_start.strftime("%Y-%m")
    return None


def _build_question_bank_trend(current: dict, previous_report: Optional[Report]) -> dict:
    """Compare the current question bank health snapshot with the previous month."""
    if not previous_report or not isinstance(previous_report.content, dict):
        return {
            "has_previous": False,
            "previous_period": None,
            "direction": "insufficient_data",
            "health_score_delta": 0,
            "quality_issue_total_delta": 0,
            "approved_count_delta": 0,
            "low_discrimination_count_delta": 0,
            "quality_metric_deltas": {},
        }

    previous_health = previous_report.content.get("question_bank_health") or {}
    if not isinstance(previous_health, dict):
        return {
            "has_previous": False,
            "previous_period": None,
            "direction": "insufficient_data",
            "health_score_delta": 0,
            "quality_issue_total_delta": 0,
            "approved_count_delta": 0,
            "low_discrimination_count_delta": 0,
            "quality_metric_deltas": {},
        }

    current_metrics = current.get("quality_metrics", {})
    previous_metrics = previous_health.get("quality_metrics") or {}
    metric_keys = [
        "missing_dimension_count",
        "missing_bloom_level_count",
        "missing_explanation_count",
        "source_linked_count",
        "source_unlinked_count",
    ]
    quality_metric_deltas = {
        key: current_metrics.get(key, 0) - previous_metrics.get(key, 0)
        for key in metric_keys
    }

    health_score_delta = round(
        current.get("health_score", 0) - previous_health.get("health_score", 0),
        1,
    )
    quality_issue_total_delta = (
        _quality_issue_total(current_metrics) - _quality_issue_total(previous_metrics)
    )

    direction = "stable"
    if health_score_delta >= 3 or quality_issue_total_delta <= -1:
        direction = "improving"
    elif health_score_delta <= -3 or quality_issue_total_delta >= 1:
        direction = "declining"

    return {
        "has_previous": True,
        "previous_period": _report_period_label(previous_report),
        "direction": direction,
        "health_score_delta": health_score_delta,
        "quality_issue_total_delta": quality_issue_total_delta,
        "approved_count_delta": current.get("approved_count", 0) - previous_health.get("approved_count", 0),
        "low_discrimination_count_delta": current.get("low_discrimination_count", 0) - previous_health.get("low_discrimination_count", 0),
        "quality_metric_deltas": quality_metric_deltas,
    }


async def _question_bank_health(
    db: AsyncSession,
    previous_report: Optional[Report] = None,
) -> dict:
    """Current state of the question bank."""
    stats = await get_question_stats(db)
    status_counts = stats["by_status"]
    total = stats["total"]
    approved = status_counts.get("approved", 0)

    # Questions with low discrimination
    result = await db.execute(
        select(func.count(Question.id))
        .where(and_(
            Question.discrimination != None,
            Question.discrimination < 0.2,
        ))
    )
    low_discrimination = result.scalar() or 0

    # Dimension distribution
    result = await db.execute(
        select(Question.dimension, func.count(Question.id))
        .where(Question.status != QuestionStatus.ARCHIVED)
        .group_by(Question.dimension)
    )
    dimension_dist = {r[0] or "未分类": r[1] for r in result.all()}

    health = {
        "total_questions": total,
        "status_distribution": status_counts,
        "approved_count": approved,
        "low_discrimination_count": low_discrimination,
        "dimension_distribution": dimension_dist,
        "bloom_distribution": stats["by_bloom_level"],
        "quality_metrics": stats["quality_metrics"],
        "health_score": _calculate_health_score(total, approved, low_discrimination),
    }
    health["trend"] = _build_question_bank_trend(health, previous_report)
    return health


async def _material_stats(db: AsyncSession, start: datetime, end: datetime) -> dict:
    """Material library statistics."""
    # Total materials
    result = await db.execute(select(func.count(Material.id)))
    total = result.scalar() or 0

    # New materials in period
    result = await db.execute(
        select(func.count(Material.id))
        .where(and_(Material.created_at >= start, Material.created_at < end))
    )
    new_count = result.scalar() or 0

    # By category
    result = await db.execute(
        select(Material.category, func.count(Material.id))
        .group_by(Material.category)
    )
    category_dist = {r[0] or "未分类": r[1] for r in result.all()}

    return {
        "total_materials": total,
        "new_this_period": new_count,
        "category_distribution": category_dist,
    }


async def _user_stats(db: AsyncSession, start: datetime, end: datetime) -> dict:
    """User activity statistics."""
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0

    result = await db.execute(
        select(func.count(User.id))
        .where(and_(User.created_at >= start, User.created_at < end))
    )
    new_users = result.scalar() or 0

    return {
        "total_users": total_users,
        "new_users": new_users,
    }


def _calculate_health_score(total: int, approved: int, low_disc: int) -> float:
    """Calculate question bank health score (0-100)."""
    if total == 0:
        return 0.0

    approval_ratio = approved / total
    low_disc_ratio = low_disc / total if total > 0 else 0

    # Weight: 60% approval, 40% quality (inverse of low discrimination)
    score = (approval_ratio * 60) + ((1 - low_disc_ratio) * 40)
    return round(min(100, max(0, score)), 1)


def _generate_recommendations(
    test_stats: dict,
    score_stats: dict,
    question_health: dict,
    material_stats: dict,
) -> list[dict]:
    """Generate improvement recommendations based on report data."""
    recs = []

    # Test volume
    if test_stats["total_sessions"] == 0:
        recs.append({
            "category": "测试量",
            "priority": "高",
            "suggestion": "本月无测试活动，建议推动考试组织工作",
        })
    elif test_stats["completion_rate"] < 0.7:
        recs.append({
            "category": "完成率",
            "priority": "中",
            "suggestion": f"测试完成率为{test_stats['completion_rate']*100:.0f}%，建议优化考试流程",
        })

    # Question bank
    if question_health["total_questions"] < 50:
        recs.append({
            "category": "题库规模",
            "priority": "高",
            "suggestion": f"题库仅有{question_health['total_questions']}题，建议补充至100题以上",
        })

    if question_health["low_discrimination_count"] > 0:
        recs.append({
            "category": "题目质量",
            "priority": "中",
            "suggestion": f"有{question_health['low_discrimination_count']}道低区分度题目，建议审核或替换",
        })

    if question_health["health_score"] < 60:
        recs.append({
            "category": "题库健康",
            "priority": "高",
            "suggestion": f"题库健康度{question_health['health_score']}分，建议增加审核通过率",
        })

    quality_metrics = question_health.get("quality_metrics", {})
    trend = question_health.get("trend", {})
    quality_metric_deltas = trend.get("quality_metric_deltas", {})

    if trend.get("has_previous") and trend.get("direction") == "declining":
        previous_period = trend.get("previous_period") or "上期"
        if trend.get("health_score_delta", 0) < 0:
            suggestion = (
                f"相比{previous_period}，题库健康度下降了"
                f"{abs(trend['health_score_delta']):.1f}分，建议复盘近月新增题目质量"
            )
        else:
            suggestion = (
                f"相比{previous_period}，题库元数据质量问题增加了"
                f"{trend.get('quality_issue_total_delta', 0)}项，建议优先补齐标注与解析"
            )
        recs.append({
            "category": "题库趋势",
            "priority": "中",
            "suggestion": suggestion,
        })

    if quality_metrics.get("missing_bloom_level_count", 0) > 0:
        recs.append({
            "category": "题目标注",
            "priority": "中",
            "suggestion": f"有{quality_metrics['missing_bloom_level_count']}道题缺少 Bloom 标注，建议补齐认知层次",
        })
    if quality_metric_deltas.get("missing_bloom_level_count", 0) > 0:
        previous_period = trend.get("previous_period") or "上期"
        recs.append({
            "category": "题目标注趋势",
            "priority": "中",
            "suggestion": (
                f"相比{previous_period}，缺少 Bloom 标注的题目增加了"
                f"{quality_metric_deltas['missing_bloom_level_count']}道，建议回查最近入库题目"
            ),
        })
    if quality_metrics.get("missing_explanation_count", 0) > 0:
        recs.append({
            "category": "题目解析",
            "priority": "中",
            "suggestion": f"有{quality_metrics['missing_explanation_count']}道题缺少解析，建议补充解析以提升可复核性",
        })
    if quality_metric_deltas.get("missing_explanation_count", 0) > 0:
        previous_period = trend.get("previous_period") or "上期"
        recs.append({
            "category": "题目解析趋势",
            "priority": "中",
            "suggestion": (
                f"相比{previous_period}，缺少解析的题目增加了"
                f"{quality_metric_deltas['missing_explanation_count']}道，建议检查生成后保存流程"
            ),
        })

    # Materials
    if material_stats["total_materials"] < 10:
        recs.append({
            "category": "素材库",
            "priority": "中",
            "suggestion": "素材数量不足，建议补充各维度学习材料",
        })

    # Scoring
    if score_stats["total_scores"] > 0 and score_stats["avg_score_ratio"] < 0.4:
        recs.append({
            "category": "成绩水平",
            "priority": "中",
            "suggestion": "平均得分率偏低，建议检查题目难度或加强培训",
        })

    if not recs:
        recs.append({
            "category": "总体",
            "priority": "低",
            "suggestion": "平台运行良好，建议继续保持",
        })

    return recs
