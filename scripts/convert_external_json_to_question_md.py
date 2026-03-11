#!/usr/bin/env python3
"""Convert external question JSON files into importable Markdown.

Target format matches the project's `/api/v1/questions/batch/import-md` parser.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "fill_blank": "填空题",
    "short_answer": "简答题",
    "essay": "论述题",
    "sjt": "情境判断题",
}

TYPE_MAP = {
    "judgment": "true_false",
    "judge": "true_false",
    "single": "single_choice",
    "multi_choice": "multiple_choice",
    "short": "short_answer",
}

DIFFICULTY_MAP = {
    "easy": 2,
    "medium": 3,
    "hard": 4,
}

DIMENSION_MAP = {
    "AI伦理": "AI伦理安全",
    "AI知识": "AI基础知识",
}

OPTION_PREFIX_RE = re.compile(r"^\s*([A-H])[\.\、\)\]:：]\s*(.+?)\s*$")
ANSWER_PREFIX_RE = re.compile(r"^\s*(参考答案|答案|答)[:：]\s*")


def load_questions(input_path: Path) -> list[dict]:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        return data["questions"]
    if isinstance(data, list):
        return data
    raise ValueError("输入 JSON 结构不支持：需要顶层 list 或包含 questions 数组的 dict")


def map_question_type(raw_type: str) -> str:
    question_type = TYPE_MAP.get((raw_type or "").strip(), (raw_type or "").strip())
    if question_type not in TYPE_LABELS:
        raise ValueError(f"不支持的题型: {raw_type}")
    return question_type


def map_difficulty(raw_difficulty) -> int:
    if isinstance(raw_difficulty, int):
        return min(max(raw_difficulty, 1), 5)
    if isinstance(raw_difficulty, str):
        raw = raw_difficulty.strip().lower()
        if raw in DIFFICULTY_MAP:
            return DIFFICULTY_MAP[raw]
        if raw.isdigit():
            return min(max(int(raw), 1), 5)
    return 3


def map_dimension(metric_l1: str | None, metric_l2: str | None, metric_l3: str | None) -> str | None:
    if not metric_l1:
        return None
    if metric_l1 in DIMENSION_MAP:
        return DIMENSION_MAP[metric_l1]
    if metric_l1 == "AI能力":
        text = " ".join(x for x in [metric_l2, metric_l3] if x)
        if any(k in text for k in ("角色定位", "认知", "判断", "评估")):
            return "AI批判思维"
        if any(k in text for k in ("开发", "运维", "工具", "工作流", "实践", "编程")):
            return "AI创新实践"
        return "AI技术应用"
    return None


def build_knowledge_tags(item: dict) -> list[str] | None:
    tags = []
    for key in ("metric_id", "metric_l1", "metric_l2", "metric_l3"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())
    return tags or None


def parse_choice_option(text: str, index: int) -> tuple[str, str]:
    match = OPTION_PREFIX_RE.match(text or "")
    if match:
        return match.group(1).upper(), match.group(2).strip()
    letter = chr(ord("A") + index)
    return letter, (text or "").strip()


def normalize_options(question_type: str, raw_options) -> dict | None:
    if question_type in {"essay", "short_answer", "fill_blank"}:
        return None

    if question_type == "true_false":
        return {"A": "正确", "B": "错误"}

    if isinstance(raw_options, dict):
        normalized = {}
        for i, (key, value) in enumerate(raw_options.items()):
            letter = (key or "").strip().upper()
            if not letter or len(letter) != 1 or not ("A" <= letter <= "H"):
                letter = chr(ord("A") + i)
            text = str(value).strip()
            match = OPTION_PREFIX_RE.match(text)
            normalized[letter] = match.group(2).strip() if match else text
        return normalized or None

    if isinstance(raw_options, list):
        normalized = {}
        for i, item in enumerate(raw_options):
            letter, text = parse_choice_option(str(item), i)
            normalized[letter] = text
        return normalized or None

    return None


def normalize_answer(question_type: str, raw_answer, options: dict | None) -> str:
    answer = "" if raw_answer is None else str(raw_answer).strip()
    if question_type == "true_false":
        if answer in {"A", "正确", "对", "true", "True"}:
            return "A"
        if answer in {"B", "错误", "错", "false", "False"}:
            return "B"
        return "A"

    if question_type in {"essay", "short_answer", "fill_blank"}:
        return ANSWER_PREFIX_RE.sub("", answer).strip()

    letters = re.findall(r"[A-H]", answer.upper())
    if letters:
        deduped = sorted(set(letters))
        if question_type == "single_choice":
            return deduped[0]
        return "".join(deduped)

    if options:
        for key, value in options.items():
            if answer == value:
                return key

    return answer


def build_rubric(item: dict) -> dict | None:
    import_meta = {}
    field_names = (
        "question_id",
        "metric_id",
        "metric_l1",
        "metric_l2",
        "metric_l3",
        "applicable_library_types",
        "applicable_roles",
        "applicable_levels",
        "source_doc",
        "source_locator",
        "source_snippet",
        "generation_meta",
    )
    for field_name in field_names:
        value = item.get(field_name)
        if value not in (None, "", [], {}):
            import_meta[field_name] = value
    return {"import_meta": import_meta} if import_meta else None


def convert_question(item: dict) -> dict:
    question_type = map_question_type(str(item.get("question_type", "")).strip())
    options = normalize_options(question_type, item.get("options"))
    correct_answer = normalize_answer(question_type, item.get("answer"), options)

    explanation = str(item.get("explanation") or "").strip()
    if not explanation:
        explanation = f"本题正确答案为 {correct_answer}。"

    converted = {
        "question_type": question_type,
        "stem": str(item.get("question") or "").strip(),
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "difficulty": map_difficulty(item.get("difficulty")),
        "dimension": map_dimension(item.get("metric_l1"), item.get("metric_l2"), item.get("metric_l3")),
        "knowledge_tags": build_knowledge_tags(item),
        "rubric": build_rubric(item),
    }

    if not converted["stem"]:
        raise ValueError("题干为空")

    return converted


def question_to_markdown(question: dict, index: int) -> list[str]:
    meta = {
        "question_type": question["question_type"],
        "difficulty": question["difficulty"],
        "status": "draft",
    }
    if question.get("dimension"):
        meta["dimension"] = question["dimension"]
    if question.get("knowledge_tags"):
        meta["knowledge_tags"] = question["knowledge_tags"]

    lines = [
        "---",
        "",
        f"## 第 {index} 题",
        "",
        f"<!-- meta: {json.dumps(meta, ensure_ascii=False)} -->",
        "",
        f"**题型：** {TYPE_LABELS[question['question_type']]}",
        "",
        f"**题干：** {question['stem']}",
        "",
    ]

    options = question.get("options")
    if options:
        lines.extend([
            "| 选项 | 内容 |",
            "|------|------|",
        ])
        for key in sorted(options):
            lines.append(f"| {key} | {options[key]} |")
        lines.append("")

    lines.extend([
        f"**正确答案：** {question['correct_answer']}",
        "",
        f"**解析：** {question['explanation']}",
        "",
    ])

    rubric = question.get("rubric")
    if rubric:
        lines.append(f"**评分标准：** {json.dumps(rubric, ensure_ascii=False)}")
        lines.append("")

    return lines


def render_markdown(questions: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# AI素养题库导出",
        f"> 导出时间: {now}",
        f"> 题目数量: {len(questions)}",
        "",
    ]
    for index, question in enumerate(questions, 1):
        lines.extend(question_to_markdown(question, index))
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将外部题目 JSON 转换为 ai-literacy-platform 可导入的 Markdown"
    )
    parser.add_argument("input", type=Path, help="输入 JSON 文件路径")
    parser.add_argument("output", type=Path, help="输出 Markdown 文件路径")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    raw_questions = load_questions(args.input)
    converted = []
    skipped = 0

    for item in raw_questions:
        try:
            converted.append(convert_question(item))
        except Exception as exc:
            skipped += 1
            print(f"[WARN] 跳过题目: {exc}")

    markdown = render_markdown(converted)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    print(f"[OK] 已写入: {args.output}")
    print(f"[OK] 成功转换: {len(converted)}")
    print(f"[OK] 跳过数量: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
