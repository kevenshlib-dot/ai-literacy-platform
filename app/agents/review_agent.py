"""Review agent - AI-assisted quality validation of generated questions.

Performs red-team validation checks:
1. Stem clarity - Is the question stem clear and unambiguous?
2. Option quality - Are distractors plausible but clearly wrong?
3. Answer correctness - Is the marked answer actually correct?
4. Knowledge alignment - Does the question match its tagged dimension?
5. Difficulty calibration - Is the difficulty rating appropriate?
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.agents.llm_utils import strip_thinking_tags, build_disable_thinking_extra_body

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """你是一个专业的题目质量审核专家。你需要对题目进行全面的质量检查。

请从以下5个维度进行评估，每个维度给出1-5分的评分和简短评语：

1. **题干清晰度** (stem_clarity): 题干表述是否清晰、无歧义
2. **选项质量** (option_quality): 干扰项是否合理，是否有明显暗示
3. **答案正确性** (answer_correctness): 标注的正确答案是否确实正确
4. **知识对齐** (knowledge_alignment): 题目是否与标注的知识维度一致
5. **难度校准** (difficulty_calibration): 难度标注是否与题目实际难度匹配

审核时重点关注：
- 正确答案是否被题干或素材证据充分支持，避免把争议性表述写成唯一正确答案。
- 选择题的四个选项是否同层级、同粒度、可比较，干扰项是否围绕真实误解而非离题内容。
- `fill_blank` 是开放式填空题，不需要选项；`short_answer` 是开放式简答题，不得使用填空标记，也不需要选项；`true_false` 必须使用 T/F 两个标准选项。
- 若题目涉及“首位/公认/奠基/关键文献/提出者/起源”等唯一归属型表述，应重点检查事实依据是否充分。

请严格按照以下JSON格式输出：
```json
{
  "scores": {
    "stem_clarity": 4,
    "option_quality": 3,
    "answer_correctness": 5,
    "knowledge_alignment": 4,
    "difficulty_calibration": 3
  },
  "overall_score": 3.8,
  "recommendation": "approve",
  "comments": "总体评语..."
}
```

recommendation 取值：approve（建议通过，overall_score >= 3.5）、revise（建议修改，2.5-3.5）、reject（建议拒绝，< 2.5）
"""

BOOLEAN_TRUE_LABELS = {"正确", "对", "true", "是", "yes"}
BOOLEAN_FALSE_LABELS = {"错误", "错", "false", "否", "no"}
BLANK_MARKERS = ("____", "___", "（ ）", "( )", "（）", "【 】", "[]", "＿", "填空")
SHORT_ANSWER_HINTS = ("请", "说明", "分析", "简述", "解释", "论述", "阐述", "为什么", "如何", "结合")
ABSOLUTE_CLAIM_MARKERS = ("首位", "公认", "唯一", "首要", "第一位", "首次")


def _infer_review_risk_tags(
    *,
    stem: str,
    options: Optional[dict],
    correct_answer: str,
    explanation: Optional[str],
    question_type: str,
    scores: Optional[dict],
    comments: str,
) -> list[str]:
    scores = scores or {}
    comments_text = str(comments or "")
    tags: list[str] = []

    answer_score = float(scores.get("answer_correctness", 0) or 0)
    option_score = float(scores.get("option_quality", 0) or 0)
    difficulty_score = float(scores.get("difficulty_calibration", 0) or 0)
    has_absolute_claim = any(marker in str(stem or "") for marker in ABSOLUTE_CLAIM_MARKERS)

    if has_absolute_claim or answer_score <= 3 or any(token in comments_text for token in ("事实", "正确答案", "学术", "共识", "不准确", "争议")):
        tags.append("factual_risk")
    if question_type in ("single_choice", "multiple_choice") and (
        option_score <= 3 or has_absolute_claim or any(token in comments_text for token in ("干扰项", "选项", "区分度", "对等"))
    ):
        tags.append("distractor_risk")
    if difficulty_score <= 3 or "难度" in comments_text:
        tags.append("difficulty_risk")

    normalized_options = _normalize_option_map(options)
    if question_type == "true_false":
        if set(normalized_options.keys()) != {"A", "B"}:
            tags.append("type_mismatch")
    elif question_type == "fill_blank":
        if normalized_options or not _has_blank_marker(stem):
            tags.append("type_mismatch")
    elif question_type in ("short_answer", "essay"):
        if (
            normalized_options
            or _has_blank_marker(stem)
            or _looks_like_option_answer(correct_answer)
            or len(str(correct_answer or "").strip()) < 8
        ):
            tags.append("type_mismatch")
    elif question_type in ("single_choice", "multiple_choice"):
        if len(normalized_options) < 4:
            tags.append("type_mismatch")

    return list(dict.fromkeys(tags))


def _finalize_review_payload(
    payload: dict,
    *,
    stem: str,
    options: Optional[dict],
    correct_answer: str,
    explanation: Optional[str],
    question_type: str,
) -> dict:
    payload = dict(payload or {})
    comments = str(payload.get("comments", "") or "")
    payload["risk_tags"] = _infer_review_risk_tags(
        stem=stem,
        options=options,
        correct_answer=correct_answer,
        explanation=explanation,
        question_type=question_type,
        scores=payload.get("scores"),
        comments=comments,
    )
    return payload


def _normalize_option_map(options: Optional[dict]) -> dict[str, str]:
    if not isinstance(options, dict):
        return {}
    return {
        str(key).strip().upper(): str(value).strip()
        for key, value in options.items()
        if str(key).strip() and str(value).strip()
    }


def _normalize_boolean_label(value: str) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    if normalized in BOOLEAN_TRUE_LABELS:
        return "true"
    if normalized in BOOLEAN_FALSE_LABELS:
        return "false"
    return None


def _has_blank_marker(stem: str) -> bool:
    collapsed = str(stem or "").replace(" ", "")
    return any(marker in collapsed for marker in BLANK_MARKERS)


def _looks_like_option_answer(answer: str) -> bool:
    return bool(re.fullmatch(r"[A-F]+", str(answer or "").strip().upper()))


def _has_short_answer_prompt(stem: str) -> bool:
    stem = str(stem or "")
    return any(hint in stem for hint in SHORT_ANSWER_HINTS) or "？" in stem or "?" in stem


def ai_review_question(
    stem: str,
    options: Optional[dict],
    correct_answer: str,
    explanation: Optional[str],
    question_type: str,
    difficulty: int,
    dimension: Optional[str] = None,
) -> dict:
    """Use AI to review a question's quality.

    Returns a review dict with scores, recommendation, and comments.
    """
    if settings.LLM_API_KEY == "your-api-key":
        logger.warning("LLM API key not configured, using rule-based review")
        return _rule_based_review(
            stem, options, correct_answer, explanation, question_type, difficulty, dimension
        )

    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )

        question_text = f"""题型：{question_type}
难度：{difficulty}/5
知识维度：{dimension or '未标注'}
题干：{stem}
选项：{json.dumps(options, ensure_ascii=False) if options else '无'}
正确答案：{correct_answer}
解析：{explanation or '无'}"""

        request_kwargs = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": f"请审核以下题目：\n\n{question_text}"},
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        extra_body = build_disable_thinking_extra_body(
            settings.LLM_MODEL,
            settings.LLM_BASE_URL,
        )
        if extra_body:
            request_kwargs["extra_body"] = extra_body

        response = client.chat.completions.create(**request_kwargs)

        raw = response.choices[0].message.content.strip()
        raw = strip_thinking_tags(raw)
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

        return _finalize_review_payload(
            json.loads(raw),
            stem=stem,
            options=options,
            correct_answer=correct_answer,
            explanation=explanation,
            question_type=question_type,
        )

    except Exception as e:
        logger.error(f"AI review failed: {e}")
        return _rule_based_review(
            stem, options, correct_answer, explanation, question_type, difficulty, dimension
        )


def _rule_based_review(
    stem: str,
    options: Optional[dict],
    correct_answer: str,
    explanation: Optional[str],
    question_type: str,
    difficulty: int,
    dimension: Optional[str] = None,
) -> dict:
    """Rule-based quality check fallback when LLM is not available."""
    stem = str(stem or "").strip()
    correct_answer = str(correct_answer or "").strip()
    normalized_options = _normalize_option_map(options)
    option_values = list(normalized_options.values())
    scores = {}
    comments_parts: list[str] = []

    # Stem clarity
    stem_score = 5
    if len(stem) < 10:
        stem_score = 2
    elif len(stem) < 20:
        stem_score = 3

    if question_type in ("single_choice", "multiple_choice"):
        if not any(token in stem for token in ("？", "?", "：", ":", "哪项", "下列", "以下")):
            stem_score = max(stem_score - 1, 1)
    elif question_type == "fill_blank":
        if _has_blank_marker(stem):
            stem_score = max(stem_score, 4)
        else:
            stem_score = max(stem_score - 2, 1)
            comments_parts.append("填空题题干应包含明确空位")
    elif question_type in ("short_answer", "essay"):
        if not _has_short_answer_prompt(stem):
            stem_score = max(stem_score - 1, 1)
            comments_parts.append("主观题题干应明确说明回答任务")
    elif question_type == "true_false" and len(stem) < 8:
        stem_score = min(stem_score, 2)

    scores["stem_clarity"] = stem_score

    # Option quality + answer correctness
    if question_type == "single_choice":
        option_quality = 4 if len(normalized_options) >= 4 else 2
        if len(normalized_options) == 3:
            option_quality = 3
        if option_values and all(len(value) < 4 for value in option_values):
            option_quality = min(option_quality, 3)
        if len({value.lower() for value in option_values}) < len(option_values):
            option_quality = min(option_quality, 2)
            comments_parts.append("单选题选项存在重复或区分度不足")
        answer_score = 4 if correct_answer in normalized_options else 2
        if answer_score < 4:
            comments_parts.append("单选题正确答案未落在选项内")
    elif question_type == "multiple_choice":
        option_quality = 4 if len(normalized_options) >= 4 else 2
        answers = sorted({char for char in correct_answer.upper() if char.isalpha()})
        answer_score = 4 if len(answers) >= 2 and all(char in normalized_options for char in answers) else 2
        if len(answers) < 2:
            comments_parts.append("多选题正确答案至少应包含两个选项")
        if answer_score < 4:
            comments_parts.append("多选题正确答案与选项不匹配")
    elif question_type == "true_false":
        normalized_labels = {
            _normalize_boolean_label(value)
            for value in option_values
        }
        normalized_labels.discard(None)
        has_standard_options = (
            len(normalized_options) == 2
            and {"T", "F"}.issubset(normalized_options.keys())
        )
        if has_standard_options and normalized_labels == {"true", "false"}:
            option_quality = 5
        elif has_standard_options:
            option_quality = 4
            comments_parts.append("判断题建议使用“正确/错误”标准选项")
        else:
            option_quality = 2
            comments_parts.append("判断题应仅提供 T/F 两个标准选项")
        answer_score = 4 if correct_answer in ("T", "F") and has_standard_options else 2
        if answer_score < 4:
            comments_parts.append("判断题正确答案应为 T 或 F")
    elif question_type == "fill_blank":
        option_quality = 5 if not normalized_options else 1
        answer_score = 4
        if normalized_options:
            comments_parts.append("填空题不应提供选择项")
        if not correct_answer:
            answer_score = 1
        elif _looks_like_option_answer(correct_answer):
            answer_score = 2
            comments_parts.append("填空题正确答案不应是选项字母")
        elif len(correct_answer) > 48:
            answer_score = 3
            comments_parts.append("填空题答案过长，更适合改为简答题")
    elif question_type in ("short_answer", "essay"):
        option_quality = 5 if not normalized_options else 1
        answer_score = 4
        if normalized_options:
            comments_parts.append("主观题不应提供选择项")
        if not correct_answer:
            answer_score = 1
        elif _looks_like_option_answer(correct_answer) or len(correct_answer) < 8:
            answer_score = 2
            comments_parts.append("主观题参考答案过短或格式错误")
        elif not explanation or len(str(explanation).strip()) < 8:
            answer_score = 3
            comments_parts.append("主观题建议补充更完整的解析或评分依据")
    else:
        option_quality = 4 if not normalized_options else 3
        answer_score = 4 if correct_answer else 2

    scores["option_quality"] = option_quality
    scores["answer_correctness"] = answer_score

    # Knowledge alignment
    scores["knowledge_alignment"] = 4 if dimension else 3
    if not dimension:
        comments_parts.append("建议添加知识维度标签")

    # Difficulty calibration
    if 1 <= difficulty <= 5:
        difficulty_score = 4
        if question_type in ("short_answer", "essay") and difficulty <= 2:
            difficulty_score = 3
            comments_parts.append("主观题当前难度标注偏低")
        elif question_type == "true_false" and difficulty >= 4 and len(stem) < 18:
            difficulty_score = 3
            comments_parts.append("判断题当前难度标注偏高")
    else:
        difficulty_score = 2
        comments_parts.append("难度标注超出 1-5 范围")
    scores["difficulty_calibration"] = difficulty_score

    overall = sum(scores.values()) / len(scores)

    if overall >= 3.5:
        recommendation = "approve"
    elif overall >= 2.5:
        recommendation = "revise"
    else:
        recommendation = "reject"

    if scores["stem_clarity"] < 3 and "题干过短或缺少标点" not in comments_parts:
        comments_parts.append("题干过短或表达不完整")
    if scores["option_quality"] < 3 and question_type in ("single_choice", "multiple_choice"):
        comments_parts.append("选择题选项数量不足或区分度不够")
    if scores["answer_correctness"] < 3 and "答案格式可能有误" not in comments_parts:
        comments_parts.append("答案格式或内容可能有误")

    return _finalize_review_payload({
        "scores": scores,
        "overall_score": round(overall, 1),
        "recommendation": recommendation,
        "comments": "；".join(dict.fromkeys(comments_parts)) if comments_parts else "题目质量整体良好",
    }, stem=stem, options=options, correct_answer=correct_answer, explanation=explanation, question_type=question_type)
