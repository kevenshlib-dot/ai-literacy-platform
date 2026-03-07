"""Question generation agent - uses LLM to generate questions from knowledge units."""
import json
import logging
import re
from typing import Optional

from openai import OpenAI
from httpx import Timeout

from app.core.config import settings

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
你是一个专业的AI素养评测出题专家。请根据要求生成高质量的题目。

## 严格输出规范

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

## 关键规则（违反将导致输出无效）

1. **options 字段的键必须是大写字母 A/B/C/D**，不得使用中文键或数字键
2. **单选题 correct_answer** 只能是单个大写字母：A、B、C 或 D
3. **多选题 correct_answer** 是多个大写字母的拼接（按字母排序）：AB、AC、ABC、ABD、ACD、ABCD 等
4. **判断题 correct_answer** 只能是 A（正确）或 B（错误）
5. **填空题和简答题** 的 options 必须为 null
6. **explanation 必须提供**，不能为空
7. **stem 必须完整**，语句通顺，不能截断
8. **干扰项**必须具有合理性和迷惑性，不能一眼看出错误
9. 每道题的 knowledge_tags 必须是字符串数组
10. **dimension 必须是以下五个值之一**：AI基础知识、AI技术应用、AI伦理安全、AI批判思维、AI创新实践
11. 直接输出 JSON 数组，不要加 ```json 标记，不要加任何其他文字
"""


def _build_user_prompt(
    content: str,
    question_types: list[str],
    count: int,
    difficulty: int,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> str:
    """Build user prompt for question generation."""
    type_parts = []
    for t in question_types:
        label = TYPE_LABELS.get(t, t)
        type_parts.append(f"{label}({t})")
    type_str = "、".join(type_parts)

    bloom_str = ""
    if bloom_level and bloom_level in BLOOM_LABELS:
        bloom_str = f"\n- 认知层次：{BLOOM_LABELS[bloom_level]}（{bloom_level}）"
    custom_str = ""
    if custom_prompt:
        custom_str = f"\n- 额外要求：{custom_prompt}"

    difficulty_desc = {1: "入门", 2: "简单", 3: "中等", 4: "困难", 5: "专家"}
    diff_label = difficulty_desc.get(difficulty, "中等")

    content_section = (
        f"\n\n【知识内容】\n{content}"
        if content
        else "\n\n请基于AI素养领域的专业知识出题（涵盖AI基础知识、技术应用、伦理安全、批判思维、创新实践等维度）。"
    )

    return f"""请生成 {count} 道题目，严格遵守系统提示中的输出格式。

要求：
- 题型：{type_str}
- 难度：{difficulty}/5（{diff_label}）{bloom_str}{custom_str}
- 每道题必须包含 stem、correct_answer、explanation
- 选择题和判断题必须包含 options（键为 A/B/C/D）
- 直接输出 JSON 数组，不要包含任何其他文字{content_section}"""


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
    if settings.LLM_API_KEY == "your-api-key":
        logger.warning("LLM API key not configured, using template fallback")
        return _template_fallback(content, question_types, count, difficulty, bloom_level)

    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=Timeout(60.0, connect=10.0),
        )

        user_prompt = _build_user_prompt(
            content, question_types, count, difficulty, bloom_level, custom_prompt
        )

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
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

    Generates structurally correct questions from content sentences.
    """
    sentences = _extract_key_sentences(content)
    if not sentences:
        # 无有效句子时用通用AI素养题
        sentences = [
            "人工智能是计算机科学的一个分支，致力于创建能模拟人类智能的系统",
            "机器学习是AI的核心方法，通过数据驱动的方式让计算机自动学习",
            "深度学习使用多层神经网络来处理复杂的模式识别任务",
            "自然语言处理（NLP）使计算机能够理解和生成人类语言",
            "AI伦理关注人工智能技术的公平性、透明性和责任归属",
        ]

    questions = []
    for i in range(count):
        qtype = question_types[i % len(question_types)]
        sent = sentences[i % len(sentences)]

        dim = classify_dimension(sent)

        if qtype == "single_choice":
            q = {
                "question_type": "single_choice",
                "dimension": dim,
                "stem": f'关于"{sent}"，以下哪项理解最为准确？',
                "options": {
                    "A": f"{sent}，这体现了AI技术的核心特征",
                    "B": "该概念仅适用于传统计算机程序设计领域",
                    "C": "这一表述与人工智能发展方向相矛盾",
                    "D": "该技术已被完全淘汰，不再具有实际价值",
                },
                "correct_answer": "A",
                "explanation": f"该题基于知识点：{sent}。选项A正确反映了原文含义，其余选项为常见误解。",
                "knowledge_tags": ["AI素养", "基础概念"],
            }
        elif qtype == "multiple_choice":
            q = {
                "question_type": "multiple_choice",
                "dimension": dim,
                "stem": f'以下关于"{sent}"的说法，哪些是正确的？',
                "options": {
                    "A": "该概念是人工智能领域的重要组成部分",
                    "B": "理解该概念有助于提升AI素养水平",
                    "C": "该概念与计算机科学完全无关",
                    "D": "该概念已不再被学术界和产业界关注",
                },
                "correct_answer": "AB",
                "explanation": f"A和B正确。{sent}确实是AI领域的重要概念。C和D为错误表述。",
                "knowledge_tags": ["AI素养", "综合理解"],
            }
        elif qtype == "true_false":
            q = {
                "question_type": "true_false",
                "dimension": dim,
                "stem": f"{sent}。",
                "options": {"A": "正确", "B": "错误"},
                "correct_answer": "A",
                "explanation": f"该描述正确。{sent}是AI领域的基本事实。",
                "knowledge_tags": ["AI素养", "基础判断"],
            }
        elif qtype == "fill_blank":
            # 提取句子中的关键术语做填空
            words = re.findall(r"[\u4e00-\u9fa5A-Za-z]{2,6}", sent)
            blank_word = words[0] if words else "人工智能"
            stem_with_blank = sent.replace(blank_word, "____", 1)
            q = {
                "question_type": "fill_blank",
                "dimension": dim,
                "stem": f"请补全：{stem_with_blank}",
                "options": None,
                "correct_answer": blank_word,
                "explanation": f"完整表述为：{sent}。",
                "knowledge_tags": ["AI素养", "概念填空"],
            }
        else:  # short_answer, essay
            q = {
                "question_type": qtype,
                "dimension": dim,
                "stem": f'请结合所学知识，论述"{sent}"的含义及其在AI素养教育中的重要性。',
                "options": None,
                "correct_answer": (
                    f"{sent}。这一概念在AI素养教育中非常重要，"
                    "因为它帮助学习者建立对人工智能技术的基本认知框架。"
                ),
                "explanation": "答案应包含对核心概念的准确定义、在AI素养体系中的定位、以及对实际应用的分析。",
                "knowledge_tags": ["AI素养", "综合论述"],
            }

        questions.append(q)

    return questions
