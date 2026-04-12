"""Paper parsing enhancement agent - uses LLM to verify and correct regex-parsed paper structure.

Takes the output of parse_word_paper() (regex-based) and enhances it with:
- Question type verification/correction
- Answer inference when regex extraction failed
- Confidence scores and issue flags per question
"""
import json
import logging
import math
from typing import Optional

from app.core.llm_config import get_llm_config_sync, make_openai_client
from app.agents.llm_utils import extract_json_text, strip_thinking_tags

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

SYSTEM_PROMPT = """你是一位专业的考试试卷结构分析专家。你的任务是审核一份已被初步解析的试卷数据，验证并修正每道题的题型和答案。

你将收到一个JSON数组，每个元素代表一道题，包含：
- index: 题目序号
- section_title: 所在分节标题
- detected_type: 初步检测的题型（可能有误）
- stem: 题干（可能截断）
- options: 选项（如有）
- detected_answer: 初步检测的答案（可能为空或有误）

有效题型包括：
- true_false（判断题）：答案应为 T 或 F
- single_choice（单选题）：答案应为单个字母如 A、B、C、D
- multiple_choice（多选题）：答案应为多个字母如 ACD
- fill_blank（填空题）：答案为文本
- short_answer（简答/论述/开放题）：答案为文本

请对每道题：
1. 根据题干内容、选项结构判断正确的题型
2. 如果初步答案为空，尝试根据题干内容推断正确答案（仅在有足够信息时推断）
3. 验证已有答案的正确性和格式
4. 给出置信度（0.0-1.0）和发现的问题

严格按以下JSON数组格式输出，不要输出其他内容：
```json
[
  {
    "index": 1,
    "verified_type": "single_choice",
    "verified_answer": "B",
    "type_confidence": 0.95,
    "answer_confidence": 0.90,
    "issues": []
  }
]
```

注意：
- 如果无法确定答案，verified_answer 留空字符串""，answer_confidence 设为 0.0
- issues 是问题描述数组，如 ["答案缺失，需人工补充", "题型可能有误：检测为判断题但有4个选项"]
- 判断题答案统一用 T/F 格式
- 选择题答案统一用大写字母"""


def _build_question_summary(questions: list[dict], section_title: str = "") -> list[dict]:
    """Build a compact summary of questions for LLM input."""
    summaries = []
    for i, q_item in enumerate(questions):
        q = q_item.get("question", {}) or {}
        stem = q.get("stem", "")
        if len(stem) > 200:
            stem = stem[:200] + "..."

        summaries.append({
            "index": q_item.get("order_num", i + 1),
            "section_title": section_title,
            "detected_type": q.get("question_type", ""),
            "stem": stem,
            "options": q.get("options") or {},
            "detected_answer": q.get("correct_answer", ""),
        })
    return summaries


def _call_llm(summaries: list[dict], cfg) -> list[dict]:
    """Send question summaries to LLM for verification. Returns list of verification results."""
    client = make_openai_client(cfg)

    user_prompt = json.dumps(summaries, ensure_ascii=False, indent=2)

    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=min(4096, max(1024, len(summaries) * 120)),
    )

    raw = response.choices[0].message.content.strip()
    raw = strip_thinking_tags(raw)
    json_text = extract_json_text(raw)
    return json.loads(json_text)


def _apply_enhancements(paper_data: dict, results: list[dict]) -> dict:
    """Merge LLM verification results back into the paper dict."""
    # Build index map: order_num -> result
    result_map = {}
    for r in results:
        idx = r.get("index")
        if idx is not None:
            result_map[idx] = r

    def _enhance_question(q_item: dict) -> dict:
        order = q_item.get("order_num")
        r = result_map.get(order)
        if not r:
            return q_item

        q = q_item.get("question", {}) or {}

        # Add LLM enhancement fields
        q_item["llm_question_type"] = r.get("verified_type", "")
        q_item["llm_correct_answer"] = r.get("verified_answer", "")
        q_item["type_confidence"] = r.get("type_confidence", 0.5)
        q_item["answer_confidence"] = r.get("answer_confidence", 0.5)
        q_item["issues"] = r.get("issues", [])

        # Auto-apply LLM results when regex had no answer and LLM is confident
        if not q.get("correct_answer") and r.get("verified_answer"):
            q["correct_answer"] = r["verified_answer"]

        # Auto-apply type correction when LLM is very confident
        llm_type = r.get("verified_type", "")
        if llm_type and llm_type != q.get("question_type") and r.get("type_confidence", 0) >= 0.9:
            q_item["llm_type_differs"] = True

        return q_item

    # Process all questions
    for sec in paper_data.get("paper", {}).get("sections", []):
        sec["questions"] = [_enhance_question(q) for q in sec.get("questions", [])]

    unsectioned = paper_data.get("paper", {}).get("unsectioned_questions", [])
    paper_data["paper"]["unsectioned_questions"] = [_enhance_question(q) for q in unsectioned]

    return paper_data


def enhance_parsed_paper(parsed: dict) -> dict:
    """Enhance a regex-parsed paper dict with LLM verification.

    Args:
        parsed: Output from parse_word_paper(), standard paper format.

    Returns:
        Same dict with per-question LLM enhancement fields added.
        Top-level 'llm_enhanced' flag indicates whether LLM was used.
    """
    cfg = get_llm_config_sync("paper_import")
    if cfg.api_key == "your-api-key":
        logger.info("Paper import LLM not configured, skipping enhancement")
        parsed["llm_enhanced"] = False
        return parsed

    # Collect all questions with section context
    all_summaries = []
    paper = parsed.get("paper", {})

    for sec in paper.get("sections", []):
        sec_title = sec.get("title", "")
        summaries = _build_question_summary(sec.get("questions", []), sec_title)
        all_summaries.extend(summaries)

    unsectioned = paper.get("unsectioned_questions", [])
    if unsectioned:
        summaries = _build_question_summary(unsectioned, "")
        all_summaries.extend(summaries)

    if not all_summaries:
        parsed["llm_enhanced"] = False
        return parsed

    try:
        # Batch if needed
        all_results = []
        num_batches = math.ceil(len(all_summaries) / BATCH_SIZE)

        for i in range(num_batches):
            batch = all_summaries[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
            batch_results = _call_llm(batch, cfg)
            if isinstance(batch_results, list):
                all_results.extend(batch_results)

        parsed = _apply_enhancements(parsed, all_results)
        parsed["llm_enhanced"] = True

        # Count issues for logging
        total_issues = sum(
            1 for sec in paper.get("sections", [])
            for q in sec.get("questions", [])
            if q.get("issues")
        )
        total_issues += sum(1 for q in unsectioned if q.get("issues"))

        logger.info(
            f"Paper LLM enhancement complete: {len(all_summaries)} questions, "
            f"{len(all_results)} results, {total_issues} issues found"
        )

    except Exception as e:
        logger.warning(f"Paper LLM enhancement failed, using regex-only: {e}")
        parsed["llm_enhanced"] = False

    return parsed
