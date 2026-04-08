"""Question generation agent - uses LLM to generate questions from knowledge units."""
import json
import logging
import random
import re
from typing import Optional

from openai import OpenAI
from httpx import Timeout

from app.core.config import settings
from app.core.llm_config import get_llm_config_sync, make_openai_client

logger = logging.getLogger(__name__)

# ── 题型常量 ────────────────────────────────────────────────────────
TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "fill_blank": "填空题",
    "short_answer": "简答题",
}

LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}

# 需要 options 的题型
OPTION_TYPES = {"single_choice", "multiple_choice", "true_false"}

# 合法的 question_type 集合
VALID_TYPES = set(TYPE_LABELS.keys()) | {"essay", "sjt"}

BLOOM_LABELS = {
    "remember": "记忆",
    "understand": "理解",
    "apply": "应用",
    "analyze": "分析",
    "evaluate": "评价",
    "create": "创造",
}

# ── 五维度常量与关键词映射（用于自动分类） ─────────────────────────────
FIVE_DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]

DIMENSION_KEYWORDS = {
    "AI基础知识": [
        "机器学习", "深度学习", "神经网络", "算法", "数据处理", "模型训练",
        "监督学习", "无监督学习", "强化学习", "回归", "分类", "聚类",
        "特征工程", "过拟合", "欠拟合", "损失函数", "梯度下降", "反向传播",
        "卷积", "循环神经", "Transformer", "注意力机制", "embedding",
        "训练集", "测试集", "验证集", "参数", "超参数", "激活函数",
        "基础", "概念", "原理", "定义", "发展历史", "图灵",
    ],
    "AI技术应用": [
        "自然语言处理", "NLP", "计算机视觉", "语音识别", "推荐系统",
        "自动驾驶", "智能助手", "图像识别", "目标检测", "文本分类",
        "情感分析", "机器翻译", "对话系统", "搜索引擎", "OCR",
        "人脸识别", "语义理解", "知识图谱", "ChatGPT", "GPT",
        "大语言模型", "LLM", "生成式AI", "AIGC", "应用", "场景",
    ],
    "AI伦理安全": [
        "伦理", "安全", "隐私", "偏见", "公平", "透明",
        "数据保护", "算法歧视", "责任", "法规", "合规", "GDPR",
        "深度伪造", "deepfake", "虚假信息", "版权", "知识产权",
        "数据泄露", "对抗攻击", "鲁棒性", "可解释性", "信任",
        "道德", "社会影响", "就业", "监管",
    ],
    "AI批判思维": [
        "批判", "局限", "风险", "评估", "验证", "分析",
        "信息素养", "媒体素养", "虚假信息", "误导", "判断",
        "质疑", "反思", "独立思考", "证据", "论证",
        "可靠性", "有效性", "逻辑", "谬误", "偏差",
    ],
    "AI创新实践": [
        "提示工程", "prompt", "AI工具", "实践", "创新",
        "解决方案", "设计", "跨领域", "AI创作", "编程",
        "代码", "项目", "动手", "实验", "开发",
        "微调", "fine-tune", "API", "部署", "应用开发",
        "工作流", "自动化", "效率", "协作",
    ],
}

# ── 题目风格多样性目录 ────────────────────────────────────────────────
QUESTION_STEM_STYLES = [
    {
        "name": "直接知识型",
        "description": "直接考查概念定义、原理或事实",
        "example_pattern": "以下关于XX的描述，哪项是正确的？",
    },
    {
        "name": "情景应用型",
        "description": "设置一个具体的工作/学习/生活情景，考查知识在情境中的运用",
        "example_pattern": "小明是一名市场分析师，他想用AI工具分析客户评论的情感倾向。以下哪种方法最合适？",
    },
    {
        "name": "案例分析型",
        "description": "给出一个真实或虚构的案例（公司、项目、事件），要求分析其中涉及的AI概念",
        "example_pattern": "某医院引入AI辅助诊断系统后，误诊率下降了30%，但部分医生担心过度依赖。以下分析最准确的是？",
    },
    {
        "name": "对比辨析型",
        "description": "比较两个或多个相近概念/技术/方法的异同",
        "example_pattern": "监督学习与无监督学习的核心区别在于？",
    },
    {
        "name": "问题解决型",
        "description": "描述一个需要解决的问题，要求选择最佳策略或方案",
        "example_pattern": "你的团队需要从10万条客户反馈中快速识别负面评论，以下哪个方案最高效？",
    },
    {
        "name": "因果推理型",
        "description": "考查对因果关系的理解，为什么某技术能实现某效果",
        "example_pattern": "深度学习在图像识别任务上优于传统方法，主要原因是？",
    },
    {
        "name": "伦理困境型",
        "description": "设置一个涉及AI伦理的两难情境，考查价值判断和决策能力",
        "example_pattern": "一家招聘公司的AI筛选系统被发现对女性求职者的通过率显著低于男性。作为技术负责人，你的首要措施应该是？",
    },
    {
        "name": "评价判断型",
        "description": "给出一个观点或做法，要求判断其合理性并说明理由",
        "example_pattern": "'AI生成的文本不需要人工审核就可以直接发布。'对这一观点的评价，最合理的是？",
    },
    {
        "name": "趋势预测型",
        "description": "基于当前技术发展，推断未来趋势或影响",
        "example_pattern": "随着大语言模型能力的提升，以下哪个职业最可能需要转型？",
    },
    {
        "name": "实践操作型",
        "description": "考查实际使用AI工具的步骤、方法或最佳实践",
        "example_pattern": "使用ChatGPT编写一份数据分析报告时，以下哪种提示词(Prompt)设计最有效？",
    },
]

# 情境上下文池 - 用于注入题目场景多样性
SCENARIO_CONTEXTS = [
    "职场工作场景（如项目管理、数据分析、内容创作、客户服务）",
    "教育学习场景（如课堂教学、学生作业、教研活动、在线课程）",
    "日常生活场景（如智能家居、健康管理、出行规划、消费购物）",
    "科研探索场景（如文献检索、实验设计、数据处理、论文写作）",
    "产业应用场景（如智能制造、金融风控、医疗诊断、农业监测）",
    "社会治理场景（如公共安全、城市管理、政务服务、舆情监测）",
    "创意创作场景（如艺术设计、音乐创作、影视制作、游戏开发）",
    "创业创新场景（如产品设计、市场调研、商业决策、技术选型）",
]

# 难度校准详细描述
DIFFICULTY_CALIBRATION = {
    1: {
        "label": "入门",
        "description": "面向零基础学习者。考查最基本的AI概念识别和术语理解。",
        "stem_length": "题干简短（1-2句话）",
        "distractor_strategy": "干扰项与正确答案差异较大，容易排除",
    },
    2: {
        "label": "简单",
        "description": "面向初学者。考查基本概念的理解和简单区分。",
        "stem_length": "题干1-3句话，可包含简单情境",
        "distractor_strategy": "干扰项与正确答案有一定相似性，但存在明显的概念错误",
    },
    3: {
        "label": "中等",
        "description": "面向有一定基础的学习者。考查概念的深入理解和简单应用。",
        "stem_length": "题干2-4句话，包含情境描述",
        "distractor_strategy": "干扰项基于常见误解设计，需要较好的理解才能区分",
    },
    4: {
        "label": "困难",
        "description": "面向进阶学习者。考查知识的综合应用、分析和评价能力。",
        "stem_length": "题干3-5句话，包含复杂的案例或多条件情境",
        "distractor_strategy": "干扰项部分正确或在特定条件下成立，需要全面分析",
    },
    5: {
        "label": "专家",
        "description": "面向专业人士。考查创新思维、综合评价和复杂决策能力。",
        "stem_length": "题干可较长，涉及多层次的问题描述",
        "distractor_strategy": "每个干扰项在某种角度下都有道理，只有最佳答案最全面或最准确",
    },
}


def classify_dimension(stem: str, knowledge_tags: list = None) -> str:
    """根据题干和知识标签自动分类AI素养维度。

    使用关键词匹配算法，对每个维度计算匹配得分，返回最佳匹配。
    如果所有维度得分都为0，返回默认维度"AI基础知识"。
    """
    text = stem or ""
    if knowledge_tags and isinstance(knowledge_tags, list):
        text += " " + " ".join(str(t) for t in knowledge_tags)
    text = text.lower()

    best_dim = "AI基础知识"
    best_score = 0

    for dim, keywords in DIMENSION_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in text:
                score += 1
        if score > best_score:
            best_score = score
            best_dim = dim

    return best_dim

# ── System Prompt（含每种题型的严格示例） ────────────────────────────
SYSTEM_PROMPT = """\
# 角色定义

你是一位资深的AI素养评测出题专家，拥有10年以上教育测评经验，专长于：
- 布鲁姆认知目标分类法（Bloom's Taxonomy）的精准应用
- 基于情境的评测设计（Scenario-Based Assessment）
- 干扰项心理学（Distractor Psychology）：利用常见误解和认知偏差设计高质量干扰项
- AI/人工智能领域的全面知识覆盖

你的任务是生成高质量、多样化的AI素养评测题目。

# 出题质量标准

## 题干设计标准
1. **情境丰富性**：优先使用具体情境（工作场景、学习场景、生活场景）包裹知识点，避免纯粹的"以下哪项正确"式提问
2. **认知层次精准**：题目应精准对应布鲁姆认知层次——记忆/理解层次问"是什么"，应用层次问"怎么做"，分析层次问"为什么"，评价层次问"哪个更好"，创造层次问"如何设计"
3. **表述清晰完整**：题干必须自足，不依赖外部信息即可作答；避免否定句式（"以下哪项不正确"）除非明确标注

## 干扰项设计标准（核心）
1. **基于真实误解**：每个干扰项应对应一种常见的认知错误或误解，而非随意编造的错误选项
2. **似是而非**：干扰项应在表面上看起来合理，但在关键概念上存在偏差
3. **长度均衡**：所有选项（包括正确答案）的长度应大致相同，不能让正确答案因为更详细而被猜出
4. **独立性**：选项之间不能互相矛盾导致排除法过于容易，也不能有包含关系
5. **正确答案位置随机**：正确答案不能总是A或总是最长的选项，应在A/B/C/D之间均匀分布

## 反模式（必须避免）
- 所有题目正确答案都是同一个字母
- 题干过于笼统："关于XX，以下说法正确的是？"（没有情境）
- 干扰项一眼假：如"AI已经完全取代了人类"这种明显错误
- 题目之间高度重复：考查同一个知识点的不同措辞
- 判断题全部为"正确"
- 选项中出现"以上都是/以上都不是"

# 题目风格目录

生成题目时，请在以下风格中灵活选择和混合使用：
- **直接知识型**：考查概念定义、事实（适合记忆/理解层次）
- **情景应用型**：设置工作/学习/生活场景，考查应用能力
- **案例分析型**：给出案例，分析其中的AI概念或决策
- **对比辨析型**：比较相近概念/技术的异同
- **问题解决型**：描述问题，选择最佳方案
- **因果推理型**：理解技术原理或效果的因果关系
- **伦理困境型**：AI伦理相关的两难情境
- **评价判断型**：对某个观点/做法进行评判
- **实践操作型**：考查AI工具使用的具体方法和步骤

# 严格输出规范

你必须输出一个纯JSON数组，不要包含任何其他文字。每个元素的格式如下：

### 单选题 (single_choice)
{"question_type": "single_choice", "dimension": "AI基础知识", "stem": "以下哪项是机器学习的核心特征？", "options": {"A": "需要显式编程规则", "B": "从数据中自动学习模式", "C": "不需要计算资源", "D": "只能处理文本数据"}, "correct_answer": "B", "explanation": "机器学习的核心特征是从数据中自动学习模式和规律，而非依赖人工编写的显式规则。", "knowledge_tags": ["机器学习", "基础概念"]}

### 多选题 (multiple_choice)
{"question_type": "multiple_choice", "dimension": "AI技术应用", "stem": "以下哪些属于深度学习的常见应用？", "options": {"A": "图像识别", "B": "自然语言处理", "C": "手动数据录入", "D": "语音识别"}, "correct_answer": "ABD", "explanation": "深度学习广泛应用于图像识别、NLP和语音识别，手动数据录入不属于深度学习应用。", "knowledge_tags": ["深度学习", "应用场景"]}

### 判断题 (true_false)
{"question_type": "true_false", "dimension": "AI基础知识", "stem": "监督学习需要使用带标签的训练数据。", "options": {"A": "正确", "B": "错误"}, "correct_answer": "A", "explanation": "监督学习的核心就是利用带有标签的数据来训练模型。", "knowledge_tags": ["监督学习"]}

### 填空题 (fill_blank)
{"question_type": "fill_blank", "dimension": "AI基础知识", "stem": "神经网络中，用于引入非线性变换的函数称为____函数。", "options": null, "correct_answer": "激活", "explanation": "激活函数（如ReLU、Sigmoid等）为神经网络引入非线性。", "knowledge_tags": ["神经网络", "激活函数"]}

### 简答题 (short_answer)
{"question_type": "short_answer", "dimension": "AI基础知识", "stem": "请简述过拟合的含义及至少两种常用的缓解方法。", "options": null, "correct_answer": "过拟合是指模型在训练集上表现良好但在新数据上泛化能力差。常用缓解方法包括：1）正则化；2）Dropout；3）增加训练数据；4）早停法。", "explanation": "过拟合是模型容量过大或训练数据不足导致的。", "knowledge_tags": ["过拟合", "模型优化"]}

# 关键规则（违反将导致输出无效）

1. **options 字段的键必须是大写字母 A/B/C/D**，不得使用中文键或数字键
2. **单选题 correct_answer** 只能是单个大写字母：A、B、C 或 D
3. **多选题 correct_answer** 是多个大写字母的拼接（按字母排序）：AB、AC、ABC、ABD、ACD、ABCD 等
4. **判断题 correct_answer** 只能是 A（正确）或 B（错误）
5. **填空题和简答题** 的 options 必须为 null
6. **explanation 必须提供**，不能为空，且应解释为什么正确答案对、其他选项错
7. **stem 必须完整**，语句通顺，不能截断
8. **干扰项**必须具有合理性和迷惑性，不能一眼看出错误
9. 每道题的 knowledge_tags 必须是字符串数组
10. **dimension 必须是以下五个值之一**：AI基础知识、AI技术应用、AI伦理安全、AI批判思维、AI创新实践
11. 直接输出 JSON 数组，不要加 ```json 标记，不要加任何其他文字
12. **正确答案位置分散**：多道题时，正确答案应分布在不同选项位置（A/B/C/D），不能全部相同
"""


def _build_user_prompt(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> str:
    """Build user prompt for question generation with diversity and quality instructions."""
    # ── 题型说明 ──
    type_parts = []
    for t in question_types:
        label = TYPE_LABELS.get(t, t)
        type_parts.append(f"{label}({t})")
    type_str = "、".join(type_parts)

    # ── 难度校准详细描述 ──
    diff_info = DIFFICULTY_CALIBRATION.get(difficulty, DIFFICULTY_CALIBRATION[3])
    difficulty_section = f"""- 难度：{difficulty}/5（{diff_info['label']}）
  - 目标受众：{diff_info['description']}
  - 题干要求：{diff_info['stem_length']}
  - 干扰项策略：{diff_info['distractor_strategy']}"""

    # ── 布鲁姆认知层次 ──
    bloom_section = ""
    if bloom_level and bloom_level in BLOOM_LABELS:
        bloom_instructions = {
            "remember": "聚焦于事实回忆、术语识别、定义复述。使用'是什么''哪个是''列举'等提问方式。",
            "understand": "聚焦于概念解释、原因理解、意义阐述。使用'为什么''解释''区别'等提问方式。",
            "apply": "聚焦于在新情境中使用知识解决问题。必须设置具体情境，使用'如何使用''在...情况下''应该采取'等方式。",
            "analyze": "聚焦于分解问题、辨别因果、比较异同。使用案例分析、对比辨析题型。涉及多因素分析。",
            "evaluate": "聚焦于判断、评价、论证。给出观点或方案让考生判断优劣。涉及标准制定和价值判断。",
            "create": "聚焦于设计方案、提出新解法、综合创新。使用开放性较强的题目，鼓励创造性思考。",
        }
        bloom_detail = bloom_instructions.get(bloom_level, "")
        bloom_section = f"\n- 认知层次：{BLOOM_LABELS[bloom_level]}（{bloom_level}）\n  - 出题指导：{bloom_detail}"

    # ── 随机选择题目风格要求（多样性机制） ──
    num_styles = min(count, 4)
    selected_styles = random.sample(QUESTION_STEM_STYLES, min(num_styles, len(QUESTION_STEM_STYLES)))
    style_instructions = []
    for i, style in enumerate(selected_styles, 1):
        style_instructions.append(
            f"  {i}. {style['name']}：{style['description']}（参考：{style['example_pattern']}）"
        )
    style_section = "\n".join(style_instructions)

    # ── 随机选择情境上下文 ──
    num_contexts = min(3, count)
    selected_contexts = random.sample(SCENARIO_CONTEXTS, min(num_contexts, len(SCENARIO_CONTEXTS)))
    context_section = "、".join(selected_contexts)

    # ── 额外要求 ──
    custom_section = ""
    if custom_prompt:
        custom_section = f"\n\n【额外要求】\n{custom_prompt}"

    # ── 内容区 ──
    if content:
        content_section = f"""

【知识内容】（请基于以下内容深度出题，确保题目考查内容中的核心概念和关键知识点）
{content}

【内容分析指引】
- 识别上述内容中的核心概念、关键定义、重要原理
- 围绕这些核心知识点设计题目，不要仅考查表面文字
- 干扰项应基于对这些概念的常见误解来设计
- 确保每道题至少与内容中的一个核心知识点直接相关"""
    else:
        content_section = """

【出题范围】
请基于AI素养领域的专业知识出题，涵盖以下维度（均匀分布）：
- AI基础知识（机器学习原理、深度学习、算法基础、数据处理）
- AI技术应用（NLP、计算机视觉、推荐系统、大语言模型、AIGC）
- AI伦理安全（隐私保护、算法偏见、数据安全、负责任AI）
- AI批判思维（信息辨别、AI局限性认知、证据评估、逻辑推理）
- AI创新实践（提示工程、AI工具使用、工作流自动化、方案设计）"""

    # ── 组合多样性要求 ──
    diversity_rules = f"""

【多样性与质量要求】
1. 题目风格混合——请在以下推荐风格中选择并混合使用：
{style_section}
2. 情境多样——题目场景应涉及：{context_section}
3. 正确答案分布——{count}道题中，正确答案应分布在不同选项位置（ABCD），不要集中在某一个
4. 知识点覆盖——每道题应考查不同的知识点或从不同角度考查，避免重复
5. 干扰项质量——每个干扰项都应对应一种常见误解，在explanation中简要说明为何该选项不正确"""

    return f"""请生成 {count} 道题目，严格遵守系统提示中的输出格式和质量标准。

【基本要求】
- 题型：{type_str}
{difficulty_section}{bloom_section}
- 每道题必须包含 stem、correct_answer、explanation、knowledge_tags、dimension
- 选择题和判断题必须包含 options（键为 A/B/C/D）
- 直接输出 JSON 数组，不要包含任何其他文字{diversity_rules}{content_section}{custom_section}"""


# ── LLM 返回结果后处理与校验 ────────────────────────────────────────

def _normalize_options_keys(options: dict) -> dict:
    """将非标准选项键规范化为 A/B/C/D。

    处理常见的LLM输出偏差：
    - 中文键: {"选项A": "..."} -> {"A": "..."}
    - 数字键: {"1": "..."} -> {"A": "..."}
    - 小写键: {"a": "..."} -> {"A": "..."}
    """
    if not options or not isinstance(options, dict):
        return options

    keys = list(options.keys())
    # 已经是标准格式
    if all(k in "ABCDEFGH" and len(k) == 1 for k in keys):
        return options

    # 小写字母键 -> 大写
    if all(k in "abcdefgh" and len(k) == 1 for k in keys):
        return {k.upper(): v for k, v in options.items()}

    # 数字键 -> 字母
    digit_map = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
    if all(k in digit_map for k in keys):
        return {digit_map[k]: v for k, v in options.items()}

    # 包含中文或前缀的键 -> 按顺序映射为 A/B/C/D
    letters = "ABCDEFGH"
    normalized = {}
    for i, (_, v) in enumerate(options.items()):
        if i < len(letters):
            normalized[letters[i]] = v
    return normalized


def _normalize_correct_answer(answer: str, question_type: str, options: Optional[dict]) -> str:
    """规范化正确答案格式。"""
    if not answer:
        return answer

    answer = answer.strip()

    if question_type in ("fill_blank", "short_answer", "essay"):
        # 主观题：去掉「参考答案：」等前缀
        for prefix in ("参考答案：", "参考答案:", "答案：", "答案:", "答："):
            if answer.startswith(prefix):
                answer = answer[len(prefix):].strip()
        return answer

    # 选择题/判断题：提取大写字母
    if question_type in ("single_choice", "multiple_choice", "true_false"):
        # 尝试提取字母（兼容 "答案A" "选项B" "A和C" "A、B" 等格式）
        letters = sorted(set(re.findall(r"[A-D]", answer.upper())))
        if letters:
            result = "".join(letters)
            # 单选题只取第一个
            if question_type == "single_choice":
                return result[0]
            # 判断题只允许 A 或 B
            if question_type == "true_false":
                return result[0] if result[0] in ("A", "B") else "A"
            return result

        # 判断题中文答案映射
        if question_type == "true_false":
            if answer in ("正确", "对", "是", "True", "true", "T"):
                return "A"
            if answer in ("错误", "错", "否", "False", "false", "F"):
                return "B"

        # 选择题中文选项映射（如答案文本匹配某个选项值）
        if options:
            for key, val in options.items():
                if answer == val or answer.strip() == val.strip():
                    return key

    return answer


def _validate_and_fix_question(raw: dict, requested_types: list[str]) -> Optional[dict]:
    """校验并修复单道题目，返回 None 表示该题无法修复应丢弃。"""
    # ── 1. 题型规范化 ──
    qt = raw.get("question_type", "")
    if qt in LABEL_TO_TYPE:
        qt = LABEL_TO_TYPE[qt]
    # 常见 LLM 拼写偏差
    type_aliases = {
        "single": "single_choice", "multi_choice": "multiple_choice",
        "multi": "multiple_choice", "boolean": "true_false",
        "judge": "true_false", "judgment": "true_false",
        "blank": "fill_blank", "short": "short_answer",
    }
    qt = type_aliases.get(qt, qt)

    if qt not in VALID_TYPES:
        # 尝试匹配请求的第一个类型
        qt = requested_types[0] if requested_types else "single_choice"
    raw["question_type"] = qt

    # ── 2. 必填字段检查 ──
    stem = raw.get("stem", "")
    if not stem or not isinstance(stem, str) or len(stem.strip()) < 5:
        logger.warning(f"题目 stem 无效，已丢弃: {stem!r}")
        return None
    raw["stem"] = stem.strip()

    correct_answer = raw.get("correct_answer", "")
    if not correct_answer:
        logger.warning(f"题目缺少 correct_answer，已丢弃: {stem[:30]}")
        return None

    # ── 3. 选项规范化 ──
    options = raw.get("options")
    if qt in OPTION_TYPES:
        if not options or not isinstance(options, dict):
            # 判断题可以自动补充
            if qt == "true_false":
                options = {"A": "正确", "B": "错误"}
            else:
                logger.warning(f"选择题缺少有效 options，已丢弃: {stem[:30]}")
                return None
        options = _normalize_options_keys(options)
        # 确保至少有2个选项
        if len(options) < 2:
            logger.warning(f"选项数量不足，已丢弃: {stem[:30]}")
            return None
        raw["options"] = options
    else:
        # 填空题/简答题不需要选项
        raw["options"] = None

    # ── 4. 正确答案规范化 ──
    raw["correct_answer"] = _normalize_correct_answer(
        str(correct_answer), qt, raw.get("options")
    )

    # 验证答案有效性
    if qt == "single_choice" and raw["correct_answer"] not in (raw.get("options") or {}):
        # 尝试修复：如果答案文本匹配某个选项值
        if raw.get("options"):
            for k, v in raw["options"].items():
                if str(correct_answer).strip() == v.strip():
                    raw["correct_answer"] = k
                    break
            else:
                # 默认设为 A，并记录警告
                logger.warning(
                    f"单选题答案 '{correct_answer}' 不在选项中，默认设为A: {stem[:30]}"
                )
                raw["correct_answer"] = "A"

    if qt == "multiple_choice" and raw.get("options"):
        valid_keys = set(raw["options"].keys())
        answer_keys = set(raw["correct_answer"])
        if not answer_keys.issubset(valid_keys):
            logger.warning(
                f"多选题答案 '{raw['correct_answer']}' 包含无效选项: {stem[:30]}"
            )
            fixed = "".join(sorted(answer_keys & valid_keys))
            raw["correct_answer"] = fixed or "AB"

    # ── 5. 解析字段 ──
    explanation = raw.get("explanation")
    if not explanation or not isinstance(explanation, str) or len(explanation.strip()) < 2:
        raw["explanation"] = f"本题正确答案为 {raw['correct_answer']}。"
    else:
        raw["explanation"] = explanation.strip()

    # ── 6. knowledge_tags 规范化 ──
    tags = raw.get("knowledge_tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，、;；]", tags) if t.strip()]
    if not isinstance(tags, list):
        tags = ["AI素养"]
    raw["knowledge_tags"] = tags

    # ── 7. dimension 自动分类 ──
    dim = raw.get("dimension", "")
    if dim not in FIVE_DIMENSIONS:
        # LLM 未给出有效维度 → 用关键词匹配自动分类
        raw["dimension"] = classify_dimension(raw["stem"], raw.get("knowledge_tags"))
    else:
        raw["dimension"] = dim

    return raw


# ── 主入口 ──────────────────────────────────────────────────────────

def generate_questions_via_llm(
    content: str,
    question_types: list[str],
    count: int = 3,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> list[dict]:
    """Generate questions using LLM API.

    Returns list of validated question dicts. Falls back to templates on failure.
    """
    _cfg = get_llm_config_sync("question_generation")
    if _cfg.api_key == "your-api-key":
        logger.warning("LLM API key not configured, using template fallback")
        return _template_fallback(content, question_types, count, difficulty, bloom_level)

    try:
        client = make_openai_client(_cfg)


        user_prompt = _build_user_prompt(
            content, question_types, count, difficulty, bloom_level, custom_prompt
        )

        response = client.chat.completions.create(
            model=_cfg.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4096,
        )

        raw = response.choices[0].message.content.strip()

        # Extract JSON from response (LLM may wrap in ```json ... ```)
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

        questions = json.loads(raw)
        if not isinstance(questions, list):
            questions = [questions]

        # ── 逐题校验并修复 ──
        validated = []
        for q in questions:
            fixed = _validate_and_fix_question(q, question_types)
            if fixed is not None:
                validated.append(fixed)

        if not validated:
            logger.warning("LLM output passed 0 validation, falling back to template")
            return _template_fallback(content, question_types, count, difficulty, bloom_level)

        return validated[:count]

    except json.JSONDecodeError as e:
        logger.error(f"LLM output is not valid JSON: {e}")
        return _template_fallback(content, question_types, count, difficulty, bloom_level)
    except Exception as e:
        logger.error(f"LLM question generation failed: {e}")
        return _template_fallback(content, question_types, count, difficulty, bloom_level)


# ── 模板降级（无 LLM 时使用） ────────────────────────────────────────

def _extract_key_sentences(content: str, max_count: int = 5) -> list[str]:
    """从内容中提取关键完整句子（不截断）。"""
    if not content:
        return []
    # 按句号/问号/感叹号/换行分句
    sentences = re.split(r"[。！？\n]", content)
    # 过滤太短或太长的句子
    sentences = [s.strip() for s in sentences if 8 <= len(s.strip()) <= 120]
    return sentences[:max_count]


def _template_fallback(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
) -> list[dict]:
    """Template-based fallback when LLM is not available.

    Generates structurally varied questions from content sentences.
    Uses multiple template variants per question type for diversity.
    """
    sentences = _extract_key_sentences(content)
    if not sentences:
        # 无有效句子时用通用AI素养题（扩充为8条覆盖更多维度）
        sentences = [
            "人工智能是计算机科学的一个分支，致力于创建能模拟人类智能的系统",
            "机器学习是AI的核心方法，通过数据驱动的方式让计算机自动学习",
            "深度学习使用多层神经网络来处理复杂的模式识别任务",
            "自然语言处理（NLP）使计算机能够理解和生成人类语言",
            "AI伦理关注人工智能技术的公平性、透明性和责任归属",
            "大语言模型（LLM）通过海量文本预训练获得了强大的语言理解和生成能力",
            "提示工程是一种通过设计有效指令来引导AI模型输出的技术",
            "算法偏见是指AI系统因训练数据或设计缺陷而产生的系统性歧视",
        ]

    # ── 单选题模板池（3种变体，正确答案分布在B/D/C） ──
    def _single_choice_variant_1(sent, dim):
        short = sent.split("，")[0] if "，" in sent else sent[:20]
        return {
            "question_type": "single_choice",
            "dimension": dim,
            "stem": "一位数据分析师在学习AI基础知识时遇到以下概念：'" + sent + "'。对这一概念的理解，最准确的是？",
            "options": {
                "A": "该概念仅在理论层面有价值，缺乏实际应用场景",
                "B": short + "是AI领域的重要基础概念，具有广泛的应用价值",
                "C": "这一概念已经被更先进的技术完全取代",
                "D": "该概念仅适用于小规模数据处理，无法扩展",
            },
            "correct_answer": "B",
            "explanation": "选项B正确。" + sent + "是AI领域的重要基础知识。A错在否认实际应用价值；C错在'完全取代'的绝对化表述；D错在'仅适用于小规模'的限制。",
            "knowledge_tags": ["AI素养", "概念理解"],
        }

    def _single_choice_variant_2(sent, dim):
        short = sent.split("，")[0] if "，" in sent else sent[:15]
        return {
            "question_type": "single_choice",
            "dimension": dim,
            "stem": "在一次AI素养培训中，讲师提到：'" + sent + "'。以下哪位学员的理解最为正确？",
            "options": {
                "A": "学员甲：这个概念太抽象了，和我们日常工作没有关系",
                "B": "学员乙：这个概念虽然重要，但已经过时了",
                "C": "学员丙：这个概念说明AI可以完全替代人类的判断",
                "D": "学员丁：这正说明了AI技术的一个核心特征——" + short,
            },
            "correct_answer": "D",
            "explanation": "学员丁的理解最准确，正确把握了核心要点。甲忽视了实际关联性；乙的'过时'说法错误；丙的'完全替代'过于绝对。",
            "knowledge_tags": ["AI素养", "概念辨析"],
        }

    def _single_choice_variant_3(sent, dim):
        dim_short = dim.replace("AI", "")
        return {
            "question_type": "single_choice",
            "dimension": dim,
            "stem": "以下关于AI技术的描述中，哪一项与'" + sent[:25] + "...'这一知识点最直接相关？",
            "options": {
                "A": "AI系统的运行完全不依赖任何形式的数据输入",
                "B": "所有AI应用都必须使用专用GPU硬件才能运行",
                "C": "该知识点反映了AI技术在" + dim_short + "方面的重要特征",
                "D": "这一技术只能处理英文，无法支持中文等其他语言",
            },
            "correct_answer": "C",
            "explanation": "C正确地将知识点与" + dim + "维度关联。A错：AI系统需要数据；B错：并非都需要专用GPU；D错：现代AI技术支持多语言。",
            "knowledge_tags": ["AI素养", dim],
        }

    single_choice_templates = [_single_choice_variant_1, _single_choice_variant_2, _single_choice_variant_3]

    # ── 多选题模板池（2种变体） ──
    def _multiple_choice_variant_1(sent, dim):
        return {
            "question_type": "multiple_choice",
            "dimension": dim,
            "stem": "某公司正在开展AI素养培训，以下哪些观点与'" + sent + "'这一知识点的核心思想一致？",
            "options": {
                "A": "AI技术的发展需要跨学科知识的支撑",
                "B": "理解这一概念有助于更好地使用AI工具",
                "C": "该概念表明AI已无需人类参与即可自主决策",
                "D": "掌握这一知识对提升AI素养具有重要意义",
            },
            "correct_answer": "ABD",
            "explanation": "A、B、D正确。AI的发展确实需要多学科支撑，理解核心概念有助于工具使用和素养提升。C错误，AI仍需人类监督。",
            "knowledge_tags": ["AI素养", "综合理解"],
        }

    def _multiple_choice_variant_2(sent, dim):
        return {
            "question_type": "multiple_choice",
            "dimension": dim,
            "stem": "关于'" + sent + "'，以下哪些说法是合理的？",
            "options": {
                "A": "这体现了AI技术不断演进的特征",
                "B": "理解这一点需要具备一定的计算思维基础",
                "C": "这说明AI技术没有任何局限性",
                "D": "该概念在实际应用中具有重要的指导意义",
            },
            "correct_answer": "ABD",
            "explanation": "A、B、D合理。C错误——任何技术都存在局限性，这是批判性思维的基本要求。",
            "knowledge_tags": ["AI素养", "批判分析"],
        }

    multiple_choice_templates = [_multiple_choice_variant_1, _multiple_choice_variant_2]

    # ── 判断题模板池（3种变体，混合正确A和错误B） ──
    def _true_false_variant_1(sent, dim):
        return {
            "question_type": "true_false",
            "dimension": dim,
            "stem": sent + "。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "A",
            "explanation": "该描述正确。" + sent + "是AI领域公认的基本事实。",
            "knowledge_tags": ["AI素养", "基础判断"],
        }

    def _true_false_variant_2(sent, dim):
        return {
            "question_type": "true_false",
            "dimension": "AI伦理安全",
            "stem": "AI技术的所有应用都不需要人类进行任何形式的监督和审核。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "B",
            "explanation": "该说法错误。虽然AI技术可以自动化许多任务，但在关键决策、伦理审查等方面仍需要人类监督，这是负责任AI的基本原则。",
            "knowledge_tags": ["AI伦理", "人机协作"],
        }

    def _true_false_variant_3(sent, dim):
        return {
            "question_type": "true_false",
            "dimension": "AI基础知识",
            "stem": "机器学习模型的性能完全取决于算法的先进程度，与训练数据的质量无关。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "B",
            "explanation": "该说法错误。数据质量对模型性能有至关重要的影响，'垃圾进，垃圾出'（Garbage In, Garbage Out）是机器学习的基本准则。",
            "knowledge_tags": ["机器学习", "数据质量"],
        }

    true_false_templates = [_true_false_variant_1, _true_false_variant_2, _true_false_variant_3]

    # ── 简答题提问角度池 ──
    short_answer_stems = [
        '请结合实际案例，说明"{sent}"的含义及其在AI应用中的意义。',
        '有人说"{sent}"。请用自己的理解解释这一概念，并给出至少一个应用场景。',
        '针对"{sent}"这一知识点，请从定义、原理和应用三个角度进行简要论述。',
    ]

    questions = []
    for i in range(count):
        qtype = question_types[i % len(question_types)]
        sent = sentences[i % len(sentences)]
        dim = classify_dimension(sent)

        if qtype == "single_choice":
            template_fn = single_choice_templates[i % len(single_choice_templates)]
            q = template_fn(sent, dim)
        elif qtype == "multiple_choice":
            template_fn = multiple_choice_templates[i % len(multiple_choice_templates)]
            q = template_fn(sent, dim)
        elif qtype == "true_false":
            template_fn = true_false_templates[i % len(true_false_templates)]
            q = template_fn(sent, dim)
        elif qtype == "fill_blank":
            words = re.findall(r"[\u4e00-\u9fa5A-Za-z]{2,6}", sent)
            blank_word = words[0] if words else "人工智能"
            stem_with_blank = sent.replace(blank_word, "____", 1)
            # 交替使用简洁式和情境包裹式
            if i % 2 == 0:
                stem_text = "请补全以下AI领域的关键概念：" + stem_with_blank
            else:
                stem_text = "在介绍AI基础知识时，有这样一段描述：'" + stem_with_blank + "'。请填入正确的术语。"
            q = {
                "question_type": "fill_blank",
                "dimension": dim,
                "stem": stem_text,
                "options": None,
                "correct_answer": blank_word,
                "explanation": "完整表述为：" + sent + "。" + blank_word + "是该知识点的核心术语。",
                "knowledge_tags": ["AI素养", "概念填空"],
            }
        else:  # short_answer, essay
            stem_template = short_answer_stems[i % len(short_answer_stems)]
            q = {
                "question_type": qtype,
                "dimension": dim,
                "stem": stem_template.format(sent=sent),
                "options": None,
                "correct_answer": (
                    sent + "。这一概念在AI领域具有重要意义，"
                    "它帮助我们理解人工智能系统的基本工作原理和应用边界。"
                    "在实际应用中，这一概念广泛应用于数据分析、智能决策等场景。"
                ),
                "explanation": "答案应涵盖：1）核心概念的准确定义；2）基本原理的阐述；3）至少一个实际应用场景的说明。",
                "knowledge_tags": ["AI素养", "综合论述"],
            }

        questions.append(q)

    return questions
