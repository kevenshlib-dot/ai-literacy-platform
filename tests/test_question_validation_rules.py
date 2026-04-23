"""Unit tests for material-generation validation rules."""

from app.agents.question_agent import (
    _contains_material_reference,
    _contains_prompt_instruction_leakage,
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


def test_contains_prompt_instruction_leakage_detects_planning_markers():
    assert _contains_prompt_instruction_leakage("【题目槽位 1 参考素材】") is True
    assert _contains_prompt_instruction_leakage("请参考证据锚点设计题目") is True
    assert _contains_prompt_instruction_leakage("多个节点环境中部署实例") is False


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


def test_validate_and_fix_question_rejects_material_reference_content():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "single_choice",
            "dimension": "AI基础知识",
            "stem": "根据本文内容，以下哪项做法更合理？",
            "options": {"A": "方案A", "B": "方案B", "C": "方案C", "D": "方案D"},
            "correct_answer": "A",
            "explanation": "解释说明。",
            "knowledge_tags": ["测试"],
        },
        ["single_choice"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["题目包含素材元信息或禁用表述"]


def test_validate_and_fix_question_rejects_prompt_instruction_leakage():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "single_choice",
            "dimension": "AI基础知识",
            "stem": "【题目槽位 2 参考素材】以下哪项更符合要求？",
            "options": {"A": "方案A", "B": "方案B", "C": "方案C", "D": "方案D"},
            "correct_answer": "A",
            "explanation": "请参考证据锚点作答。",
            "knowledge_tags": ["测试"],
        },
        ["single_choice"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["题目泄漏了规划或提示词标记"]


def test_validate_and_fix_question_rejects_choice_options_with_mixed_granularity():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "single_choice",
            "dimension": "AI基础知识",
            "stem": "以下哪项更符合要求？",
            "options": {
                "A": "建立最小必要采集机制",
                "B": "随意扩大字段采集范围并长期保留原始数据以便未来所有潜在分析任务都能继续使用",
                "C": "执行访问审计",
                "D": "明确用途边界",
            },
            "correct_answer": "A",
            "explanation": "解释说明。",
            "knowledge_tags": ["测试"],
        },
        ["single_choice"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["选择题选项粒度不一致"]


def test_validate_and_fix_question_rejects_absolute_claim_without_anchor_support():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "single_choice",
            "dimension": "AI伦理安全",
            "stem": "在人工智能伦理研究中，被公认的首要议题是什么？",
            "options": {
                "A": "机器人权利",
                "B": "界面配色",
                "C": "商业融资",
                "D": "办公效率",
            },
            "correct_answer": "A",
            "explanation": "解释中没有给出明确证据。",
            "knowledge_tags": ["人工智能伦理"],
            "_plan_meta": {
                "fact_anchor": "学科定位与部门伦理学",
                "evidence_span": "将科技伦理视为部门伦理学有助于突出科技工作者的伦理责任。",
                "knowledge_point": "学科定位",
            },
        },
        ["single_choice"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["题目包含绝对化表述但缺少明确素材锚点"]


def test_validate_and_fix_question_rejects_short_answer_with_blank_marker():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "short_answer",
            "dimension": "AI伦理安全",
            "stem": "请说明将科技伦理冠名为______更合理的原因。",
            "options": None,
            "correct_answer": "部门伦理学",
            "explanation": "这一表述更强调其具体学科归属。",
            "knowledge_tags": ["部门伦理学"],
        },
        ["short_answer"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["简答题题干不得包含填空标记"]


def test_validate_and_fix_question_rejects_incomplete_stem_fragment():
    rejection_reasons = []
    fixed = _validate_and_fix_question(
        {
            "question_type": "single_choice",
            "dimension": "AI伦理安全",
            "stem": "某科技媒体在报道",
            "options": {
                "A": "方案A",
                "B": "方案B",
                "C": "方案C",
                "D": "方案D",
            },
            "correct_answer": "A",
            "explanation": "解释说明。",
            "knowledge_tags": ["测试"],
        },
        ["single_choice"],
        rejection_reasons,
    )

    assert fixed is None
    assert rejection_reasons == ["题干必须是完整句，不得只保留场景片段"]
