"""Question import/export service – Markdown format.

Export produces a human-readable Markdown file with machine-parseable
``<!-- meta: {...} -->`` comments that carry structured metadata.

Import parses the same format back, creating draft questions.
"""
import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.question import Question

logger = logging.getLogger(__name__)

# ── Markdown format helpers ──────────────────────────────────────────

_TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "fill_blank": "填空题",
    "short_answer": "简答题",
    "essay": "论述题",
    "sjt": "情境判断题",
}


def export_questions_to_md(questions: list[Question]) -> str:
    """Serialise a list of Question ORM objects to Markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "# AI素养题库导出",
        f"> 导出时间: {now}",
        f"> 题目数量: {len(questions)}",
        "",
    ]

    for idx, q in enumerate(questions, 1):
        lines.append("---")
        lines.append("")
        lines.append(f"## 第 {idx} 题")
        lines.append("")

        # ── meta JSON ──
        meta: dict = {
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
            "difficulty": q.difficulty,
        }
        if q.dimension:
            meta["dimension"] = q.dimension
        if q.knowledge_tags:
            meta["knowledge_tags"] = q.knowledge_tags
        if q.bloom_level:
            meta["bloom_level"] = q.bloom_level.value if hasattr(q.bloom_level, "value") else q.bloom_level
        status_val = q.status.value if hasattr(q.status, "value") else q.status
        meta["status"] = status_val

        lines.append(f"<!-- meta: {json.dumps(meta, ensure_ascii=False)} -->")
        lines.append("")

        # ── question type label ──
        qtype = meta["question_type"]
        lines.append(f"**题型：** {_TYPE_LABELS.get(qtype, qtype)}")
        lines.append("")

        # ── stem ──
        lines.append(f"**题干：** {q.stem}")
        lines.append("")

        # ── options (choice / true-false) ──
        if q.options and isinstance(q.options, dict) and len(q.options) > 0:
            lines.append("| 选项 | 内容 |")
            lines.append("|------|------|")
            for key in sorted(q.options.keys()):
                lines.append(f"| {key} | {q.options[key]} |")
            lines.append("")

        # ── correct answer ──
        lines.append(f"**正确答案：** {q.correct_answer}")
        lines.append("")

        # ── explanation ──
        if q.explanation:
            lines.append(f"**解析：** {q.explanation}")
            lines.append("")

        # ── rubric (for subjective questions) ──
        if q.rubric:
            lines.append(f"**评分标准：** {json.dumps(q.rubric, ensure_ascii=False)}")
            lines.append("")

    return "\n".join(lines)


# ── Import / parse ───────────────────────────────────────────────────

_META_RE = re.compile(r"<!--\s*meta:\s*(\{.*?\})\s*-->", re.DOTALL)
_STEM_RE = re.compile(r"\*\*题干[：:]\*\*\s*(.+?)(?=\n\n|\n\||\n\*\*|\Z)", re.DOTALL)
_ANSWER_RE = re.compile(r"\*\*正确答案[：:]\*\*\s*(.+)")
_EXPLAIN_RE = re.compile(r"\*\*解析[：:]\*\*\s*(.+?)(?=\n\n|\n\*\*|\n---|\Z)", re.DOTALL)
_RUBRIC_RE = re.compile(r"\*\*评分标准[：:]\*\*\s*(.+)")
_OPTION_ROW_RE = re.compile(r"\|\s*([A-Z])\s*\|\s*(.+?)\s*\|")


def parse_md_to_questions(md_content: str) -> list[dict]:
    """Parse a Markdown export back into a list of question dicts.

    Each dict is compatible with ``QuestionCreate`` schema fields.
    Status is always forced to ``draft`` regardless of what the export says.
    """
    # Split by --- separator, skip header block
    blocks = re.split(r"\n---\n", md_content)
    results: list[dict] = []

    for block in blocks:
        # Must contain a meta comment to be a valid question block
        meta_match = _META_RE.search(block)
        if not meta_match:
            continue

        try:
            meta = json.loads(meta_match.group(1))
        except json.JSONDecodeError:
            logger.warning("Skipping block with invalid meta JSON")
            continue

        # ── extract stem ──
        stem_match = _STEM_RE.search(block)
        if not stem_match:
            logger.warning("Skipping block: no stem found")
            continue
        stem = stem_match.group(1).strip()

        # ── extract correct answer ──
        ans_match = _ANSWER_RE.search(block)
        if not ans_match:
            logger.warning("Skipping block: no correct_answer found")
            continue
        correct_answer = ans_match.group(1).strip()

        # ── extract options ──
        options: Optional[dict] = None
        option_rows = _OPTION_ROW_RE.findall(block)
        if option_rows:
            options = {key: val.strip() for key, val in option_rows}

        # ── extract explanation ──
        explanation: Optional[str] = None
        expl_match = _EXPLAIN_RE.search(block)
        if expl_match:
            explanation = expl_match.group(1).strip()

        # ── extract rubric ──
        rubric: Optional[dict] = None
        rubric_match = _RUBRIC_RE.search(block)
        if rubric_match:
            try:
                rubric = json.loads(rubric_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # ── build question dict ──
        q: dict = {
            "question_type": meta.get("question_type", "single_choice"),
            "stem": stem,
            "correct_answer": correct_answer,
            "difficulty": meta.get("difficulty", 3),
        }
        if options:
            q["options"] = options
        if explanation:
            q["explanation"] = explanation
        if rubric:
            q["rubric"] = rubric
        if meta.get("dimension"):
            q["dimension"] = meta["dimension"]
        if meta.get("knowledge_tags"):
            q["knowledge_tags"] = meta["knowledge_tags"]
        if meta.get("bloom_level"):
            q["bloom_level"] = meta["bloom_level"]

        results.append(q)

    return results
