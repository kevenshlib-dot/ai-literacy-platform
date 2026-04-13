"""Paper parsing enhancement agent - uses LLM to verify and correct regex-parsed paper structure.

Takes the output of parse_word_paper() (regex-based) and enhances it with:
- Question type verification/correction
- Answer inference when regex extraction failed
- Confidence scores and issue flags per question
"""
import asyncio
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.core.llm_config import get_llm_config_sync, make_openai_client
from app.agents.llm_utils import extract_json_text, strip_thinking_tags

_executor = ThreadPoolExecutor(max_workers=2)

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

SYSTEM_PROMPT = """/no_think
你是试卷结构验证工具。直接输出JSON数组，不要解释。

输入：题目数组（含 index, detected_type, stem, options, detected_answer）
输出：验证结果数组

题型：true_false(T/F), single_choice(单字母), multiple_choice(多字母), fill_blank, short_answer
规则：如果 detected_type 和 detected_answer 看起来合理，直接确认；只在明显错误时修正。

输出格式（严格JSON数组，无其他文字）：
[{"index":1,"verified_type":"true_false","verified_answer":"T","type_confidence":0.9,"answer_confidence":0.9,"issues":[]}]"""


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


LLM_TIMEOUT = 120  # seconds — local models may be slow


def _call_llm(summaries: list[dict], cfg) -> list[dict]:
    """Send question summaries to LLM for verification. Returns list of verification results."""
    # Use a dedicated client with generous timeout for local models
    client = make_openai_client(cfg, timeout=LLM_TIMEOUT)

    # Only send questions that actually need LLM help (missing answer or uncertain type)
    # This reduces token count and speeds up response significantly
    needs_help = [s for s in summaries if not s.get("detected_answer") or not s.get("detected_type")]
    to_send = needs_help if needs_help else summaries[:10]  # limit if all look fine

    if not to_send:
        # All questions have type and answer — no LLM needed
        return [{"index": s["index"], "verified_type": s["detected_type"],
                 "verified_answer": s["detected_answer"],
                 "type_confidence": 0.95, "answer_confidence": 0.95, "issues": []}
                for s in summaries]

    user_prompt = json.dumps(to_send, ensure_ascii=False)  # compact, no indent

    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=max(4096, len(to_send) * 200),
    )

    # Handle None content (Qwen thinking mode may put all tokens in reasoning)
    raw = response.choices[0].message.content or ""
    raw = raw.strip()

    if not raw:
        reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
        if reasoning:
            raw = reasoning.strip()

    if not raw:
        logger.warning(f"LLM returned empty content (finish_reason={response.choices[0].finish_reason})")
        return []

    raw = strip_thinking_tags(raw)
    json_text = extract_json_text(raw)
    results = json.loads(json_text)

    # For questions we didn't send to LLM, create pass-through results
    sent_indices = {s["index"] for s in to_send}
    for s in summaries:
        if s["index"] not in sent_indices:
            results.append({
                "index": s["index"], "verified_type": s["detected_type"],
                "verified_answer": s["detected_answer"],
                "type_confidence": 0.95, "answer_confidence": 0.95, "issues": [],
            })

    return results


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

        # Normalize LLM returned type to valid values
        VALID_TYPES = {"true_false", "single_choice", "multiple_choice", "fill_blank", "short_answer", "essay", "sjt"}
        llm_type = r.get("verified_type", "")
        if llm_type not in VALID_TYPES:
            llm_type = ""  # Discard invalid type from LLM
            q_item["llm_question_type"] = ""

        # Auto-apply LLM results when regex had no answer and LLM is confident
        if not q.get("correct_answer") and r.get("verified_answer"):
            q["correct_answer"] = r["verified_answer"]

        # Auto-apply type correction when LLM is very confident
        # But NEVER change true_false to something else (LLM often gets this wrong)
        orig_type = q.get("question_type", "")
        if llm_type and llm_type != orig_type and r.get("type_confidence", 0) >= 0.9:
            # Don't override true_false → single_choice (common LLM mistake for T/F with options)
            if orig_type == "true_false" and llm_type in ("single_choice", "multiple_choice"):
                q_item["llm_type_differs"] = False  # Ignore this suggestion
            else:
                q_item["llm_type_differs"] = True

        return q_item

    # Process all questions
    for sec in paper_data.get("paper", {}).get("sections", []):
        sec["questions"] = [_enhance_question(q) for q in sec.get("questions", [])]

    unsectioned = paper_data.get("paper", {}).get("unsectioned_questions", [])
    paper_data["paper"]["unsectioned_questions"] = [_enhance_question(q) for q in unsectioned]

    return paper_data


def _enhance_sync(parsed: dict) -> dict:
    """Synchronous implementation of enhance_parsed_paper (runs in thread pool)."""
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


async def enhance_parsed_paper(parsed: dict) -> dict:
    """Async wrapper: runs LLM enhancement in a thread pool to avoid blocking the event loop.

    This is critical — synchronous OpenAI client calls block the entire uvicorn event loop,
    making all pages unresponsive during LLM processing.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _enhance_sync, parsed)
