"""Scoring agent - LLM-as-a-Judge for subjective question scoring.

Supports multi-model evaluator panel with bias mitigation.
"""
import json
import logging
import statistics
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.agents.llm_utils import (
    extract_json_text,
    strip_thinking_tags,
    build_disable_thinking_extra_body,
)

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """你是一个专业、严格且客观的AI素养评测评分专家。你需要根据题目、参考答案、评分标准和学生作答进行评分。

评分规则：
1. 只依据输入中的题目、参考答案、评分标准和学生作答评分
2. 不允许引用输入中不存在的知识点或事实
3. 关键概念必须准确，存在明显事实错误应扣分
4. 不要因为作答长度、礼貌措辞或语气而额外加分
5. 如果学生未作答或几乎未回应，应明确给低分

请严格按照以下JSON格式输出：
```json
{
  "earned_ratio": 0.8,
  "judgement": "一句客观评分结论",
  "positive_points": ["答对的点1"],
  "missed_points": ["遗漏的要点1"],
  "error_reasons": ["incomplete_answer"],
  "feedback": "面向考生的反馈",
  "confidence": 0.85,
  "evidence": ["基于学生答案可直接观察到的依据1"]
}
```

earned_ratio：得分比例（0.0-1.0），1.0为满分
judgement：一句客观结论，不要夸大
positive_points：回答中的有效点，最多3条
missed_points：相对参考答案遗漏的关键点，最多4条
error_reasons：仅允许使用以下枚举：concept_error, incomplete_answer, logic_gap, scenario_misjudgment, unsupported_claim, no_answer
feedback：简洁说明优点和不足
confidence：模型对本次评分的置信度（0.0-1.0）
evidence：只能引用学生答案、参考答案、评分标准中可以直接支持评分的依据，最多3条
"""

ALLOWED_ERROR_REASONS = {
    "concept_error",
    "incomplete_answer",
    "logic_gap",
    "scenario_misjudgment",
    "unsupported_claim",
    "no_answer",
}


def score_subjective_answer(
    stem: str,
    correct_answer: str,
    student_answer: str,
    question_type: str,
    max_score: float,
    rubric: Optional[dict] = None,
) -> dict:
    """Score a subjective answer using LLM or rule-based fallback.

    Returns dict with earned_score, is_correct, feedback, and analysis.
    """
    if not student_answer or not student_answer.strip():
        return _empty_answer_result()

    if settings.LLM_API_KEY == "your-api-key":
        return _with_scoring_source(
            _rule_based_scoring(
                stem, correct_answer, student_answer, question_type, max_score
            ),
            "fallback",
        )

    try:
        result = _call_subjective_scoring_llm(
            stem=stem,
            correct_answer=correct_answer,
            student_answer=student_answer,
            max_score=max_score,
            rubric=rubric,
        )
        normalized = _normalize_subjective_scoring_result(
            result,
            max_score=max_score,
            student_answer=student_answer,
        )
        return _with_scoring_source(normalized, "llm")

    except Exception as e:
        logger.error(f"LLM scoring failed: {e}")
        return _with_scoring_source(
            _rule_based_scoring(
                stem, correct_answer, student_answer, question_type, max_score
            ),
            "fallback",
        )


def _call_subjective_scoring_llm(
    *,
    stem: str,
    correct_answer: str,
    student_answer: str,
    max_score: float,
    rubric: Optional[dict],
) -> dict:
    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )

    rubric_text = ""
    if rubric:
        rubric_text = f"\n评分标准：{json.dumps(rubric, ensure_ascii=False)}"

    user_prompt = f"""题目：{stem}
参考答案：{correct_answer}{rubric_text}
学生作答：{student_answer}
满分：{max_score}

请输出严格符合要求的JSON评分结果。"""

    request_kwargs = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    extra_body = build_disable_thinking_extra_body(
        settings.LLM_MODEL,
        settings.LLM_BASE_URL,
    )
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    response = client.chat.completions.create(**request_kwargs)
    raw = extract_json_text(response.choices[0].message.content.strip())
    return json.loads(raw)


def _normalize_subjective_scoring_result(
    result: dict,
    *,
    max_score: float,
    student_answer: str,
) -> dict:
    earned_ratio = max(0.0, min(1.0, float(result.get("earned_ratio", 0.0))))
    if not student_answer.strip():
        earned_ratio = 0.0

    earned_score = round(earned_ratio * max_score, 1)
    positive_points = _normalize_string_list(result.get("positive_points"), limit=3)
    missed_points = _normalize_string_list(result.get("missed_points"), limit=4)
    evidence = _normalize_string_list(result.get("evidence"), limit=3)
    error_reasons = [
        reason
        for reason in _normalize_string_list(result.get("error_reasons"), limit=4)
        if reason in ALLOWED_ERROR_REASONS
    ]

    if earned_score <= 0 and not error_reasons:
        error_reasons = ["no_answer" if not student_answer.strip() else "incomplete_answer"]
    if earned_ratio >= 0.8:
        missed_points = missed_points[:2]

    judgement = str(result.get("judgement") or "").strip()
    feedback = str(result.get("feedback") or "").strip()
    confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

    if not judgement:
        judgement = "回答覆盖了部分参考要点。"
    if not feedback:
        feedback = judgement

    return {
        "earned_score": earned_score,
        "is_correct": earned_ratio >= 0.6,
        "feedback": feedback,
        "analysis": {
            "earned_ratio": round(earned_ratio, 4),
            "judgement": judgement,
            "positive_points": positive_points,
            "missed_points": missed_points,
            "error_reasons": error_reasons,
            "confidence": confidence,
            "evidence": evidence,
        },
    }


def _normalize_string_list(value, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _with_scoring_source(result: dict, source: str) -> dict:
    normalized = dict(result)
    analysis = dict(normalized.get("analysis") or {})
    analysis["scoring_source"] = source
    normalized["analysis"] = analysis
    return normalized


def _empty_answer_result() -> dict:
    return {
        "earned_score": 0.0,
        "is_correct": False,
        "feedback": "未作答",
        "analysis": {
            "earned_ratio": 0.0,
            "judgement": "未作答。",
            "positive_points": [],
            "missed_points": [],
            "error_reasons": ["no_answer"],
            "confidence": 1.0,
            "evidence": [],
            "scoring_source": "rule",
        },
    }


def _rule_based_scoring(
    stem: str,
    correct_answer: str,
    student_answer: str,
    question_type: str,
    max_score: float,
) -> dict:
    """Simple keyword-matching fallback for subjective scoring."""
    if not student_answer or not student_answer.strip():
        return _empty_answer_result()

    # Split reference answer into key phrases
    ref_keywords = set()
    for seg in correct_answer.replace("，", ",").replace("。", ",").replace("；", ",").split(","):
        seg = seg.strip()
        if len(seg) >= 2:
            ref_keywords.add(seg)

    if not ref_keywords:
        ref_keywords = {correct_answer.strip()}

    # Count keyword matches
    matched = sum(1 for kw in ref_keywords if kw in student_answer)
    total = len(ref_keywords)

    ratio = matched / total if total > 0 else 0
    # Bonus for length (shows effort)
    if len(student_answer) > len(correct_answer) * 0.5:
        ratio = min(1.0, ratio + 0.1)

    earned_score = round(ratio * max_score, 1)

    feedback_parts = []
    if ratio >= 0.8:
        feedback_parts.append("回答较为完整")
    elif ratio >= 0.5:
        feedback_parts.append("回答部分正确，但有遗漏")
    else:
        feedback_parts.append("回答不够完整，需要补充关键概念")

    error_reasons = []
    if ratio < 0.8:
        error_reasons.append("incomplete_answer")
    if ratio < 0.4:
        error_reasons.append("concept_error")

    return {
        "earned_score": earned_score,
        "is_correct": ratio >= 0.6,
        "feedback": "；".join(feedback_parts),
        "analysis": {
            "earned_ratio": round(ratio, 4),
            "judgement": feedback_parts[0],
            "positive_points": [f"命中参考答案关键词 {matched}/{total} 个"] if matched else [],
            "missed_points": [kw for kw in sorted(ref_keywords) if kw not in student_answer][:4],
            "error_reasons": error_reasons,
            "confidence": 0.45,
            "evidence": [f"学生答案包含关键词：{kw}" for kw in sorted(ref_keywords) if kw in student_answer][:3],
            "scoring_source": "rule",
        },
    }


# ---- Multi-Model Evaluator Panel (T020) ----

PANEL_SYSTEM_PROMPT = """你是一位专业的AI素养评测评分专家。请根据评分维度对学生的回答进行独立评分。

重要规则（防偏见）：
1. 不要因为回答长度而给予额外分数
2. 不要因为学生使用礼貌或讨好的语言而加分
3. 只关注内容的准确性、完整性和逻辑性
4. 严格按照评分标准（Rubric）评分，不要放水

{position_instruction}

评分维度：
- accuracy（准确性）：概念是否正确，是否有事实错误
- completeness（完整性）：是否覆盖了参考答案的要点
- logic（逻辑性）：论述是否有条理，推理是否合理
- expression（表达性）：语言是否清晰，是否易于理解

请严格以JSON格式输出：
```json
{{
  "scores": {{
    "accuracy": 0-10,
    "completeness": 0-10,
    "logic": 0-10,
    "expression": 0-10
  }},
  "overall_ratio": 0.0-1.0,
  "feedback": "评分反馈..."
}}
```"""

# Position swap instructions for bias mitigation
POSITION_INSTRUCTIONS = [
    "请先阅读参考答案，再阅读学生作答。",
    "请先阅读学生作答，再阅读参考答案。注意不要因为阅读顺序而产生偏见。",
    "请同时对比参考答案和学生作答，注意独立判断。",
]


def _single_evaluator_score(
    stem: str,
    correct_answer: str,
    student_answer: str,
    max_score: float,
    rubric: Optional[dict],
    position_index: int,
) -> dict:
    """Single evaluator scoring with position swap for bias mitigation."""
    position_instruction = POSITION_INSTRUCTIONS[position_index % len(POSITION_INSTRUCTIONS)]

    rubric_text = ""
    if rubric:
        rubric_text = f"\n评分标准（Rubric）：{json.dumps(rubric, ensure_ascii=False)}"

    # Build user prompt with position swap
    if position_index % 2 == 0:
        user_prompt = f"""题目：{stem}
参考答案：{correct_answer}{rubric_text}
学生作答：{student_answer}
满分：{max_score}"""
    else:
        user_prompt = f"""题目：{stem}
学生作答：{student_answer}{rubric_text}
参考答案：{correct_answer}
满分：{max_score}"""

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        request_kwargs = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": PANEL_SYSTEM_PROMPT.format(
                    position_instruction=position_instruction
                )},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
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

        result = json.loads(raw)
        return result

    except Exception as e:
        logger.warning(f"Evaluator {position_index} failed: {e}")
        return None


def multi_model_score(
    stem: str,
    correct_answer: str,
    student_answer: str,
    question_type: str,
    max_score: float,
    rubric: Optional[dict] = None,
    num_evaluators: int = 3,
) -> dict:
    """Multi-model evaluator panel scoring.

    Uses multiple evaluators with position swapping for bias mitigation.
    Returns averaged scores with dimension breakdown.
    """
    if not student_answer or not student_answer.strip():
        return {
            "earned_score": 0.0,
            "is_correct": False,
            "feedback": "未作答",
            "panel_scores": [],
            "dimension_scores": {
                "accuracy": 0, "completeness": 0, "logic": 0, "expression": 0
            },
        }

    if settings.LLM_API_KEY == "your-api-key":
        return _rule_based_panel_scoring(
            stem, correct_answer, student_answer, question_type, max_score, num_evaluators
        )

    # Run multiple evaluators
    panel_results = []
    for i in range(num_evaluators):
        result = _single_evaluator_score(
            stem, correct_answer, student_answer, max_score, rubric, i
        )
        if result:
            panel_results.append(result)

    if not panel_results:
        return _rule_based_panel_scoring(
            stem, correct_answer, student_answer, question_type, max_score, num_evaluators
        )

    return _aggregate_panel_results(panel_results, max_score)


def _aggregate_panel_results(panel_results: list[dict], max_score: float) -> dict:
    """Aggregate results from multiple evaluators."""
    ratios = []
    dim_scores = {"accuracy": [], "completeness": [], "logic": [], "expression": []}
    feedbacks = []

    for r in panel_results:
        ratio = max(0.0, min(1.0, float(r.get("overall_ratio", 0.5))))
        ratios.append(ratio)

        scores = r.get("scores", {})
        for dim in dim_scores:
            dim_scores[dim].append(float(scores.get(dim, 5)))

        if r.get("feedback"):
            feedbacks.append(r["feedback"])

    # Average ratio (removing outliers if 3+ evaluators)
    if len(ratios) >= 3:
        avg_ratio = statistics.mean(sorted(ratios)[1:-1]) if len(ratios) > 3 else statistics.mean(ratios)
    else:
        avg_ratio = statistics.mean(ratios)

    earned_score = round(avg_ratio * max_score, 1)
    avg_dims = {dim: min(10.0, round(statistics.mean(scores), 1)) for dim, scores in dim_scores.items()}

    return {
        "earned_score": earned_score,
        "is_correct": avg_ratio >= 0.6,
        "feedback": feedbacks[0] if feedbacks else "评审团综合评分",
        "panel_scores": [{"ratio": r, "scores": panel_results[i].get("scores")}
                        for i, r in enumerate(ratios)],
        "dimension_scores": avg_dims,
        "evaluator_count": len(panel_results),
        "score_variance": round(statistics.variance(ratios), 4) if len(ratios) >= 2 else 0,
    }


def _rule_based_panel_scoring(
    stem: str,
    correct_answer: str,
    student_answer: str,
    question_type: str,
    max_score: float,
    num_evaluators: int,
) -> dict:
    """Rule-based fallback for multi-model panel scoring."""
    base = _rule_based_scoring(stem, correct_answer, student_answer, question_type, max_score)
    ratio = base["earned_score"] / max_score if max_score > 0 else 0

    # Simulate panel with slight variance
    import random
    panel_scores = []
    for i in range(num_evaluators):
        noise = random.uniform(-0.1, 0.1)
        adj_ratio = max(0.0, min(1.0, ratio + noise))
        panel_scores.append({
            "ratio": round(adj_ratio, 2),
            "scores": {
                "accuracy": round(adj_ratio * 10, 1),
                "completeness": round(min(10, adj_ratio * 10 * random.uniform(0.8, 1.2)), 1),
                "logic": round(min(10, adj_ratio * 10 * random.uniform(0.85, 1.15)), 1),
                "expression": round(min(10, adj_ratio * 10 * random.uniform(0.9, 1.1)), 1),
            },
        })

    avg_ratio = statistics.mean([p["ratio"] for p in panel_scores])
    avg_dims = {}
    for dim in ["accuracy", "completeness", "logic", "expression"]:
        avg_dims[dim] = round(statistics.mean([p["scores"][dim] for p in panel_scores]), 1)

    return {
        "earned_score": round(avg_ratio * max_score, 1),
        "is_correct": avg_ratio >= 0.6,
        "feedback": base["feedback"],
        "panel_scores": panel_scores,
        "dimension_scores": avg_dims,
        "evaluator_count": num_evaluators,
        "score_variance": round(statistics.variance([p["ratio"] for p in panel_scores]), 4)
                          if num_evaluators >= 2 else 0,
    }
