"""Three-agent system for dynamic indicator generation.

Research Agent: Tracks AI field developments
Consultant Agent: Maps findings to five-dimension framework
Review Agent: Red-team audit and quality check
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.agents.llm_utils import strip_thinking_tags

logger = logging.getLogger(__name__)

FIVE_DIMENSIONS = [
    "AI基础知识",
    "AI技术应用",
    "AI伦理安全",
    "AI批判思维",
    "AI创新实践",
]


def research_agent(topic: Optional[str] = None) -> dict:
    """Research Agent: identify emerging AI trends and developments.

    Returns research findings with source references.
    """
    if settings.LLM_API_KEY == "your-api-key":
        return _rule_based_research(topic)

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        prompt = f"""你是一个AI领域研究员。请分析最新的AI发展动态，识别以下方面的趋势：
1. 新兴AI技术或工具
2. AI政策法规变化
3. AI伦理与安全新议题
4. AI教育与素养新需求

{"关注领域：" + topic if topic else ""}

请以JSON格式输出研究发现：
```json
{{
  "findings": [
    {{
      "title": "发现标题",
      "category": "技术/政策/伦理/教育",
      "summary": "简要描述",
      "relevance": "与AI素养的关联",
      "source_type": "arXiv/政策文件/行业报告",
      "importance": "高/中/低"
    }}
  ]
}}
```"""
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = response.choices[0].message.content.strip()
        raw = strip_thinking_tags(raw)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Research agent LLM failed: {e}")
        return _rule_based_research(topic)


def consultant_agent(research_findings: dict) -> list[dict]:
    """Consultant Agent: map research findings to five-dimension framework.

    Generates indicator proposals from research findings.
    """
    if settings.LLM_API_KEY == "your-api-key":
        return _rule_based_consultant(research_findings)

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        dims_str = "、".join(FIVE_DIMENSIONS)
        findings_str = json.dumps(research_findings, ensure_ascii=False, indent=2)

        prompt = f"""你是一个AI素养评测框架顾问。基于以下研究发现，提出评测指标更新建议。

五维框架：{dims_str}

研究发现：
{findings_str}

请为每个相关发现提出指标建议，以JSON数组格式输出：
```json
[
  {{
    "title": "建议标题",
    "dimension": "所属维度",
    "proposal_type": "new_indicator/update/deprecate",
    "description": "详细描述",
    "rationale": "建议理由"
  }}
]
```"""
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = response.choices[0].message.content.strip()
        raw = strip_thinking_tags(raw)
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Consultant agent LLM failed: {e}")
        return _rule_based_consultant(research_findings)


def review_agent(proposals: list[dict]) -> list[dict]:
    """Review Agent: red-team audit of indicator proposals.

    Evaluates feasibility, relevance, and potential issues.
    """
    if settings.LLM_API_KEY == "your-api-key":
        return _rule_based_review(proposals)

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        proposals_str = json.dumps(proposals, ensure_ascii=False, indent=2)

        prompt = f"""你是一个AI素养评测框架的红队审核员。请审查以下指标更新建议，评估：
1. 可行性（是否可以转化为可测量的评测指标）
2. 相关性（是否与AI素养框架匹配）
3. 潜在问题（是否有偏见、遗漏或不当之处）
4. 优先级建议

建议列表：
{proposals_str}

请以JSON数组格式输出审核结果：
```json
[
  {{
    "proposal_title": "建议标题",
    "approved": true/false,
    "confidence_score": 0.0-1.0,
    "feasibility": "高/中/低",
    "issues": ["问题1"],
    "suggestions": ["改进建议1"],
    "priority": "高/中/低"
  }}
]
```"""
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = response.choices[0].message.content.strip()
        raw = strip_thinking_tags(raw)
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Review agent LLM failed: {e}")
        return _rule_based_review(proposals)


# ---- Rule-based fallbacks ----

_TREND_TEMPLATES = [
    {
        "title": "大语言模型安全对齐",
        "category": "伦理",
        "summary": "大语言模型的安全对齐技术持续发展，包括RLHF、Constitutional AI等方法",
        "relevance": "需要更新AI伦理安全维度的评测指标",
        "source_type": "arXiv",
        "importance": "高",
    },
    {
        "title": "多模态AI应用普及",
        "category": "技术",
        "summary": "GPT-4V、Gemini等多模态模型推动图文理解和生成能力的提升",
        "relevance": "AI技术应用维度需要增加多模态相关指标",
        "source_type": "行业报告",
        "importance": "高",
    },
    {
        "title": "AI监管政策更新",
        "category": "政策",
        "summary": "欧盟AI法案、中国AI治理等全球监管框架不断完善",
        "relevance": "AI伦理安全和批判思维维度需更新法规相关内容",
        "source_type": "政策文件",
        "importance": "高",
    },
    {
        "title": "AI Agent与工具使用",
        "category": "技术",
        "summary": "AI Agent框架快速发展，工具调用和自主决策能力增强",
        "relevance": "AI创新实践维度需增加Agent设计和使用相关指标",
        "source_type": "arXiv",
        "importance": "中",
    },
    {
        "title": "提示工程最佳实践",
        "category": "教育",
        "summary": "提示工程方法论逐步成熟，出现更多结构化提示技术",
        "relevance": "AI创新实践维度需更新提示工程评测内容",
        "source_type": "行业报告",
        "importance": "中",
    },
]


def _rule_based_research(topic: Optional[str] = None) -> dict:
    """Rule-based research findings generator."""
    findings = _TREND_TEMPLATES.copy()
    if topic:
        topic_lower = topic.lower()
        findings = [f for f in findings if topic_lower in f["title"].lower()
                    or topic_lower in f["summary"].lower()
                    or topic_lower in f["category"].lower()]
        if not findings:
            findings = _TREND_TEMPLATES[:3]
    return {"findings": findings}


def _rule_based_consultant(research_findings: dict) -> list[dict]:
    """Generate proposals from research findings using rules."""
    findings = research_findings.get("findings", [])
    proposals = []

    dimension_map = {
        "技术": "AI技术应用",
        "伦理": "AI伦理安全",
        "政策": "AI伦理安全",
        "教育": "AI创新实践",
    }

    for finding in findings:
        category = finding.get("category", "技术")
        dimension = dimension_map.get(category, "AI基础知识")

        proposals.append({
            "title": f"新增指标：{finding['title']}相关能力评测",
            "dimension": dimension,
            "proposal_type": "new_indicator",
            "description": f"基于{finding['title']}的发展趋势，建议在{dimension}维度增加相关评测指标。{finding.get('summary', '')}",
            "rationale": finding.get("relevance", "与AI素养框架直接相关"),
        })

    return proposals


def _rule_based_review(proposals: list[dict]) -> list[dict]:
    """Red-team review using rule-based assessment."""
    reviews = []
    for proposal in proposals:
        title = proposal.get("title", "")
        description = proposal.get("description", "")
        dimension = proposal.get("dimension", "")

        # Check if dimension is valid
        valid_dimension = dimension in FIVE_DIMENSIONS

        # Score based on completeness
        has_description = len(description) > 20
        has_rationale = bool(proposal.get("rationale"))

        confidence = 0.5
        if valid_dimension:
            confidence += 0.2
        if has_description:
            confidence += 0.15
        if has_rationale:
            confidence += 0.15

        issues = []
        if not valid_dimension:
            issues.append("维度不在五维框架范围内")
        if not has_description:
            issues.append("描述过于简略")

        reviews.append({
            "proposal_title": title,
            "approved": confidence >= 0.7 and valid_dimension,
            "confidence_score": round(confidence, 2),
            "feasibility": "高" if confidence >= 0.8 else "中" if confidence >= 0.6 else "低",
            "issues": issues,
            "suggestions": ["建议增加具体的评测题目示例"] if not issues else [],
            "priority": proposal.get("importance", "中"),
        })

    return reviews
