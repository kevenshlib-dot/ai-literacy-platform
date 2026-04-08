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
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.core.llm_config import get_llm_config_sync, make_openai_client

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """你是一个专业的题目质量审核专家。你需要对题目进行全面的质量检查。

请从以下5个维度进行评估，每个维度给出1-5分的评分和简短评语：

1. **题干清晰度** (stem_clarity): 题干表述是否清晰、无歧义
2. **选项质量** (option_quality): 干扰项是否合理，是否有明显暗示
3. **答案正确性** (answer_correctness): 标注的正确答案是否确实正确
4. **知识对齐** (knowledge_alignment): 题目是否与标注的知识维度一致
5. **难度校准** (difficulty_calibration): 难度标注是否与题目实际难度匹配

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
    _cfg = get_llm_config_sync("review")
    if _cfg.api_key == "your-api-key":
        logger.warning("LLM API key not configured, using rule-based review")
        return _rule_based_review(
            stem, options, correct_answer, explanation, question_type, difficulty, dimension
        )

    try:
        client = make_openai_client(_cfg)

        question_text = f"""题型：{question_type}
难度：{difficulty}/5
知识维度：{dimension or '未标注'}
题干：{stem}
选项：{json.dumps(options, ensure_ascii=False) if options else '无'}
正确答案：{correct_answer}
解析：{explanation or '无'}"""

        response = client.chat.completions.create(
            model=_cfg.model,
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": f"请审核以下题目：\n\n{question_text}"},
            ],
            temperature=0.3,
            max_tokens=1024,
        )

        raw = response.choices[0].message.content.strip()
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

        return json.loads(raw)

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
    scores = {}

    # Stem clarity: check length and punctuation
    stem_score = 5
    if len(stem) < 10:
        stem_score = 2
    elif len(stem) < 20:
        stem_score = 3
    if "？" not in stem and "。" not in stem and "?" not in stem and ":" not in stem:
        stem_score = max(stem_score - 1, 1)
    scores["stem_clarity"] = stem_score

    # Option quality
    if question_type in ("single_choice", "multiple_choice"):
        if options and len(options) >= 3:
            opt_score = 4
            values = list(options.values())
            if all(len(v) < 5 for v in values):
                opt_score = 3
            scores["option_quality"] = opt_score
        else:
            scores["option_quality"] = 2
    elif question_type == "true_false":
        scores["option_quality"] = 4
    else:
        scores["option_quality"] = 4

    # Answer correctness
    if correct_answer and len(correct_answer.strip()) > 0:
        if question_type == "single_choice" and correct_answer in ("A", "B", "C", "D"):
            scores["answer_correctness"] = 4
        elif question_type == "multiple_choice" and all(c in "ABCD" for c in correct_answer):
            scores["answer_correctness"] = 4
        elif question_type == "true_false" and correct_answer in ("A", "B"):
            scores["answer_correctness"] = 4
        else:
            scores["answer_correctness"] = 3
    else:
        scores["answer_correctness"] = 1

    # Knowledge alignment
    scores["knowledge_alignment"] = 4 if dimension else 3

    # Difficulty calibration
    scores["difficulty_calibration"] = 4 if 1 <= difficulty <= 5 else 2

    # Calculate overall
    overall = sum(scores.values()) / len(scores)

    if overall >= 3.5:
        recommendation = "approve"
    elif overall >= 2.5:
        recommendation = "revise"
    else:
        recommendation = "reject"

    comments_parts = []
    if scores["stem_clarity"] < 3:
        comments_parts.append("题干过短或缺少标点")
    if scores.get("option_quality", 4) < 3:
        comments_parts.append("选项数量不足或过于简短")
    if scores["answer_correctness"] < 3:
        comments_parts.append("答案格式可能有误")
    if not dimension:
        comments_parts.append("建议添加知识维度标签")

    return {
        "scores": scores,
        "overall_score": round(overall, 1),
        "recommendation": recommendation,
        "comments": "；".join(comments_parts) if comments_parts else "题目质量整体良好",
    }
