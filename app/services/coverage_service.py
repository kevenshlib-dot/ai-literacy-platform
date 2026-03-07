"""Coverage analysis service - analyze material and question coverage across dimensions."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionStatus
from app.models.material import Material, KnowledgeUnit


FIVE_DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]

DIMENSION_SUB_TOPICS = {
    "AI基础知识": ["机器学习", "深度学习", "神经网络", "算法", "数据处理", "模型训练"],
    "AI技术应用": ["自然语言处理", "计算机视觉", "语音识别", "推荐系统", "自动驾驶", "智能助手"],
    "AI伦理安全": ["数据隐私", "算法偏见", "公平性", "透明度", "安全性", "法规合规"],
    "AI批判思维": ["AI局限性", "风险评估", "信息验证", "决策分析", "批判性评价", "媒体素养"],
    "AI创新实践": ["提示工程", "AI工具使用", "解决方案设计", "创新应用", "跨领域融合", "AI创作"],
}

# Materials older than this are considered potentially outdated
FRESHNESS_DAYS = 365


async def get_coverage_analysis(db: AsyncSession) -> dict:
    """Generate comprehensive coverage analysis across five dimensions."""
    material_coverage = await _material_coverage(db)
    question_coverage = await _question_coverage(db)
    heatmap = _build_heatmap(material_coverage, question_coverage)
    gaps = _identify_gaps(heatmap)
    stale_materials = await _find_stale_materials(db)

    return {
        "dimensions": FIVE_DIMENSIONS,
        "material_coverage": material_coverage,
        "question_coverage": question_coverage,
        "heatmap": heatmap,
        "gaps": gaps,
        "stale_materials": stale_materials,
        "summary": {
            "total_dimensions": len(FIVE_DIMENSIONS),
            "covered_dimensions": sum(1 for d in heatmap if heatmap[d]["coverage_score"] > 0),
            "gap_count": len(gaps),
            "stale_count": len(stale_materials),
            "overall_coverage": round(
                sum(h["coverage_score"] for h in heatmap.values()) / len(FIVE_DIMENSIONS), 2
            ),
        },
    }


async def get_dimension_detail(db: AsyncSession, dimension: str) -> dict:
    """Get detailed coverage for a specific dimension."""
    if dimension not in FIVE_DIMENSIONS:
        return {"error": f"未知维度: {dimension}", "valid_dimensions": FIVE_DIMENSIONS}

    # Materials in this dimension
    mat_result = await db.execute(
        select(Material)
        .where(Material.category == dimension)
        .order_by(Material.created_at.desc())
    )
    materials = list(mat_result.scalars().all())

    # Knowledge units
    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.dimension == dimension)
    )
    units = list(ku_result.scalars().all())

    # Questions
    q_result = await db.execute(
        select(Question)
        .where(Question.dimension == dimension)
        .where(Question.status != QuestionStatus.ARCHIVED)
    )
    questions = list(q_result.scalars().all())

    # Difficulty distribution
    diff_dist = {}
    for q in questions:
        d = q.difficulty or 3
        diff_dist[d] = diff_dist.get(d, 0) + 1

    # Sub-topic coverage
    sub_topics = DIMENSION_SUB_TOPICS.get(dimension, [])
    sub_coverage = {}
    for sub in sub_topics:
        mat_count = sum(1 for m in materials if sub in (m.title or "") or sub in (m.description or ""))
        q_count = sum(1 for q in questions if sub in q.stem)
        ku_count = sum(1 for u in units if sub in (u.content or ""))
        sub_coverage[sub] = {
            "materials": mat_count,
            "questions": q_count,
            "knowledge_units": ku_count,
            "total": mat_count + q_count + ku_count,
        }

    return {
        "dimension": dimension,
        "material_count": len(materials),
        "question_count": len(questions),
        "knowledge_unit_count": len(units),
        "difficulty_distribution": diff_dist,
        "sub_topic_coverage": sub_coverage,
        "uncovered_sub_topics": [s for s in sub_topics if sub_coverage[s]["total"] == 0],
    }


async def _material_coverage(db: AsyncSession) -> dict:
    """Count materials per dimension."""
    # By category
    result = await db.execute(
        select(Material.category, func.count(Material.id))
        .group_by(Material.category)
    )
    by_category = {r[0]: r[1] for r in result.all() if r[0]}

    # By knowledge unit dimension
    result2 = await db.execute(
        select(KnowledgeUnit.dimension, func.count(KnowledgeUnit.id))
        .group_by(KnowledgeUnit.dimension)
    )
    by_ku = {r[0]: r[1] for r in result2.all() if r[0]}

    coverage = {}
    for dim in FIVE_DIMENSIONS:
        coverage[dim] = {
            "materials": by_category.get(dim, 0),
            "knowledge_units": by_ku.get(dim, 0),
        }
    return coverage


async def _question_coverage(db: AsyncSession) -> dict:
    """Count approved questions per dimension and difficulty."""
    result = await db.execute(
        select(
            Question.dimension,
            Question.difficulty,
            func.count(Question.id),
        )
        .where(Question.status != QuestionStatus.ARCHIVED)
        .group_by(Question.dimension, Question.difficulty)
    )

    coverage = {}
    for dim in FIVE_DIMENSIONS:
        coverage[dim] = {"total": 0, "by_difficulty": {}}

    for dim, diff, cnt in result.all():
        if dim in coverage:
            coverage[dim]["total"] += cnt
            coverage[dim]["by_difficulty"][diff] = cnt

    return coverage


def _build_heatmap(material_coverage: dict, question_coverage: dict) -> dict:
    """Build heatmap data for visualization."""
    heatmap = {}
    for dim in FIVE_DIMENSIONS:
        mat = material_coverage.get(dim, {})
        q = question_coverage.get(dim, {})

        mat_count = mat.get("materials", 0) + mat.get("knowledge_units", 0)
        q_count = q.get("total", 0)

        # Coverage score: 0-100 based on material and question counts
        # Target: >= 10 materials AND >= 20 questions for full coverage
        mat_score = min(100, mat_count * 10)  # 10 materials = 100%
        q_score = min(100, q_count * 5)  # 20 questions = 100%
        coverage_score = round((mat_score * 0.4 + q_score * 0.6), 1)

        heatmap[dim] = {
            "material_count": mat_count,
            "question_count": q_count,
            "coverage_score": coverage_score,
            "level": _coverage_level(coverage_score),
        }

    return heatmap


def _coverage_level(score: float) -> str:
    """Classify coverage level."""
    if score >= 80:
        return "充足"
    elif score >= 50:
        return "适中"
    elif score >= 20:
        return "不足"
    else:
        return "缺失"


def _identify_gaps(heatmap: dict) -> list[dict]:
    """Identify coverage gaps requiring attention."""
    gaps = []
    for dim, data in heatmap.items():
        if data["coverage_score"] < 50:
            priority = "高" if data["coverage_score"] < 20 else "中"
            gaps.append({
                "dimension": dim,
                "coverage_score": data["coverage_score"],
                "level": data["level"],
                "priority": priority,
                "suggestion": f"建议补充{dim}相关素材和题目",
                "needed_materials": max(0, 10 - data["material_count"]),
                "needed_questions": max(0, 20 - data["question_count"]),
            })

    gaps.sort(key=lambda x: x["coverage_score"])
    return gaps


async def _find_stale_materials(db: AsyncSession) -> list[dict]:
    """Find materials that may be outdated."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    result = await db.execute(
        select(Material)
        .where(Material.created_at < cutoff)
        .order_by(Material.created_at.asc())
        .limit(50)
    )
    materials = list(result.scalars().all())

    return [
        {
            "id": str(m.id),
            "title": m.title,
            "category": m.category,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "days_old": (datetime.now(timezone.utc) - m.created_at).days if m.created_at else None,
        }
        for m in materials
    ]
