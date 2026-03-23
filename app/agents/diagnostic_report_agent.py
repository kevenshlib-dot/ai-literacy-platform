"""LLM generator for structured diagnostic report sections."""
import json
import logging

from openai import OpenAI

from app.agents.llm_utils import build_disable_thinking_extra_body, extract_json_text
from app.core.config import settings

logger = logging.getLogger(__name__)

DIAGNOSTIC_REPORT_SYSTEM_PROMPT = """你是一名严格、客观的考试诊断报告分析师。

你只能依据输入的事实包生成结论，不得编造任何题目、维度、课程或成绩信息。

硬性规则：
1. 不得修改或重述与事实包冲突的总分、等级、百分位、维度分数。
2. 只能引用事实包中出现的 question_id、dimension、course_id。
3. 如果证据不足，明确说明“依据有限”，不要臆测。
4. 个性化总结必须客观，不夸大、不贬低。
5. 提升建议必须具体、可执行，并与错因和低分维度直接对应。
6. 推荐资源只能从 resource_candidates 中选择。

请严格输出 JSON，对象结构如下：
```json
{
  "wrong_answer_summary": {
    "overview": "整体错题概述",
    "items": [
      {
        "question_id": "uuid",
        "reason_summary": "该题错误原因总结",
        "improvement_tip": "针对该题的改进建议"
      }
    ],
    "patterns": ["高频错误模式1"]
  },
  "dimension_analysis": {
    "AI基础知识": {
      "summary": "该维度总结",
      "evidence": ["证据1"],
      "priority": "high"
    }
  },
  "personalized_summary": {
    "summary": "针对考生整体表现的客观总结",
    "highlights": ["亮点1"],
    "cautions": ["风险点1"]
  },
  "improvement_priorities": [
    {
      "dimension": "AI基础知识",
      "reason": "优先提升原因",
      "actions": ["行动1", "行动2"]
    }
  ],
  "actionable_suggestions": [
    {
      "dimension": "AI基础知识",
      "title": "建议标题",
      "suggestion": "建议内容",
      "actions": ["动作1", "动作2"]
    }
  ],
  "recommended_resources": [
    {
      "course_id": "uuid",
      "match_reason": "与当前薄弱项的匹配原因"
    }
  ]
}
```"""


def generate_structured_diagnostic_sections(fact_pack: dict) -> dict:
    """Generate LLM-backed report sections from a fact pack."""
    if settings.LLM_API_KEY == "your-api-key":
        raise RuntimeError("LLM not configured")

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )
    request_kwargs = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": DIAGNOSTIC_REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "请基于以下事实包生成结构化诊断报告：\n"
                + json.dumps(fact_pack, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
    }
    extra_body = build_disable_thinking_extra_body(
        settings.LLM_MODEL,
        settings.LLM_BASE_URL,
    )
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    response = client.chat.completions.create(**request_kwargs)
    raw = extract_json_text(response.choices[0].message.content.strip())
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("diagnostic report output must be a JSON object")
    return data
