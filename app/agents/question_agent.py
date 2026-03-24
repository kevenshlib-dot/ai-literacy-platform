"""Question generation agent - uses LLM to generate questions from knowledge units."""
import hashlib
import json
import logging
import random
import re
from itertools import combinations
from typing import Optional

from openai import OpenAI
from httpx import Timeout

from app.core.config import settings
from app.agents.llm_utils import (
    build_disable_thinking_extra_body,
    extract_json_text,
)
from app.agents.model_registry import (
    ModelConfig,
    get_default_model_config,
    resolve_api_key,
    resolve_base_url,
)

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
STRICT_FORMAT_TYPES = {"true_false", "fill_blank"}
BLANK_MARKERS = ("____", "___", "（ ）", "( )", "（）", "【 】", "[]", "＿", "填空")
BLANK_MARKER_PATTERN = r"(?:____|___|（\s*）|\(\s*\)|（）|【\s*】|\[\s*\]|＿|填空)"
TRUE_FALSE_INTERROGATIVE_PREFIXES = (
    "以下",
    "下列",
    "请判断",
    "判断以下",
    "判断下列",
    "是否",
)
QUESTION_GENERATION_RETRY_LIMIT = 2

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
    "法律合规场景（如知识产权保护、合同审查、数据合规、伦理审批）",
    "新闻媒体场景（如事实核查、深度报道、自媒体运营、信息甄别）",
]

# 直接出题时的主题池 - 增加多样性
DIRECT_GENERATION_TOPICS = [
    {
        "theme": "AI与自然语言处理",
        "keywords": "大语言模型、Transformer架构、文本生成、机器翻译、情感分析、对话系统、提示工程、RAG检索增强生成",
    },
    {
        "theme": "AI与计算机视觉",
        "keywords": "图像识别、目标检测、图像分割、人脸识别、OCR文字识别、视频分析、医学影像、自动驾驶视觉",
    },
    {
        "theme": "AI与数据科学",
        "keywords": "数据预处理、特征工程、模型评估、A/B测试、数据可视化、异常检测、预测建模、数据仓库",
    },
    {
        "theme": "AI伦理与社会影响",
        "keywords": "算法偏见、隐私保护、深度伪造、AI监管、就业影响、数字鸿沟、信息茧房、版权争议",
    },
    {
        "theme": "AI工具使用与效率",
        "keywords": "ChatGPT/Claude使用技巧、AI绘画工具、AI编程助手、AI办公自动化、AI辅助写作、AI翻译工具",
    },
    {
        "theme": "机器学习基础原理",
        "keywords": "监督学习、无监督学习、强化学习、过拟合与正则化、梯度下降、交叉验证、集成学习、迁移学习",
    },
    {
        "theme": "深度学习与神经网络",
        "keywords": "CNN卷积神经网络、RNN循环神经网络、注意力机制、生成对抗网络GAN、自编码器、扩散模型",
    },
    {
        "theme": "AI行业应用案例",
        "keywords": "智慧医疗、智能金融、智能制造、智慧教育、智慧农业、智能物流、AI客服、个性化推荐",
    },
    {
        "theme": "AI安全与对抗",
        "keywords": "对抗样本、数据投毒、模型窃取、后门攻击、联邦学习隐私、差分隐私、鲁棒性、安全审计",
    },
    {
        "theme": "AI创新前沿",
        "keywords": "多模态AI、AI Agent、世界模型、具身智能、量子机器学习、神经符号AI、小样本学习、AI科学发现",
    },
]

# 出题语气/视角池 - 增加题干表达方式多样性
QUESTION_VOICE_STYLES = [
    "第三人称叙事视角：以'某公司/某团队/某研究员'为主角设置情境",
    "第二人称代入视角：以'你作为...需要...'的方式让考生代入角色",
    "新闻报道视角：以'据报道/近日/最新研究表明'引出真实感场景",
    "对话讨论视角：以'同事/朋友/专家'之间的讨论引出问题",
    "问题驱动视角：以'如何解决/怎样实现/为什么会'开头直接提出挑战",
]

FORBIDDEN_MATERIAL_REFERENCES = [
    "结合素材", "根据本文", "根据材料", "根据上文", "根据下文",
    "本文作者", "作者认为", "本书", "该书", "书中", "出版社",
    "出版信息", "ISBN", "第1章", "第2章", "第3章", "第4章", "第5章",
    "第1节", "第2节", "第3节", "章节",
]

FORBIDDEN_MATERIAL_REGEXES = [
    re.compile(r"第\s*[一二三四五六七八九十0-9]+\s*[章节篇部分]"),
    re.compile(r"(作者|著者|主编|副主编)[：: ]"),
    re.compile(r"(出版社|出版时间|出版日期|版次)[：: ]"),
]

GARBLED_TEXT_MARKERS = ["�", "\x00", "□", "�", "锟斤拷"]
MAX_ROLE_LEAD_STEMS = 2
MATERIAL_GENERATION_MAX_ATTEMPTS = 2
STRUCTURED_OUTPUT_UNSUPPORTED_HOSTS = ("localhost", "127.0.0.1", "100.64.", "192.168.", "10.", "172.")

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
DEFAULT_QUESTION_SYSTEM_PROMPT = """\
# 角色定义

你同时具备三个身份：
1. **资深社会人文学科教授**——擅长将专业知识转化为生动、贴近实际的考题，语言风格灵活多变
2. **精通AI的技术实践者**——对人工智能的原理、工具、伦理和应用有深入的实战经验
3. **资深图书馆专家**——善于从文献资料中提取核心知识点，精准把握信息素养和知识组织

你的专业能力：
- 布鲁姆认知目标分类法（Bloom's Taxonomy）的精准应用
- 基于情境的评测设计（Scenario-Based Assessment）
- 干扰项心理学（Distractor Psychology）：利用常见误解和认知偏差设计高质量干扰项
- AI/人工智能领域的全面知识覆盖

你的任务是生成高质量、多样化的AI素养评测题目。

# 出题质量标准

## 题干设计标准
1. **语言多样化**：每道题的题干必须使用不同的表达方式和句式开头，严禁使用固定模板。具体要求：
   - 不要每道题都以"以下关于...的描述"或"以下哪项..."开头
   - 在不违反题型硬约束的前提下，交替使用陈述句、设问句、情境描述、案例引用、数据引用等不同开头
   - 每道题的语言风格应有所变化（学术风、口语风、新闻风、叙事风等）
2. **情境丰富性**：优先使用具体情境（工作场景、学习场景、生活场景）包裹知识点，但若题型硬约束要求固定格式，必须优先满足题型格式
3. **认知层次精准**：题目应精准对应布鲁姆认知层次——记忆/理解层次问"是什么"，应用层次问"怎么做"，分析层次问"为什么"，评价层次问"哪个更好"，创造层次问"如何设计"
4. **表述清晰完整**：题干必须自足，不依赖外部信息即可作答；避免否定句式（"以下哪项不正确"）除非明确标注
5. **答案简明扼要**：正确答案和解析要准确精练，避免冗长啰嗦

## 干扰项设计标准（核心）
1. **基于真实误解**：每个干扰项应对应一种常见的认知错误或误解，而非随意编造的错误选项
2. **似是而非**：干扰项应在表面上看起来合理，但在关键概念上存在偏差
3. **长度均衡**：所有选项（包括正确答案）的长度应大致相同，不能让正确答案因为更详细而被猜出
4. **独立性**：选项之间不能互相矛盾导致排除法过于容易，也不能有包含关系
5. **正确答案位置随机**：正确答案不能总是A或总是最长的选项，应在A/B/C/D之间均匀分布

## 反模式（必须避免，违反将导致题目无效）
- ❌ 所有题目正确答案都是同一个字母（必须随机分布在A/B/C/D中）
- ❌ 题干过于笼统："关于XX，以下说法正确的是？"（没有情境）
- ❌ 题干句式雷同：多道题都以"以下关于..."或"以下哪项..."开头
- ❌ 干扰项一眼假：如"AI已经完全取代了人类"这种明显错误
- ❌ 题目之间高度重复：考查同一个知识点的不同措辞
- ❌ 判断题全部为"正确"
- ❌ 选项中出现"以上都是/以上都不是"
- ❌ 考查书名、作者、章节标题等形式化信息（有参考素材时）
- ❌ 答案和解析过于冗长（应简明扼要）

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
5. **判断题 stem 必须是完整陈述句**，不得出现问号、"以下哪项"、"是否正确"等疑问表达
6. **填空题 stem 必须包含明确空位标记**（如 ____ / （ ）），且不得写成问答题或简答题
7. **填空题和简答题** 的 options 必须为 null
8. **explanation 必须提供**，不能为空，且应解释为什么正确答案对、其他选项错
9. **stem 必须完整**，语句通顺，不能截断
10. **干扰项**必须具有合理性和迷惑性，不能一眼看出错误
11. 每道题的 knowledge_tags 必须是字符串数组
12. **dimension 必须是以下五个值之一**：AI基础知识、AI技术应用、AI伦理安全、AI批判思维、AI创新实践
13. 直接输出 JSON 数组，不要加 ```json 标记，不要加任何其他文字
14. **正确答案位置分散**：多道题时，正确答案应分布在不同选项位置（A/B/C/D），不能全部相同
"""

DEFAULT_QUESTION_USER_PROMPT_TEMPLATE = """请生成 {{count}} 道题目，严格遵守系统提示中的输出格式和质量标准。

【基本要求】
- 题型：{{question_types}}
{{difficulty_section}}{{bloom_section}}
- 每道题必须包含 stem、correct_answer、explanation、knowledge_tags、dimension
- 选择题和判断题必须包含 options（键为 A/B/C/D）
- 直接输出 JSON 数组，不要包含任何其他文字{{diversity_rules}}{{question_plan_section}}{{content_section}}{{custom_requirements}}"""

QUESTION_PROMPT_TEMPLATE_PLACEHOLDERS = [
    {
        "key": "{{count}}",
        "description": "本次要生成的题目数量",
        "source": "题型分配合计数量",
    },
    {
        "key": "{{question_types}}",
        "description": "题型说明，如单选题(single_choice)",
        "source": "题型分配",
    },
    {
        "key": "{{difficulty_section}}",
        "description": "难度等级及出题要求",
        "source": "难度等级",
    },
    {
        "key": "{{bloom_section}}",
        "description": "布鲁姆认知层次说明",
        "source": "认知层次",
    },
    {
        "key": "{{diversity_rules}}",
        "description": "题干多样性与质量规则",
        "source": "系统自动生成的质量与多样性规则",
    },
    {
        "key": "{{question_plan_section}}",
        "description": "系统自动生成的知识点出题规划",
        "source": "规划阶段抽取的知识点、证据和出题建议",
    },
    {
        "key": "{{content_section}}",
        "description": "素材内容或自由出题范围",
        "source": "所选素材；未选素材时自动切换为自由出题范围",
    },
    {
        "key": "{{custom_requirements}}",
        "description": "页面额外要求(custom_prompt)",
        "source": "额外要求",
    },
]

ALLOWED_USER_PROMPT_TEMPLATE_KEYS = {
    item["key"][2:-2] for item in QUESTION_PROMPT_TEMPLATE_PLACEHOLDERS
}
REQUIRED_USER_PROMPT_TEMPLATE_KEYS = {
    "count",
    "question_types",
    "difficulty_section",
    "diversity_rules",
    "question_plan_section",
    "content_section",
}
USER_PROMPT_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Backwards-compatible alias for existing imports.
SYSTEM_PROMPT = DEFAULT_QUESTION_SYSTEM_PROMPT


def validate_user_prompt_template(template: str) -> str:
    placeholders = [match.group(1).strip() for match in USER_PROMPT_TEMPLATE_PATTERN.finditer(template or "")]
    unknown = sorted({name for name in placeholders if name not in ALLOWED_USER_PROMPT_TEMPLATE_KEYS})
    if unknown:
        rendered = ", ".join(f"{{{{{name}}}}}" for name in unknown)
        raise ValueError(f"用户提示词模板包含未知占位符: {rendered}")
    missing = sorted(REQUIRED_USER_PROMPT_TEMPLATE_KEYS - set(placeholders))
    if missing:
        rendered = ", ".join(f"{{{{{name}}}}}" for name in missing)
        raise ValueError(f"用户提示词模板缺少必填占位符: {rendered}")
    return template


def render_user_prompt(template: str, context: dict[str, str]) -> str:
    validate_user_prompt_template(template)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return context.get(key, match.group(0))

    return USER_PROMPT_TEMPLATE_PATTERN.sub(replace, template)


def _build_prompt_rng(seed_payload: dict, prompt_seed: Optional[int]):
    if prompt_seed is None:
        return random

    material = {
        "prompt_seed": prompt_seed,
        **seed_payload,
    }
    derived_seed = int(
        hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        16,
    )
    return random.Random(derived_seed)


def _extract_content_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not content:
        return sections

    pattern = re.compile(r"【([^】]+)】\n(.*?)(?=(?:\n\n【)|\Z)", re.S)
    for match in pattern.finditer(content):
        title = match.group(1).strip()
        body = match.group(2).strip()
        if title and body:
            sections[title] = body
    return sections


def _split_keywords_text(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[、,，;；\n]+", text)
    return [part.strip() for part in parts if part.strip()]


def _dedupe_text_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = _normalize_text_for_compare(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item.strip())
    return deduped


def _summarize_knowledge_point(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = re.sub(r"^[：:;；，,。.\-]+", "", cleaned)
    if not cleaned:
        return "AI素养关键知识"
    return cleaned[:32]


def _has_blank_marker(text: str) -> bool:
    return any(marker in (text or "") for marker in BLANK_MARKERS)


def _looks_like_true_false_statement(stem: str) -> bool:
    normalized = str(stem or "").strip()
    if not normalized:
        return False
    if "?" in normalized or "？" in normalized:
        return False
    if normalized.endswith("吗"):
        return False
    return not any(normalized.startswith(prefix) for prefix in TRUE_FALSE_INTERROGATIVE_PREFIXES)


def _build_type_rule_section(question_types: list[str]) -> str:
    normalized_types = [qt for qt in question_types if qt in VALID_TYPES]
    if not normalized_types:
        return ""

    lines = [
        "",
        "",
        "【题型硬约束——优先级高于多样性要求】",
        "所有风格变化、情境包装和语言多样性都必须服从题型格式；若冲突，必须优先满足题型硬约束。",
    ]
    if any(qt in ("single_choice", "multiple_choice") for qt in normalized_types):
        lines.extend([
            "- 单选题/多选题：必须使用 A/B/C/D 四个标准选项；干扰项应基于真实误解，但不得改变题型结构。",
        ])
    if "true_false" in normalized_types:
        lines.extend([
            "- 判断题：题干必须写成可直接判断真假的完整陈述句，严禁使用问号、'以下哪项'、'是否正确'、'请判断'等疑问表达。",
            "- 判断题：options 必须严格且仅为 {\"A\": \"正确\", \"B\": \"错误\"}，correct_answer 只能是 A 或 B。",
            "- 判断题：如果某个知识点更适合提问式表达，请放弃该知识点，改选能自然写成陈述句的知识点。",
        ])
    if "fill_blank" in normalized_types:
        lines.extend([
            "- 填空题：题干必须包含明确空位标记（如 ____ 或 （ ）），不得改写成问答题、简答题或判断题。",
            "- 填空题：options 必须为 null，correct_answer 应是简洁术语、短语或关键词，不应是一整句解释。",
            "- 填空题：优先选择概念名称、关键术语、核心步骤中的缺失项，不要选择需要长篇作答的知识点。",
        ])
    if "short_answer" in normalized_types:
        lines.extend([
            "- 简答题：题干必须明确说明作答任务，options 必须为 null，参考答案应为文本型答案而非字母选项。",
        ])
    return "\n".join(lines)


def _build_plan_type_requirements(question_types: list[str]) -> str:
    lines: list[str] = []
    if "true_false" in question_types:
        lines.append("7. 若题型为判断题，只规划能自然写成陈述句的知识点，不要规划成疑问句或选择题式表达；")
    if "fill_blank" in question_types:
        lines.append("8. 若题型为填空题，只规划能抽取出术语、关键词、短语或固定步骤缺失项的知识点；")
    if "short_answer" in question_types:
        lines.append("9. 若题型为简答题，只规划需要简要解释、说明原因或概括方法的知识点；")
    return "\n".join(lines)


def _build_choice_answer_enums(min_answers: int = 1) -> list[str]:
    letters = ("A", "B", "C", "D")
    answers: list[str] = []
    for size in range(min_answers, len(letters) + 1):
        for combo in combinations(letters, size):
            answers.append("".join(combo))
    return answers


def _build_choice_options_schema() -> dict:
    return {
        "type": "object",
        "required": ["A", "B", "C", "D"],
        "additionalProperties": False,
        "properties": {
            "A": {"type": "string", "minLength": 1},
            "B": {"type": "string", "minLength": 1},
            "C": {"type": "string", "minLength": 1},
            "D": {"type": "string", "minLength": 1},
        },
    }


def _build_question_item_schema(question_type: str) -> dict:
    base_properties = {
        "question_type": {"type": "string", "const": question_type},
        "dimension": {
            "type": "string",
            "enum": FIVE_DIMENSIONS,
        },
        "stem": {"type": "string", "minLength": 5},
        "correct_answer": {"type": "string"},
        "explanation": {"type": "string", "minLength": 2},
        "knowledge_tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    }

    if question_type == "single_choice":
        return {
            "type": "object",
            "required": list(base_properties.keys()) + ["options"],
            "additionalProperties": False,
            "properties": {
                **base_properties,
                "options": _build_choice_options_schema(),
                "correct_answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
            },
        }

    if question_type == "multiple_choice":
        return {
            "type": "object",
            "required": list(base_properties.keys()) + ["options"],
            "additionalProperties": False,
            "properties": {
                **base_properties,
                "options": _build_choice_options_schema(),
                "correct_answer": {"type": "string", "enum": _build_choice_answer_enums(min_answers=2)},
            },
        }

    if question_type == "true_false":
        return {
            "type": "object",
            "required": list(base_properties.keys()) + ["options"],
            "additionalProperties": False,
            "properties": {
                **base_properties,
                "stem": {
                    "type": "string",
                    "minLength": 5,
                    "not": {"pattern": r"[？?]"},
                },
                "options": {
                    "type": "object",
                    "required": ["A", "B"],
                    "additionalProperties": False,
                    "properties": {
                        "A": {"const": "正确"},
                        "B": {"const": "错误"},
                    },
                },
                "correct_answer": {"type": "string", "enum": ["A", "B"]},
            },
        }

    if question_type == "fill_blank":
        return {
            "type": "object",
            "required": list(base_properties.keys()) + ["options"],
            "additionalProperties": False,
            "properties": {
                **base_properties,
                "stem": {
                    "type": "string",
                    "minLength": 5,
                    "pattern": BLANK_MARKER_PATTERN,
                },
                "options": {"type": "null"},
                "correct_answer": {"type": "string", "minLength": 1, "maxLength": 48},
            },
        }

    return {
        "type": "object",
        "required": list(base_properties.keys()) + ["options"],
        "additionalProperties": False,
        "properties": {
            **base_properties,
            "options": {"type": "null"},
            "correct_answer": {"type": "string", "minLength": 1},
        },
    }


def build_question_plan(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    prompt_seed: Optional[int] = None,
) -> list[dict]:
    """Build a deterministic question plan before final prompt generation."""
    rng = _build_prompt_rng(
        {
            "content": content,
            "question_types": question_types,
            "count": count,
            "difficulty": difficulty,
            "bloom_level": bloom_level,
            "custom_prompt": custom_prompt,
            "stage": "question_plan",
        },
        prompt_seed,
    )

    sections = _extract_content_sections(content)
    title = sections.get("知识单元标题", "")
    summary = sections.get("知识单元摘要", "")
    keywords = _split_keywords_text(sections.get("知识关键词", ""))
    body = sections.get("知识单元正文", content)
    sentences = _extract_key_sentences(body, max_count=max(count * 2, 6))

    topic_candidates = _dedupe_text_items(
        keywords
        + ([title] if title else [])
        + ([summary] if summary else [])
        + sentences
    )
    if not topic_candidates:
        sampled_topics = rng.sample(
            DIRECT_GENERATION_TOPICS,
            min(3, len(DIRECT_GENERATION_TOPICS)),
        )
        topic_candidates = [f"{topic['theme']}：{topic['keywords']}" for topic in sampled_topics]

    evidence_candidates = _dedupe_text_items(
        ([summary] if summary else [])
        + sentences
        + ([body[:120]] if body else [])
    )
    if not evidence_candidates:
        evidence_candidates = topic_candidates[:]

    selected_styles = rng.sample(
        QUESTION_STEM_STYLES,
        min(max(count, 1), len(QUESTION_STEM_STYLES)),
    )
    selected_contexts = rng.sample(
        SCENARIO_CONTEXTS,
        min(max(count, 1), len(SCENARIO_CONTEXTS)),
    )

    plan: list[dict] = []
    for index in range(max(count, 1)):
        question_type = question_types[index % len(question_types)] if question_types else "single_choice"
        if question_type == "fill_blank" and keywords:
            topic = keywords[index % len(keywords)]
        elif question_type == "true_false":
            topic = evidence_candidates[index % len(evidence_candidates)]
        else:
            topic = topic_candidates[index % len(topic_candidates)]
        evidence = evidence_candidates[index % len(evidence_candidates)]
        style = selected_styles[index % len(selected_styles)]
        scenario = selected_contexts[index % len(selected_contexts)]
        base_tags = _dedupe_text_items(
            [topic]
            + keywords[:3]
            + ([title] if title else [])
        )
        knowledge_tags = base_tags[:3] or [_summarize_knowledge_point(topic)]
        dimension = classify_dimension(" ".join([topic, evidence]), knowledge_tags)

        plan.append(
            {
                "knowledge_point": _summarize_knowledge_point(topic),
                "evidence": evidence[:120],
                "question_type": question_type,
                "stem_style": style["name"],
                "scenario": scenario,
                "answer_focus": evidence[:80],
                "distractor_focus": f"围绕“{_summarize_knowledge_point(topic)}”设计常见误解或边界条件",
                "knowledge_tags": knowledge_tags,
                "dimension": dimension,
            }
        )

    return plan[:count]


def _build_question_plan_section(question_plan: Optional[list[dict]]) -> str:
    if not question_plan:
        return ""

    lines = [
        "",
        "",
        "【知识点出题规划】",
        "请严格按照以下规划逐题生成，每条规划最多对应1道题，不要遗漏、合并或改题型：",
    ]
    for index, item in enumerate(question_plan, start=1):
        tags = "、".join(item.get("knowledge_tags") or [])
        lines.append(f"{index}. 知识点：{item.get('knowledge_point', '')}")
        lines.append(f"   - 证据锚点：{item.get('evidence', '')}")
        lines.append(f"   - 题型：{TYPE_LABELS.get(item.get('question_type', ''), item.get('question_type', ''))}")
        lines.append(f"   - 推荐风格：{item.get('stem_style', '')}")
        lines.append(f"   - 推荐场景：{item.get('scenario', '')}")
        lines.append(f"   - 正确答案聚焦：{item.get('answer_focus', '')}")
        lines.append(f"   - 干扰项设计：{item.get('distractor_focus', '')}")
        lines.append(f"   - 建议标签：{tags}")
        lines.append(f"   - 建议维度：{item.get('dimension', '')}")
    return "\n".join(lines)


def _build_question_response_format(count: int, question_types: list[str]) -> dict:
    normalized_types = [
        question_type
        for question_type in dict.fromkeys(question_types)
        if question_type in VALID_TYPES
    ] or ["single_choice"]
    item_schemas = [_build_question_item_schema(question_type) for question_type in normalized_types]
    question_item_schema = item_schemas[0] if len(item_schemas) == 1 else {"oneOf": item_schemas}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"generated_questions_{'_'.join(normalized_types)}",
            "strict": False,
            "schema": {
                "type": "array",
                "items": question_item_schema,
                "minItems": 1,
                "maxItems": max(count, 1),
            },
        },
    }


def _build_question_plan_response_format(count: int) -> dict:
    plan_item_schema = {
        "type": "object",
        "required": [
            "knowledge_point",
            "evidence",
            "question_type",
            "stem_style",
            "scenario",
            "answer_focus",
            "distractor_focus",
            "knowledge_tags",
            "dimension",
        ],
        "additionalProperties": True,
        "properties": {
            "knowledge_point": {"type": "string"},
            "evidence": {"type": "string"},
            "question_type": {"type": "string", "enum": sorted(VALID_TYPES)},
            "stem_style": {"type": "string"},
            "scenario": {"type": "string"},
            "answer_focus": {"type": "string"},
            "distractor_focus": {"type": "string"},
            "knowledge_tags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "dimension": {"type": "string", "enum": FIVE_DIMENSIONS},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "question_plan",
            "strict": False,
            "schema": {
                "type": "array",
                "items": plan_item_schema,
                "minItems": 1,
                "maxItems": max(count, 1),
            },
        },
    }


def _supports_structured_output(model_config: ModelConfig) -> bool:
    base_url = (resolve_base_url(model_config) or "").lower()
    if model_config.slug == "local_qwen":
        return False
    return not any(token in base_url for token in STRUCTURED_OUTPUT_UNSUPPORTED_HOSTS)


def _should_retry_without_structured_output(exc: Exception) -> bool:
    message = str(exc).lower()
    retry_markers = (
        "response_format",
        "json_schema",
        "structured output",
        "schema",
        "invalid parameter",
        "unsupported",
        "not support",
        "not supported",
        "json mode",
    )
    return any(marker in message for marker in retry_markers)


def _extract_question_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("questions"), list):
            return payload["questions"]
        return [payload]
    return [payload] if payload is not None else []


def _sum_usage(*usages: Optional[dict]) -> dict:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for usage in usages:
        if not usage:
            continue
        for key in total:
            total[key] += int(usage.get(key, 0) or 0)
    return total


def _normalize_question_plan_item(
    raw: object,
    question_types: list[str],
    fallback_item: dict,
) -> dict:
    if not isinstance(raw, dict):
        return dict(fallback_item)

    normalized = dict(fallback_item)
    question_type = raw.get("question_type")
    if question_type in LABEL_TO_TYPE:
        question_type = LABEL_TO_TYPE[question_type]
    if question_type in VALID_TYPES and question_type in set(question_types):
        normalized["question_type"] = question_type

    for field in (
        "knowledge_point",
        "evidence",
        "stem_style",
        "scenario",
        "answer_focus",
        "distractor_focus",
    ):
        value = str(raw.get(field, "") or "").strip()
        if value:
            normalized[field] = value

    tags = raw.get("knowledge_tags")
    if isinstance(tags, str):
        tags = [tag.strip() for tag in re.split(r"[,，、;；]", tags) if tag.strip()]
    if isinstance(tags, list):
        normalized["knowledge_tags"] = [
            str(tag).strip() for tag in tags if str(tag).strip()
        ][:3] or normalized["knowledge_tags"]

    dimension = raw.get("dimension")
    if dimension in FIVE_DIMENSIONS:
        normalized["dimension"] = dimension
    else:
        normalized["dimension"] = classify_dimension(
            " ".join(
                [
                    normalized.get("knowledge_point", ""),
                    normalized.get("evidence", ""),
                ]
            ),
            normalized.get("knowledge_tags"),
        )

    return normalized


def _build_question_plan_user_prompt(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> str:
    type_labels = "、".join(TYPE_LABELS.get(item, item) for item in question_types)
    bloom_text = BLOOM_LABELS.get(bloom_level, bloom_level or "不限")
    extra = f"\n【额外要求】\n{custom_prompt}" if custom_prompt else ""
    return (
        f"请先完成出题规划，不要直接生成题目。\n"
        f"目标题量：{count} 道\n"
        f"允许题型：{type_labels}\n"
        f"难度：{difficulty}/5\n"
        f"布鲁姆层级：{bloom_text}\n"
        "请围绕素材中最有价值、最适合考查的知识点，输出一个 JSON 数组，每个元素表示 1 道题的规划。\n"
        "每条规划必须包含：knowledge_point、evidence、question_type、stem_style、scenario、answer_focus、distractor_focus、knowledge_tags、dimension。\n"
        "要求：\n"
        "1. 不得重复知识点；\n"
        "2. evidence 必须是素材中的证据句或高保真摘要；\n"
        "3. question_type 只能从允许题型中选择；\n"
        "4. dimension 必须是五个 AI 素养维度之一；\n"
        "5. knowledge_tags 必须是简洁的字符串数组；\n"
        "6. 不要输出题干、选项和答案，只输出规划。\n"
        f"{_build_plan_type_requirements(question_types)}\n"
        f"{extra}\n\n"
        f"{content or '【出题范围】AI素养通识知识'}"
    )


def generate_question_plan_via_llm(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
) -> dict:
    fallback_plan = build_question_plan(
        content=content,
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
        prompt_seed=prompt_seed,
    )
    runtime_model = model_config or get_default_model_config()
    api_key = resolve_api_key(runtime_model)
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if not api_key or api_key == "your-api-key":
        return {
            "question_plan": fallback_plan,
            "usage": empty_usage,
            "fallback_used": True,
            "error": "LLM API key not configured",
        }

    try:
        response_data = _request_question_generation(
            runtime_model,
            api_key,
            "你是一名资深命题规划专家，负责先抽取可考知识点，再为后续出题生成严格的结构化规划。",
            _build_question_plan_user_prompt(
                content=content,
                question_types=question_types,
                count=count,
                difficulty=difficulty,
                bloom_level=bloom_level,
                custom_prompt=custom_prompt,
            ),
            max(2048, count * 300),
            count,
            empty_usage,
            response_format=_build_question_plan_response_format(count),
            temperature=0.2,
        )
        raw = extract_json_text(response_data["content"])
        plan_items = json.loads(raw)
        if not isinstance(plan_items, list):
            plan_items = [plan_items]

        normalized: list[dict] = []
        for index, fallback_item in enumerate(fallback_plan):
            raw_item = plan_items[index] if index < len(plan_items) else None
            normalized.append(
                _normalize_question_plan_item(
                    raw_item,
                    question_types,
                    fallback_item,
                )
            )

        return {
            "question_plan": normalized[:count],
            "usage": response_data["usage"],
            "fallback_used": False,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Question planning via LLM failed, falling back to deterministic plan: %s", exc)
        return {
            "question_plan": fallback_plan,
            "usage": empty_usage,
            "fallback_used": True,
            "error": str(exc),
        }


def build_question_prompt_context(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    prompt_seed: Optional[int] = None,
    question_plan: Optional[list[dict]] = None,
    retry_feedback: Optional[str] = None,
) -> dict[str, str]:
    """Build prompt context for question generation with diversity and quality instructions."""
    rng = _build_prompt_rng(
        {
            "content": content,
            "question_types": question_types,
            "count": count,
            "difficulty": difficulty,
            "bloom_level": bloom_level,
            "custom_prompt": custom_prompt,
            "stage": "question_prompt",
        },
        prompt_seed,
    )

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
    selected_styles = rng.sample(QUESTION_STEM_STYLES, min(num_styles, len(QUESTION_STEM_STYLES)))
    style_instructions = []
    for i, style in enumerate(selected_styles, 1):
        style_instructions.append(
            f"  {i}. {style['name']}：{style['description']}（参考：{style['example_pattern']}）"
        )
    style_section = "\n".join(style_instructions)

    # ── 随机选择情境上下文 ──
    num_contexts = min(3, count)
    selected_contexts = rng.sample(SCENARIO_CONTEXTS, min(num_contexts, len(SCENARIO_CONTEXTS)))
    context_section = "、".join(selected_contexts)

    # ── 额外要求 ──
    custom_requirement_parts: list[str] = []
    if custom_prompt:
        custom_requirement_parts.append(f"【额外要求】\n{custom_prompt}")
    if retry_feedback:
        custom_requirement_parts.append(f"【上次输出问题——本次必须修正】\n{retry_feedback}")
    custom_requirements = ""
    if custom_requirement_parts:
        custom_requirements = "\n\n" + "\n\n".join(custom_requirement_parts)

    # ── 内容区 ──
    if content:
        content_section = f"""

【参考素材】（请严格以下述素材为出题基础）
{content}

【素材出题规则——必须遵守】
1. **只从素材中选取知识点**：所有题目必须围绕素材中出现的概念、原理、观点、案例来出题
2. **禁止考查篇章结构**：不得以素材的章节标题、目录结构、作者姓名、书名、出版信息等作为考查内容
3. **考查内容理解而非形式记忆**：题目应考查对素材中知识点的理解和应用，而非对原文措辞的死记硬背
4. **深入挖掘核心知识点**：识别素材中的核心概念、关键定义、重要原理，围绕这些设计题目
5. **干扰项设计**：基于对素材中概念的常见误解来设计干扰项，确保每个干扰项都有迷惑性
6. **不要超出素材范围**：不要引入素材中未提及的专业知识作为正确答案
7. **禁止素材元信息表述**：题目中禁止出现书名、作者、出版信息、章节编号、素材专有隐喻，以及“结合素材”“根据本文”“根据材料”等表述
8. **同套题禁止重复知识点**：同一套题中，每道题必须考查不同知识点，禁止重复知识点或仅换一种说法重复设问
9. **角色控制**："一位……"开头的题干最多只能出现2题，且职业角色不能重复
10. **判断题格式固定**：判断题题干必须是陈述句，禁止使用疑问句；选项只能有且仅有 A.正确 / B.错误
11. **生成后必须先自检**：请先自检判断题格式、素材元信息、乱码残留、知识点重复、角色重复；若任一项不合格，必须直接重新生成整套题"""
    else:
        # 随机选取主题子集，增加直接出题的多样性
        num_topics = min(3, len(DIRECT_GENERATION_TOPICS))
        selected_topics = rng.sample(DIRECT_GENERATION_TOPICS, num_topics)
        topic_lines = []
        for t in selected_topics:
            topic_lines.append(f"  - {t['theme']}：{t['keywords']}")
        topic_section = "\n".join(topic_lines)

        # 随机选取语气风格
        voice_style = rng.choice(QUESTION_VOICE_STYLES)

        content_section = f"""

【出题范围】
请基于AI素养领域的专业知识出题，涵盖以下维度（均匀分布）：
- AI基础知识（机器学习原理、深度学习、算法基础、数据处理）
- AI技术应用（NLP、计算机视觉、推荐系统、大语言模型、AIGC）
- AI伦理安全（隐私保护、算法偏见、数据安全、负责任AI）
- AI批判思维（信息辨别、AI局限性认知、证据评估、逻辑推理）
- AI创新实践（提示工程、AI工具使用、工作流自动化、方案设计）

【本次推荐出题主题】（请优先围绕这些主题出题，但不限于此）
{topic_section}

【本次推荐题干风格】
{voice_style}
请尽量让每道题采用不同的表达方式和切入角度，避免题干开头和句式雷同。"""

    # ── 随机选取出题视角 ──
    voice_style = rng.choice(QUESTION_VOICE_STYLES)

    # ── 组合多样性要求 ──
    type_rule_section = _build_type_rule_section(question_types)
    diversity_rules = f"""

【多样性与质量要求——核心规则】
1. **题型约束优先**——所有语言多样化、情境包装和风格变化都必须服从题型硬约束；若冲突，以题型硬约束为准。
2. **语言多样化**——在不违反题型硬约束的前提下，每道题的题干应尽量使用不同的句式和表达方式：
   - 本次推荐视角：{voice_style}
   - 严禁多道题使用相同的句式开头（如全都用"以下关于..."或"以下哪项..."）
   - 每道题的语言风格和切入角度要有变化
3. **题目风格混合**——请在以下推荐风格中选择并混合使用：
{style_section}
4. **情境多样**——题目场景应涉及：{context_section}；但若题型更适合直接陈述或术语填空，应优先保证格式正确
5. **正确答案随机分布**——{count}道题中，选择题正确答案应尽量分布在不同选项位置（ABCD），不能全部相同
6. **知识点覆盖**——每道题应考查不同的知识点或从不同角度考查，避免重复
7. **干扰项质量**——每个干扰项都应对应一种常见误解，具有足够迷惑性
8. **答案简明**——correct_answer（主观题除外）和explanation应简洁明了{type_rule_section}"""

    return {
        "count": str(count),
        "question_types": type_str,
        "difficulty_section": difficulty_section,
        "bloom_section": bloom_section,
        "diversity_rules": diversity_rules,
        "question_plan_section": _build_question_plan_section(question_plan),
        "content_section": content_section,
        "custom_requirements": custom_requirements,
    }


def _build_user_prompt(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    prompt_seed: Optional[int] = None,
    user_prompt_template: Optional[str] = None,
    question_plan: Optional[list[dict]] = None,
    retry_feedback: Optional[str] = None,
) -> str:
    context = build_question_prompt_context(
        content=content,
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
        prompt_seed=prompt_seed,
        question_plan=question_plan,
        retry_feedback=retry_feedback,
    )
    return render_user_prompt(
        user_prompt_template or DEFAULT_QUESTION_USER_PROMPT_TEMPLATE,
        context,
    )


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


def _validate_and_fix_question(
    raw: dict,
    requested_types: list[str],
    rejection_reasons: Optional[list[str]] = None,
) -> Optional[dict]:
    """校验并修复单道题目，返回 None 表示该题无法修复应丢弃。"""
    def reject(reason: str) -> None:
        if rejection_reasons is not None:
            rejection_reasons.append(reason)

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
        reject("题干缺失或过短")
        return None
    raw["stem"] = stem.strip()

    correct_answer = raw.get("correct_answer", "")
    if not correct_answer:
        logger.warning(f"题目缺少 correct_answer，已丢弃: {stem[:30]}")
        reject("缺少正确答案")
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
                reject("缺少有效选项")
                return None
        options = _normalize_options_keys(options)
        # 确保至少有2个选项
        if len(options) < 2:
            logger.warning(f"选项数量不足，已丢弃: {stem[:30]}")
            reject("选项数量不足")
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
                logger.warning(
                    f"单选题答案 '{correct_answer}' 不在选项中，已丢弃: {stem[:30]}"
                )
                reject("单选题答案未落在选项内")
                return None

    if qt == "multiple_choice" and raw.get("options"):
        valid_keys = set(raw["options"].keys())
        answer_keys = set(raw["correct_answer"])
        if not answer_keys.issubset(valid_keys):
            logger.warning(
                f"多选题答案 '{raw['correct_answer']}' 包含无效选项: {stem[:30]}"
            )
            fixed = "".join(sorted(answer_keys & valid_keys))
            if len(fixed) < 2:
                reject("多选题答案无效")
                return None
            raw["correct_answer"] = fixed

    if qt == "true_false" and raw["correct_answer"] not in ("A", "B"):
        logger.warning(f"判断题答案 '{correct_answer}' 非法，已丢弃: {stem[:30]}")
        reject("判断题答案必须为 A 或 B")
        return None

    if qt == "true_false":
        if not _looks_like_true_false_statement(raw["stem"]):
            logger.warning(f"判断题题干不是陈述句，已丢弃: {stem[:30]}")
            reject("判断题题干必须是陈述句且不得包含问号或疑问表达")
            return None
        if raw.get("options") != {"A": "正确", "B": "错误"}:
            logger.warning(f"判断题选项非标准格式，已丢弃: {stem[:30]}")
            reject("判断题选项必须严格为 A.正确 / B.错误")
            return None

    if qt == "fill_blank":
        if not _has_blank_marker(raw["stem"]):
            logger.warning(f"填空题缺少空位标记，已丢弃: {stem[:30]}")
            reject("填空题题干必须包含明确空位标记")
            return None
        if raw.get("options") is not None:
            logger.warning(f"填空题包含非法 options，已丢弃: {stem[:30]}")
            reject("填空题不应包含选项")
            return None
        if len(raw["correct_answer"]) > 48:
            logger.warning(f"填空题答案过长，已丢弃: {stem[:30]}")
            reject("填空题答案过长，更适合改为简答题")
            return None

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


def _build_generation_retry_feedback(
    question_types: list[str],
    rejection_reasons: list[str],
    generated_count: int,
    target_count: int,
) -> str:
    unique_reasons = list(dict.fromkeys(reason.strip() for reason in rejection_reasons if reason.strip()))
    lines = [
        f"本次只生成了 {generated_count} / {target_count} 道有效题目，必须补齐。",
    ]
    if unique_reasons:
        lines.append("上次输出中最常见的问题如下，请逐条修正：")
        for index, reason in enumerate(unique_reasons[:5], start=1):
            lines.append(f"{index}. {reason}")
    if set(question_types) & STRICT_FORMAT_TYPES:
        lines.append("本次不得为了语言变化破坏题型格式；若知识点不适合当前题型，请改换更合适的知识点。")
    return "\n".join(lines)


def _question_field(question: object, field: str, default=None):
    if isinstance(question, dict):
        return question.get(field, default)
    return getattr(question, field, default)


def _normalize_text_for_compare(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？；：、“”‘’\"'（）()、,.!?;:\-_/]", "", text)
    return text


def _contains_material_reference(text: str) -> bool:
    if not text:
        return False
    if any(token in text for token in FORBIDDEN_MATERIAL_REFERENCES):
        return True
    return any(pattern.search(text) for pattern in FORBIDDEN_MATERIAL_REGEXES)


def _contains_garbled_text(text: str) -> bool:
    if not text:
        return False
    if any(marker in text for marker in GARBLED_TEXT_MARKERS):
        return True
    return bool(re.search(r"[\uFFFD\uFFFE\uFFFF]", text))


def _extract_role_from_stem(stem: str) -> Optional[str]:
    if not stem or not stem.startswith("一位"):
        return None
    match = re.match(
        r"^一位([^，。；、：:\s]{1,12}?)(?:在|正|准备|计划|希望|想|将|要|负责|面对|使用|需要|为了|进行|参与)",
        stem,
    )
    if match:
        return match.group(1)

    fallback = re.match(r"^一位([^，。；、：:\s]{1,12})", stem)
    return fallback.group(1) if fallback else None


def _knowledge_signature(question: object) -> str:
    tags = _question_field(question, "knowledge_tags") or []
    if isinstance(tags, str):
        tags = [tags]
    normalized_tags = sorted(_normalize_text_for_compare(str(tag)) for tag in tags if str(tag).strip())
    if normalized_tags:
        return "|".join(normalized_tags)
    return _normalize_text_for_compare(_question_field(question, "stem", ""))


def _stem_opening_signature(stem: str) -> str:
    if not stem:
        return ""
    return _normalize_text_for_compare(stem)[:12]


def _validate_generated_question_set(
    questions: list[object],
    strict_material_rules: bool = False,
) -> dict:
    """Validate a generated question set and return pass/fail with reasons."""
    if not questions:
        return {"passed": False, "reasons": ["未生成任何题目"]}
    if not strict_material_rules:
        return {"passed": True, "reasons": []}

    reasons: list[str] = []
    seen_signatures: dict[str, int] = {}
    seen_roles: dict[str, int] = {}
    seen_openings: dict[str, int] = {}
    role_lead_count = 0
    single_choice_answers: list[str] = []
    true_false_answers: list[str] = []

    for index, question in enumerate(questions, start=1):
        stem = str(_question_field(question, "stem", "") or "")
        explanation = str(_question_field(question, "explanation", "") or "")
        options = _question_field(question, "options") or {}
        combined_text = " ".join(
            [
                stem,
                explanation,
                " ".join(str(v) for v in options.values()) if isinstance(options, dict) else "",
                " ".join(str(t) for t in (_question_field(question, "knowledge_tags") or [])),
            ]
        )

        if _contains_material_reference(combined_text):
            reasons.append(f"第{index}题包含素材元信息或禁用表述")

        if _contains_garbled_text(combined_text):
            reasons.append(f"第{index}题存在乱码残留")

        signature = _knowledge_signature(question)
        if signature:
            if signature in seen_signatures:
                reasons.append(
                    f"第{index}题与第{seen_signatures[signature]}题知识点重复"
                )
            else:
                seen_signatures[signature] = index

        opening = _stem_opening_signature(stem)
        if opening:
            if opening in seen_openings:
                reasons.append(
                    f"第{index}题与第{seen_openings[opening]}题题干开头过于相似"
                )
            else:
                seen_openings[opening] = index

        if stem.startswith("一位"):
            role_lead_count += 1
            if role_lead_count > MAX_ROLE_LEAD_STEMS:
                reasons.append("同套题以“一位……”开头的题干超过2题")

            role = _extract_role_from_stem(stem)
            if role:
                if role in seen_roles:
                    reasons.append(
                        f"第{index}题与第{seen_roles[role]}题职业角色重复"
                    )
                else:
                    seen_roles[role] = index

        question_type = _question_field(question, "question_type")
        answer = str(_question_field(question, "correct_answer", "") or "")
        if question_type == "single_choice":
            single_choice_answers.append(answer)
        if question_type == "true_false":
            true_false_answers.append(answer)

        if question_type == "true_false":
            if "?" in stem or "？" in stem:
                reasons.append(f"第{index}题判断题题干必须是陈述句")
            if options != {"A": "正确", "B": "错误"}:
                reasons.append(f"第{index}题判断题选项必须严格为A.正确/B.错误")

    if len(single_choice_answers) >= 3 and len(set(single_choice_answers)) == 1:
        reasons.append("同套单选题正确答案位置全部相同")
    if len(true_false_answers) >= 3 and len(set(true_false_answers)) == 1:
        reasons.append("同套判断题答案全部相同")

    deduped_reasons = list(dict.fromkeys(reasons))
    return {"passed": not deduped_reasons, "reasons": deduped_reasons}


# ── 主入口 ──────────────────────────────────────────────────────────

def generate_questions_via_llm(
    content: str,
    question_types: list[str],
    count: int = 3,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
    prompt_seed: Optional[int] = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> dict:
    """Generate questions using LLM API.

    Returns dict with 'questions' (list of validated question dicts) and
    'usage' (token usage dict with prompt_tokens, completion_tokens, total_tokens).
    Falls back to templates on failure.
    """
    _empty_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    runtime_model = model_config or get_default_model_config()
    api_key = resolve_api_key(runtime_model)
    planner_result = generate_question_plan_via_llm(
        content=content,
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
        model_config=runtime_model,
        prompt_seed=prompt_seed,
    )
    question_plan = planner_result["question_plan"]

    if not api_key or api_key == "your-api-key":
        logger.warning("LLM API key not configured, using template fallback")
        return _build_fallback_generation_result(
            content,
            question_types,
            count,
            difficulty,
            bloom_level,
            _sum_usage(_empty_usage, planner_result.get("usage")),
            runtime_model,
            "LLM API key not configured",
            question_plan=question_plan,
            planner_fallback_used=planner_result.get("fallback_used", False),
            planner_error=planner_result.get("error"),
        )

    runtime_system_prompt = system_prompt or DEFAULT_QUESTION_SYSTEM_PROMPT
    max_tokens = max(4096, count * 600)
    generation_usage = dict(_empty_usage)
    retry_feedback: Optional[str] = None
    last_error: Optional[str] = None
    best_validated: list[dict] = []
    max_attempts = QUESTION_GENERATION_RETRY_LIMIT if set(question_types) & STRICT_FORMAT_TYPES else 1

    for attempt in range(1, max_attempts + 1):
        raw = ""
        try:
            user_prompt = _build_user_prompt(
                content,
                question_types,
                count,
                difficulty,
                bloom_level,
                custom_prompt,
                prompt_seed=prompt_seed,
                user_prompt_template=user_prompt_template,
                question_plan=question_plan,
                retry_feedback=retry_feedback,
            )
            response_data = _request_question_generation(
                runtime_model,
                api_key,
                runtime_system_prompt,
                user_prompt,
                max_tokens,
                count,
                _empty_usage,
                response_format=_build_question_response_format(count, question_types),
                temperature=0.4,
            )
            generation_usage = _sum_usage(generation_usage, response_data["usage"])
            raw = extract_json_text(response_data["content"])
            questions = _extract_question_payload(json.loads(raw))

            validated: list[dict] = []
            rejection_reasons: list[str] = []
            for q in questions:
                fixed = _validate_and_fix_question(q, question_types, rejection_reasons)
                if fixed is not None:
                    validated.append(fixed)

            if validated:
                best_validated = validated[:count]
            if len(validated) >= count:
                return {
                    "questions": validated[:count],
                    "usage": _sum_usage(planner_result.get("usage"), generation_usage),
                    "model_name": runtime_model.model_name,
                    "provider": runtime_model.provider,
                    "fallback_used": False,
                    "error": None,
                    "question_plan": question_plan,
                    "planner_fallback_used": planner_result.get("fallback_used", False),
                    "planner_error": planner_result.get("error"),
                }

            last_error = (
                f"Only {len(validated)}/{count} questions passed validation"
            )
            if rejection_reasons:
                last_error = f"{last_error}: {'; '.join(dict.fromkeys(rejection_reasons))}"

            if attempt < max_attempts:
                retry_feedback = _build_generation_retry_feedback(
                    question_types,
                    rejection_reasons,
                    len(validated),
                    count,
                )
                logger.warning(
                    "Question generation attempt %s/%s produced only %s/%s valid questions, retrying: %s",
                    attempt,
                    max_attempts,
                    len(validated),
                    count,
                    "; ".join(dict.fromkeys(rejection_reasons[:3])) or "insufficient valid items",
                )
                continue

        except json.JSONDecodeError as exc:
            last_error = f"Invalid JSON: {exc}"
            logger.error(
                "LLM output is not valid JSON on attempt %s/%s: %s\nRaw output (first 500 chars): %s",
                attempt,
                max_attempts,
                exc,
                raw[:500] if raw else "EMPTY",
            )
            if attempt < max_attempts:
                retry_feedback = _build_generation_retry_feedback(
                    question_types,
                    ["输出必须是纯 JSON 数组，不能包含多余文本或多个 JSON 片段"],
                    0,
                    count,
                )
                continue
        except Exception as exc:
            last_error = str(exc)
            logger.error("LLM question generation failed on attempt %s/%s: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                retry_feedback = _build_generation_retry_feedback(
                    question_types,
                    [str(exc)],
                    len(best_validated),
                    count,
                )
                continue

    total_usage = _sum_usage(planner_result.get("usage"), generation_usage)
    if best_validated:
        return {
            "questions": best_validated[:count],
            "usage": total_usage,
            "model_name": runtime_model.model_name,
            "provider": runtime_model.provider,
            "fallback_used": False,
            "error": last_error,
            "question_plan": question_plan,
            "planner_fallback_used": planner_result.get("fallback_used", False),
            "planner_error": planner_result.get("error"),
        }

    logger.warning("LLM output passed 0 validation, falling back to template")
    return _build_fallback_generation_result(
        content,
        question_types,
        count,
        difficulty,
        bloom_level,
        total_usage,
        runtime_model,
        last_error or "LLM output passed 0 validation",
        question_plan=question_plan,
        planner_fallback_used=planner_result.get("fallback_used", False),
        planner_error=planner_result.get("error"),
    )


def _build_fallback_generation_result(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str],
    usage: dict,
    runtime_model: ModelConfig,
    error_message: str,
    question_plan: Optional[list[dict]] = None,
    planner_fallback_used: bool = False,
    planner_error: Optional[str] = None,
) -> dict:
    return {
        "questions": _template_fallback(content, question_types, count, difficulty, bloom_level),
        "usage": usage,
        "model_name": runtime_model.model_name,
        "provider": runtime_model.provider,
        "fallback_used": True,
        "error": error_message,
        "question_plan": question_plan or [],
        "planner_fallback_used": planner_fallback_used,
        "planner_error": planner_error,
    }


def _request_question_generation(
    model_config: ModelConfig,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    count: int,
    empty_usage: dict,
    response_format: Optional[dict] = None,
    temperature: float = 0.4,
) -> dict:
    """Dispatch question generation to the right provider."""
    return _request_question_generation_openai_compatible(
        model_config,
        api_key,
        system_prompt,
        user_prompt,
        max_tokens,
        count,
        empty_usage,
        response_format=response_format,
        temperature=temperature,
    )


def _request_question_generation_openai_compatible(
    model_config: ModelConfig,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    count: int,
    empty_usage: dict,
    response_format: Optional[dict] = None,
    temperature: float = 0.4,
) -> dict:
    client = OpenAI(
        api_key=api_key,
        base_url=resolve_base_url(model_config),
        timeout=Timeout(600.0, connect=10.0),
    )

    request_kwargs = {
        "model": model_config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    extra_body = build_disable_thinking_extra_body(
        model_config.model_name,
        resolve_base_url(model_config),
        model_config.slug,
    )
    if extra_body:
        request_kwargs["extra_body"] = extra_body
    if response_format and _supports_structured_output(model_config):
        request_kwargs["response_format"] = response_format

    try:
        response = client.chat.completions.create(
            **request_kwargs,
        )
    except Exception as exc:
        if request_kwargs.get("response_format") and _should_retry_without_structured_output(exc):
            logger.warning(
                "Structured output unsupported for model %s, retrying without response_format: %s",
                model_config.model_name,
                exc,
            )
            request_kwargs.pop("response_format", None)
            response = client.chat.completions.create(
                **request_kwargs,
            )
        else:
            raise

    usage = empty_usage
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens or 0,
            "completion_tokens": response.usage.completion_tokens or 0,
            "total_tokens": response.usage.total_tokens or 0,
        }

    return {
        "content": response.choices[0].message.content.strip(),
        "usage": usage,
    }


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
