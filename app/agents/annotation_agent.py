"""Annotation agent - LLM-based auto-annotation of material content.

Auto-annotates literacy dimensions, difficulty, and knowledge points.
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

ANNOTATION_PROMPT = """你是一个AI素养评测专家。请分析以下教学材料内容，标注以下信息：

1. dimension: 所属的AI素养维度（从以下选择：AI基础知识、AI技术应用、AI伦理安全、AI批判思维、AI创新实践）
2. difficulty: 难度等级（1-5，1=入门，5=专家）
3. knowledge_points: 核心知识点列表
4. summary: 内容摘要（50字以内）
5. tags: 标签列表

请以JSON格式输出：
```json
{{
  "dimension": "AI基础知识",
  "difficulty": 3,
  "knowledge_points": ["知识点1", "知识点2"],
  "summary": "内容摘要...",
  "tags": ["标签1", "标签2"]
}}
```"""


def auto_annotate_content(content: str, title: Optional[str] = None) -> dict:
    """Auto-annotate material content using LLM or rule-based fallback."""
    if settings.LLM_API_KEY == "your-api-key":
        return _rule_based_annotation(content, title)

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        user_msg = f"标题：{title or '未命名'}\n\n内容：{content[:2000]}"

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": ANNOTATION_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
        result = json.loads(raw)
        result["confidence"] = 0.85
        return result

    except Exception as e:
        logger.warning(f"LLM annotation failed: {e}, using rule-based")
        return _rule_based_annotation(content, title)


def _rule_based_annotation(content: str, title: Optional[str] = None) -> dict:
    """Rule-based annotation fallback using keyword matching."""
    text = f"{title or ''} {content}".lower()

    # Dimension detection
    dimension_keywords = {
        "AI基础知识": ["人工智能", "机器学习", "深度学习", "神经网络", "算法", "模型", "训练", "数据集"],
        "AI技术应用": ["应用", "工具", "场景", "实践", "部署", "系统", "平台", "产品"],
        "AI伦理安全": ["伦理", "隐私", "安全", "偏见", "公平", "透明", "责任", "法规", "数据保护"],
        "AI批判思维": ["批判", "评估", "分析", "判断", "局限", "风险", "误导", "验证"],
        "AI创新实践": ["创新", "设计", "提示工程", "prompt", "创造", "解决方案", "优化"],
    }

    dimension_scores = {}
    for dim, keywords in dimension_keywords.items():
        score = sum(1 for kw in keywords if kw in text)
        dimension_scores[dim] = score

    dimension = max(dimension_scores, key=dimension_scores.get) if any(dimension_scores.values()) else "AI基础知识"

    # Difficulty estimation
    complexity_indicators = {
        1: ["基础", "入门", "简介", "什么是", "概述"],
        2: ["原理", "方法", "步骤", "流程"],
        3: ["技术", "实现", "架构", "框架"],
        4: ["高级", "进阶", "优化", "调优"],
        5: ["前沿", "研究", "论文", "最新", "state-of-the-art"],
    }
    difficulty = 3
    for level, indicators in complexity_indicators.items():
        if any(ind in text for ind in indicators):
            difficulty = level

    # Knowledge points extraction
    knowledge_points = []
    kp_candidates = ["人工智能", "机器学习", "深度学习", "自然语言处理", "计算机视觉",
                     "数据分析", "神经网络", "强化学习", "生成式AI", "大语言模型",
                     "提示工程", "AI伦理", "数据隐私", "算法偏见"]
    for kp in kp_candidates:
        if kp in text:
            knowledge_points.append(kp)

    if not knowledge_points:
        knowledge_points = ["AI相关知识"]

    # Summary
    summary = content[:50].replace("\n", " ") + ("..." if len(content) > 50 else "")

    return {
        "dimension": dimension,
        "difficulty": difficulty,
        "knowledge_points": knowledge_points[:5],
        "summary": summary,
        "tags": knowledge_points[:3],
        "confidence": 0.6,
    }
