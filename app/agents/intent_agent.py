"""Intent recognition agent for intelligent test assembly.

Parses natural language descriptions like '给新员工出一份20题的入门测试'
into structured exam assembly parameters.
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.core.llm_config import get_llm_config_sync, make_openai_client

logger = logging.getLogger(__name__)

# Known dimensions for matching
KNOWN_DIMENSIONS = [
    "AI基础", "AI伦理", "AI技术", "AI应用", "AI安全",
    "机器学习", "深度学习", "自然语言处理", "计算机视觉",
    "数据科学", "数据分析", "编程基础", "算法",
]

# Difficulty keywords mapping
DIFFICULTY_KEYWORDS = {
    "入门": 1, "基础": 1, "初级": 1, "简单": 1, "容易": 1,
    "初阶": 2, "一般": 2, "普通": 2,
    "中等": 3, "中级": 3, "适中": 3,
    "高级": 4, "进阶": 4, "较难": 4,
    "专家": 5, "困难": 5, "高阶": 5, "难": 5,
}

# Question type keywords mapping
QTYPE_KEYWORDS = {
    "单选": "single_choice", "选择题": "single_choice", "选择": "single_choice",
    "多选": "multiple_choice", "多项选择": "multiple_choice",
    "判断": "true_false", "判断题": "true_false", "对错": "true_false",
    "填空": "fill_blank", "填空题": "fill_blank",
    "简答": "short_answer", "简答题": "short_answer", "问答": "short_answer",
}

SYSTEM_PROMPT = """你是一个智能组卷参数解析器。根据用户的自然语言描述，提取出组卷参数。

你需要从描述中提取以下参数：
1. title: 试卷标题（如果用户没有明确说明，根据描述生成一个合适的标题）
2. total_questions: 总题目数量（默认10）
3. difficulty: 难度等级1-5（1=入门, 2=初阶, 3=中等, 4=高级, 5=专家，默认3）
4. time_limit_minutes: 考试时长（分钟，可选）
5. dimensions: 知识维度列表（可选，如["AI基础","AI伦理"]）
6. type_distribution: 题型分布，如{"single_choice": 10, "true_false": 5}
   - 支持的题型: single_choice, multiple_choice, true_false, fill_blank, short_answer
   - 如果用户没有指定题型，默认全部为single_choice
7. score_per_question: 每题分数（默认5）
8. description: 试卷描述（根据输入生成）

请严格以JSON格式输出，不要添加任何其他内容。

输出示例：
```json
{
  "title": "新员工AI素养入门测试",
  "total_questions": 20,
  "difficulty": 1,
  "time_limit_minutes": 30,
  "dimensions": ["AI基础"],
  "type_distribution": {"single_choice": 15, "true_false": 5},
  "score_per_question": 5,
  "description": "面向新入职员工的AI基础知识入门测试"
}
```"""


def parse_intent_via_llm(description: str) -> dict:
    """Use LLM to parse natural language intent into structured parameters."""
    _cfg = get_llm_config_sync("question_generation")
    if _cfg.api_key == "your-api-key":
        logger.info("LLM API key not configured, using rule-based parsing")
        return _rule_based_parse(description)

    try:
        client = make_openai_client(_cfg)
        response = client.chat.completions.create(
            model=_cfg.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()

        # Extract JSON from potential markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        result = json.loads(content)
        return _validate_and_normalize(result, description)

    except Exception as e:
        logger.warning(f"LLM intent parsing failed: {e}, falling back to rule-based")
        return _rule_based_parse(description)


def _rule_based_parse(description: str) -> dict:
    """Rule-based fallback for intent parsing using keyword matching."""
    result = {
        "title": "",
        "total_questions": 10,
        "difficulty": 3,
        "time_limit_minutes": None,
        "dimensions": None,
        "type_distribution": {},
        "score_per_question": 5.0,
        "description": description,
    }

    # Extract question count
    count_patterns = [
        r'(\d+)\s*(?:题|道|个题|道题|个问题)',
        r'(?:题目|问题)\s*(?:数量|数)\s*(?:为|是|：|:)\s*(\d+)',
    ]
    for pattern in count_patterns:
        match = re.search(pattern, description)
        if match:
            result["total_questions"] = int(match.group(1))
            break

    # Extract time limit
    time_patterns = [
        r'(\d+)\s*(?:分钟|min)',
        r'(?:时间|时长|限时)\s*(?:为|是|：|:)?\s*(\d+)',
    ]
    for pattern in time_patterns:
        match = re.search(pattern, description)
        if match:
            result["time_limit_minutes"] = int(match.group(1))
            break

    # Extract difficulty
    for keyword, level in DIFFICULTY_KEYWORDS.items():
        if keyword in description:
            result["difficulty"] = level
            break

    # Extract dimensions
    found_dims = []
    for dim in KNOWN_DIMENSIONS:
        if dim in description:
            found_dims.append(dim)
    if found_dims:
        result["dimensions"] = found_dims

    # Extract question types and their counts
    type_dist = {}
    for keyword, qtype in QTYPE_KEYWORDS.items():
        if keyword in description:
            # Check if there's a count before the keyword
            count_match = re.search(rf'(\d+)\s*(?:道|题|个)?\s*{keyword}', description)
            if count_match:
                type_dist[qtype] = int(count_match.group(1))
            elif qtype not in type_dist:
                type_dist[qtype] = 0  # Mark as present, count TBD

    # Distribute total questions across types
    if type_dist:
        specified_count = sum(v for v in type_dist.values() if v > 0)
        unspecified_types = [k for k, v in type_dist.items() if v == 0]
        remaining = result["total_questions"] - specified_count

        if unspecified_types and remaining > 0:
            per_type = remaining // len(unspecified_types)
            for t in unspecified_types:
                type_dist[t] = max(per_type, 1)
        elif not unspecified_types and specified_count > 0:
            result["total_questions"] = specified_count

        # Remove zero-count types
        type_dist = {k: v for k, v in type_dist.items() if v > 0}

    if not type_dist:
        type_dist = {"single_choice": result["total_questions"]}

    result["type_distribution"] = type_dist

    # Extract per-question score
    score_match = re.search(r'(?:每题|每道)\s*(\d+)\s*分', description)
    if score_match:
        result["score_per_question"] = float(score_match.group(1))

    # Generate title
    parts = []
    # Look for target audience
    audience_match = re.search(r'(?:给|为|面向)\s*([\u4e00-\u9fa5]+?)(?:出|做|准备|设计|生成)', description)
    if audience_match:
        parts.append(audience_match.group(1))

    diff_label = {1: "入门", 2: "初级", 3: "中级", 4: "高级", 5: "专家"}.get(result["difficulty"], "")
    if diff_label:
        parts.append(diff_label)

    if result["dimensions"]:
        parts.append("+".join(result["dimensions"][:2]))

    parts.append("测试")
    result["title"] = "".join(parts) if parts else f"自动组卷测试({result['total_questions']}题)"

    return result


def _validate_and_normalize(result: dict, original_description: str) -> dict:
    """Validate and normalize LLM output."""
    # Ensure required fields
    if "title" not in result or not result["title"]:
        result["title"] = f"智能组卷测试"

    if "total_questions" not in result or not isinstance(result.get("total_questions"), int):
        result["total_questions"] = 10

    result["total_questions"] = max(1, min(100, result["total_questions"]))

    if "difficulty" not in result or not isinstance(result.get("difficulty"), int):
        result["difficulty"] = 3
    result["difficulty"] = max(1, min(5, result["difficulty"]))

    if "time_limit_minutes" in result and result["time_limit_minutes"] is not None:
        result["time_limit_minutes"] = max(5, min(300, result["time_limit_minutes"]))

    if "dimensions" in result and result["dimensions"] is not None:
        if not isinstance(result["dimensions"], list):
            result["dimensions"] = None

    # Normalize type_distribution
    if "type_distribution" not in result or not isinstance(result.get("type_distribution"), dict):
        result["type_distribution"] = {"single_choice": result["total_questions"]}

    valid_types = {"single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"}
    result["type_distribution"] = {
        k: int(v) for k, v in result["type_distribution"].items()
        if k in valid_types and isinstance(v, (int, float)) and v > 0
    }
    if not result["type_distribution"]:
        result["type_distribution"] = {"single_choice": result["total_questions"]}

    if "score_per_question" not in result:
        result["score_per_question"] = 5.0
    result["score_per_question"] = float(result.get("score_per_question", 5.0))

    if "description" not in result:
        result["description"] = original_description

    return result
