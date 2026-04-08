"""Interactive scenario agent for SJT situational judgment assessments.

Manages role-playing dialogue, dynamic difficulty adjustment,
and conversation analysis for situational interactive Q&A.
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.core.llm_config import get_llm_config_sync, make_openai_client

logger = logging.getLogger(__name__)

SCENARIO_SYSTEM_PROMPT = """你是一个AI素养情境评测专家，正在主持一场情境判断测试（SJT）。

你的角色：{role_description}

场景背景：{scenario}

评估维度：{dimension}
当前难度等级：{difficulty}（1-5，1=最简单，5=最难）

你的任务：
1. 根据场景背景，以角色身份与考生进行多轮对话
2. 每轮对话中，提出一个情境问题或追问
3. 根据考生的回答质量，动态调整后续问题的难度
4. 评估考生在以下三个维度的表现：
   - prompt_engineering: 提示工程能力（提问和指令表达的清晰性）
   - critical_thinking: 批判性思维（分析和判断的深度）
   - ethical_decision: 伦理决策（AI相关伦理问题的处理）

对话要求：
- 每次回复必须包含一个情境问题
- 问题要符合当前难度等级
- 自然地引导对话，不要显得生硬
- 回复中不要暴露评分维度

请以JSON格式输出：
```json
{{
  "response": "你的回复内容（包含情境问题）",
  "analysis": {{
    "prompt_engineering": 0-10,
    "critical_thinking": 0-10,
    "ethical_decision": 0-10,
    "reasoning": "评分理由"
  }},
  "difficulty_adjustment": 0,
  "should_end": false
}}
```

difficulty_adjustment: -1（降低难度）, 0（保持）, 1（提高难度）
should_end: 当对话应该结束时设为true（如考生已充分展示能力或明确放弃）"""


SUMMARY_PROMPT = """请根据以下情境对话记录，生成最终评估摘要。

场景：{scenario}
维度：{dimension}

对话记录：
{conversation}

请以JSON格式输出最终评估：
```json
{{
  "overall_score": 0-100,
  "dimension_scores": {{
    "prompt_engineering": {{"score": 0-10, "comment": "..."}},
    "critical_thinking": {{"score": 0-10, "comment": "..."}},
    "ethical_decision": {{"score": 0-10, "comment": "..."}}
  }},
  "key_decisions": ["关键决策点1", "关键决策点2"],
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["不足1", "不足2"],
  "recommendations": ["建议1", "建议2"]
}}
```"""


def generate_scenario_response(
    scenario: str,
    role_description: str,
    dimension: str,
    difficulty: int,
    conversation_history: list[dict],
    user_message: str,
) -> dict:
    """Generate next scenario turn using LLM or rule-based fallback."""
    _cfg = get_llm_config_sync("interactive")
    if _cfg.api_key == "your-api-key":
        return _rule_based_response(
            scenario, dimension, difficulty, conversation_history, user_message
        )

    try:
        client = make_openai_client(_cfg)

        system_msg = SCENARIO_SYSTEM_PROMPT.format(
            role_description=role_description or "AI评测教练",
            scenario=scenario,
            dimension=dimension or "AI综合素养",
            difficulty=difficulty,
        )

        messages = [{"role": "system", "content": system_msg}]
        for turn in conversation_history:
            messages.append({
                "role": "assistant" if turn["role"] == "system" else "user",
                "content": turn["content"],
            })
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=_cfg.model,
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        return json.loads(content)

    except Exception as e:
        logger.warning(f"LLM interactive response failed: {e}, using fallback")
        return _rule_based_response(
            scenario, dimension, difficulty, conversation_history, user_message
        )


def generate_session_summary(
    scenario: str,
    dimension: str,
    turns: list[dict],
) -> dict:
    """Generate final evaluation summary for completed session."""
    _cfg2 = get_llm_config_sync("interactive")
    if _cfg2.api_key == "your-api-key":
        return _rule_based_summary(turns)

    try:
        client = make_openai_client(_cfg2)

        conversation = "\n".join(
            f"{'[AI]' if t['role'] == 'system' else '[考生]'}: {t['content']}"
            for t in turns
        )

        response = client.chat.completions.create(
            model=_cfg2.model,
            messages=[
                {"role": "system", "content": "你是一个AI素养评测评估专家。"},
                {"role": "user", "content": SUMMARY_PROMPT.format(
                    scenario=scenario,
                    dimension=dimension or "AI综合素养",
                    conversation=conversation,
                )},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        return json.loads(content)

    except Exception as e:
        logger.warning(f"LLM summary generation failed: {e}")
        return _rule_based_summary(turns)


def _rule_based_response(
    scenario: str,
    dimension: str,
    difficulty: int,
    conversation_history: list[dict],
    user_message: str,
) -> dict:
    """Rule-based fallback for interactive responses."""
    turn_count = len(conversation_history) // 2 + 1  # Current turn number
    user_len = len(user_message)

    # Simple quality assessment based on response length and keywords
    quality_keywords = [
        "因为", "所以", "考虑", "分析", "伦理", "风险", "隐私",
        "安全", "公平", "透明", "负责", "评估", "优化", "方案",
    ]
    keyword_count = sum(1 for kw in quality_keywords if kw in user_message)

    # Score based on length and keyword density
    pe_score = min(10, max(2, keyword_count * 2 + (1 if user_len > 50 else 0)))
    ct_score = min(10, max(2, keyword_count * 2 + (2 if user_len > 100 else 0)))
    ed_score = min(10, max(2, keyword_count + (3 if any(
        kw in user_message for kw in ["伦理", "隐私", "公平", "安全"]
    ) else 0)))

    # Difficulty adjustment
    avg_score = (pe_score + ct_score + ed_score) / 3
    diff_adj = 1 if avg_score >= 7 else (-1 if avg_score <= 3 else 0)

    # Should end after max turns
    should_end = turn_count >= 3

    # Generate follow-up questions by difficulty
    followup_questions = {
        1: [
            "在这种情况下，你会如何向同事解释AI工具的基本使用方法？",
            "如果AI给出了一个你不确定的答案，你的第一反应是什么？",
            "你认为在日常工作中，AI可以帮助我们做哪些事情？",
        ],
        2: [
            "你会如何设计一个有效的提示词来完成这个任务？",
            "如果AI的输出结果与你的预期不符，你会如何调整策略？",
            "在使用AI工具时，你认为需要注意哪些数据安全问题？",
        ],
        3: [
            "请分析一下在这个场景中使用AI可能带来的风险和收益。",
            "如果团队成员对AI的使用有不同意见，你会如何协调？",
            "你如何确保AI生成的内容符合组织的合规要求？",
        ],
        4: [
            "在这个复杂场景中，你会如何设计一个多步骤的AI解决方案？",
            "如果AI系统出现偏见问题，你会采取哪些纠正措施？",
            "请评估在此场景中部署AI系统对不同利益相关方的影响。",
        ],
        5: [
            "请设计一个完整的AI治理框架来应对这个挑战。",
            "在AI决策与人类判断产生冲突时，你的决策框架是什么？",
            "如何建立一个持续监控和改进AI系统的机制？",
        ],
    }

    effective_diff = max(1, min(5, difficulty + diff_adj))
    questions = followup_questions.get(effective_diff, followup_questions[3])
    question = questions[turn_count % len(questions)]

    if should_end:
        response_text = f"感谢你的详细回答。你的观点很有见地。这次情境对话到此结束。"
    else:
        response_text = f"你的回答有一定道理。让我继续深入这个场景——{question}"

    return {
        "response": response_text,
        "analysis": {
            "prompt_engineering": pe_score,
            "critical_thinking": ct_score,
            "ethical_decision": ed_score,
            "reasoning": f"基于回答长度({user_len}字)和关键词密度({keyword_count}个)的综合评估",
        },
        "difficulty_adjustment": diff_adj,
        "should_end": should_end,
    }


def _rule_based_summary(turns: list[dict]) -> dict:
    """Rule-based summary generation."""
    user_turns = [t for t in turns if t["role"] == "user"]

    # Aggregate analysis scores from turns
    pe_scores, ct_scores, ed_scores = [], [], []
    for t in turns:
        analysis = t.get("ai_analysis", {})
        if analysis:
            pe_scores.append(analysis.get("prompt_engineering", 5))
            ct_scores.append(analysis.get("critical_thinking", 5))
            ed_scores.append(analysis.get("ethical_decision", 5))

    pe_avg = sum(pe_scores) / len(pe_scores) if pe_scores else 5
    ct_avg = sum(ct_scores) / len(ct_scores) if ct_scores else 5
    ed_avg = sum(ed_scores) / len(ed_scores) if ed_scores else 5

    overall = round((pe_avg + ct_avg + ed_avg) / 3 * 10, 1)

    strengths = []
    weaknesses = []
    if pe_avg >= 7:
        strengths.append("提示工程能力较强，能够清晰表达需求")
    elif pe_avg < 5:
        weaknesses.append("提示工程能力有待提升，建议练习更精确的表达")
    if ct_avg >= 7:
        strengths.append("批判性思维突出，善于深入分析问题")
    elif ct_avg < 5:
        weaknesses.append("批判性思维需要加强，建议多角度思考问题")
    if ed_avg >= 7:
        strengths.append("伦理决策意识强，能够考虑多方利益")
    elif ed_avg < 5:
        weaknesses.append("伦理决策意识需增强，建议关注AI伦理相关知识")

    if not strengths:
        strengths.append("整体表现稳定")
    if not weaknesses:
        weaknesses.append("建议挑战更高难度的情境")

    return {
        "overall_score": overall,
        "dimension_scores": {
            "prompt_engineering": {"score": round(pe_avg, 1), "comment": "提示工程能力评估"},
            "critical_thinking": {"score": round(ct_avg, 1), "comment": "批判性思维评估"},
            "ethical_decision": {"score": round(ed_avg, 1), "comment": "伦理决策评估"},
        },
        "key_decisions": [f"回答了{len(user_turns)}个情境问题"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": ["继续参与情境练习以提升综合素养"],
    }
