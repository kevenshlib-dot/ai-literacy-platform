"""Unit tests for material-based knowledge-unit allocation."""
import uuid

import pytest

from app.models.material import KnowledgeUnit
from app.services import question_service


def _make_unit(
    material_id: uuid.UUID,
    *,
    title: str,
    summary: str,
    keywords: list[str],
    content: str,
    chunk_index: int,
) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uuid.uuid4(),
        material_id=material_id,
        title=title,
        summary=summary,
        keywords={"topics": keywords},
        content=content,
        chunk_index=chunk_index,
    )


def test_plan_unit_type_distribution_uses_one_question_per_unit():
    material_id = uuid.uuid4()
    units = [
        _make_unit(
            material_id,
            title=f"知识点{i}",
            summary=f"摘要{i}",
            keywords=[f"关键词{i}", f"主题{i}"],
            content=f"这是第{i}个知识点的完整说明，用于测试唯一知识点分配逻辑。" * 2,
            chunk_index=i,
        )
        for i in range(5)
    ]

    requested = {
        "single_choice": 2,
        "multiple_choice": 1,
        "true_false": 1,
        "short_answer": 1,
    }
    plan = question_service._plan_unit_type_distribution(units, requested)

    used_units = [
        unit.id
        for unit in units
        if sum(plan[unit.id].values()) > 0
    ]
    total_assignments = {
        unit.id: sum(plan[unit.id].values())
        for unit in units
    }

    assert len(used_units) == 5
    assert max(total_assignments.values()) == 1


def test_plan_unit_type_distribution_prefers_high_value_units_first():
    material_id = uuid.uuid4()
    strong_unit = _make_unit(
        material_id,
        title="核心概念",
        summary="解释隐私最小化与授权范围控制。",
        keywords=["隐私最小化", "授权范围", "数据治理"],
        content="隐私最小化要求只保留完成任务所必需的数据字段。授权范围控制要求数据用途与用户同意保持一致。上线前还应检查审计和脱敏流程。",
        chunk_index=0,
    )
    medium_unit = _make_unit(
        material_id,
        title="案例分析",
        summary="分析推荐系统上线前的合规审查步骤。",
        keywords=["合规审查", "推荐系统"],
        content="推荐系统上线前，需要完成数据来源核查、字段脱敏、用途评估和访问审计配置，才能降低个人信息误用风险。",
        chunk_index=1,
    )
    weak_unit = KnowledgeUnit(
        id=uuid.uuid4(),
        material_id=material_id,
        title="导语",
        content="补充说明。",
        chunk_index=2,
    )

    plan = question_service._plan_unit_type_distribution(
        [strong_unit, medium_unit, weak_unit],
        {"single_choice": 2},
    )

    used_units = {
        unit_id
        for unit_id, allocation in plan.items()
        if sum(allocation.values()) > 0
    }

    assert used_units == {strong_unit.id, medium_unit.id}
    assert weak_unit.id not in used_units


def test_plan_unit_type_distribution_preserves_requested_counts_when_capacity_is_sufficient():
    material_id = uuid.uuid4()
    units = [
        _make_unit(
            material_id,
            title=f"知识点{i}",
            summary=f"摘要{i}",
            keywords=[f"关键词{i}", f"主题{i}"],
            content=f"知识点{i}说明多模态大模型的不同技术主题和应用约束。" * 2,
            chunk_index=i,
        )
        for i in range(5)
    ]

    requested = {
        "single_choice": 2,
        "multiple_choice": 1,
        "true_false": 1,
        "short_answer": 1,
    }
    plan = question_service._plan_unit_type_distribution(units, requested)

    actual = {
        question_type: sum(plan[unit.id].get(question_type, 0) for unit in units)
        for question_type in requested
    }

    assert actual == requested


def test_material_unique_generation_capacity_raises_when_units_are_insufficient():
    material_id = uuid.uuid4()
    units = [
        _make_unit(
            material_id,
            title="知识点A",
            summary="摘要A",
            keywords=["A"],
            content="知识点A内容。",
            chunk_index=0,
        ),
        _make_unit(
            material_id,
            title="知识点B",
            summary="摘要B",
            keywords=["B"],
            content="知识点B内容。",
            chunk_index=1,
        ),
    ]

    with pytest.raises(ValueError, match="当前素材去重后仅有 2 个可用知识点，不足以生成 3 道互不重复知识点的题目"):
        question_service._ensure_material_unique_generation_capacity(units, 3)
