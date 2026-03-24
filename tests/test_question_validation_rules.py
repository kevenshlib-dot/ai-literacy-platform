"""Unit tests for material-generation validation rules."""

from app.agents.question_agent import (
    _contains_material_reference,
    _validate_and_fix_question,
)


def test_contains_material_reference_allows_normal_technical_terms():
    assert _contains_material_reference("多个节点环境中部署实例") is False
    assert _contains_material_reference("关键环节的数据流转机制") is False
    assert _contains_material_reference("参数调节策略需要结合反馈信号") is False


def test_contains_material_reference_still_blocks_real_material_metadata():
    assert _contains_material_reference("根据本文内容回答问题") is True
    assert _contains_material_reference("第3章介绍了系统部署") is True
    assert _contains_material_reference("作者：张三") is True
    assert _contains_material_reference("出版社：测试出版社") is True


def test_validate_and_fix_question_rejects_non_statement_true_false():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "true_false",
            "dimension": "AI伦理安全",
            "stem": "以下哪项说法是正确的？",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "A",
            "explanation": "仍需合规审查。",
            "knowledge_tags": ["合规审查"],
        },
        ["true_false"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["判断题题干必须是陈述句且不得包含问号或疑问表达"]


def test_validate_and_fix_question_rejects_fill_blank_without_blank_marker():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "fill_blank",
            "dimension": "AI基础知识",
            "stem": "人工智能的英文缩写是什么",
            "options": None,
            "correct_answer": "AI",
            "explanation": "AI 是 Artificial Intelligence 的缩写。",
            "knowledge_tags": ["人工智能"],
        },
        ["fill_blank"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["填空题题干必须包含明确空位标记"]
