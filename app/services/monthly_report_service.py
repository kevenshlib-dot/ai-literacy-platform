"""Monthly report service - auto-generate platform operations reports."""
import uuid
from datetime import datetime, timezone, timedelta
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
    question_health = await _question_bank_health(db)
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


async def _question_bank_health(db: AsyncSession) -> dict:
    """Current state of the question bank."""
    # Total questions by status
    result = await db.execute(
        select(Question.status, func.count(Question.id))
        .group_by(Question.status)
    )
    status_counts = {r[0].value if hasattr(r[0], 'value') else r[0]: r[1] for r in result.all()}

    total = sum(status_counts.values())
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

    return {
        "total_questions": total,
        "status_distribution": status_counts,
        "approved_count": approved,
        "low_discrimination_count": low_discrimination,
        "dimension_distribution": dimension_dist,
        "health_score": _calculate_health_score(total, approved, low_discrimination),
    }


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
