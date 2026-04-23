"""Compare question generation results across multiple models."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agents.model_registry import ModelConfig, get_compare_models
from app.core.database import async_session
from app.models.material import Material
from app.services import question_service


def aggregate_question_counts_by_type(questions: list[dict]) -> dict[str, int]:
    counter = Counter()
    for question in questions:
        question_type = question.get("question_type")
        if question_type:
            counter[question_type] += 1
    return dict(sorted(counter.items()))


def aggregate_question_counts_by_dimension(questions: list[dict]) -> dict[str, int]:
    counter = Counter()
    for question in questions:
        dimension = question.get("dimension")
        if dimension:
            counter[dimension] += 1
    return dict(sorted(counter.items()))


def aggregate_answer_distribution(questions: list[dict]) -> dict[str, int]:
    counter = Counter()
    for question in questions:
        answer = question.get("correct_answer")
        if answer and question.get("question_type") in {"single_choice", "multiple_choice", "true_false"}:
            counter[str(answer)] += 1
    return dict(sorted(counter.items()))


@dataclass
class ComparisonRunConfig:
    material_ids: list[UUID]
    type_distribution: dict[str, int]
    difficulty: int
    bloom_level: Optional[str]
    custom_prompt: Optional[str]
    max_units: int
    prompt_seed: int
    model_slugs: list[str]
    output_dir: Path

    def to_dict(self) -> dict:
        return {
            "material_ids": [str(material_id) for material_id in self.material_ids],
            "type_distribution": self.type_distribution,
            "difficulty": self.difficulty,
            "bloom_level": self.bloom_level,
            "custom_prompt": self.custom_prompt,
            "max_units": self.max_units,
            "prompt_seed": self.prompt_seed,
            "model_slugs": self.model_slugs,
            "output_dir": str(self.output_dir),
        }


@dataclass
class ModelRunResult:
    model: ModelConfig
    materials: list[dict]
    questions: list[dict]
    stats: dict
    errors: list[dict]

    def to_dict(self) -> dict:
        return {
            "model": self.model.to_dict(),
            "materials": self.materials,
            "questions": self.questions,
            "stats": self.stats,
            "errors": self.errors,
        }


def build_markdown_report(
    config: ComparisonRunConfig,
    model_results: list[ModelRunResult],
) -> str:
    lines = [
        "# 多模型题库生成对比报告",
        "",
        "## 运行条件",
        "",
        f"- 素材数量: {len(config.material_ids)}",
        f"- 素材 ID: {'、'.join(str(material_id) for material_id in config.material_ids)}",
        f"- 题型分布: `{json.dumps(config.type_distribution, ensure_ascii=False, sort_keys=True)}`",
        f"- 难度: {config.difficulty}",
        f"- Bloom 层级: {config.bloom_level or '不限'}",
        f"- 自定义提示词: {config.custom_prompt or '无'}",
        f"- 最大知识单元数: {config.max_units}",
        f"- Prompt Seed: {config.prompt_seed}",
        "",
        "## 模型总览",
        "",
        "| 模型 | 题目总数 | Total Tokens | Prompt Tokens | Completion Tokens | 耗时(秒) | 错误数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in model_results:
        lines.append(
            "| {name} | {count} | {total_tokens} | {prompt_tokens} | {completion_tokens} | {duration:.2f} | {errors} |".format(
                name=result.model.display_name,
                count=len(result.questions),
                total_tokens=result.stats.get("total_tokens", 0),
                prompt_tokens=result.stats.get("prompt_tokens", 0),
                completion_tokens=result.stats.get("completion_tokens", 0),
                duration=result.stats.get("duration_seconds", 0.0),
                errors=len(result.errors),
            )
        )

    for result in model_results:
        lines.extend(
            [
                "",
                f"## 模型: {result.model.display_name}",
                "",
                f"- Provider: `{result.model.provider}`",
                f"- Model Name: `{result.model.model_name}`",
                f"- 题型分布: `{json.dumps(result.stats.get('type_counts', {}), ensure_ascii=False, sort_keys=True)}`",
                f"- 维度分布: `{json.dumps(result.stats.get('dimension_counts', {}), ensure_ascii=False, sort_keys=True)}`",
                f"- 答案分布: `{json.dumps(result.stats.get('answer_distribution', {}), ensure_ascii=False, sort_keys=True)}`",
            ]
        )
        if result.errors:
            lines.extend(["", "### 错误记录", ""])
            for error in result.errors:
                lines.append(f"- `{error['material_id']}`: {error['error']}")

        for material in result.materials:
            lines.extend(
                [
                    "",
                    f"### 素材: {material.get('material_title') or material['material_id']}",
                    "",
                    f"- Material ID: `{material['material_id']}`",
                    f"- 题目数: {len(material.get('questions', []))}",
                    f"- Type Counts: `{json.dumps(material.get('stats', {}).get('type_counts', {}), ensure_ascii=False, sort_keys=True)}`",
                ]
            )
            if material.get("error"):
                lines.append(f"- 错误: {material['error']}")
                continue

            for index, question in enumerate(material.get("questions", []), start=1):
                lines.extend(
                    [
                        "",
                        f"#### 题目 {index}",
                        "",
                        f"- 题型: `{question.get('question_type', '-')}`",
                        f"- 维度: `{question.get('dimension', '-')}`",
                        f"- 题干: {question.get('stem', '')}",
                    ]
                )
                options = question.get("options") or {}
                if options:
                    lines.append("- 选项:")
                    for key, value in options.items():
                        lines.append(f"  - {key}. {value}")
                lines.extend(
                    [
                        f"- 答案: `{question.get('correct_answer', '')}`",
                        f"- 解析: {question.get('explanation', '')}",
                    ]
                )

    return "\n".join(lines) + "\n"


def write_run_outputs(
    config: ComparisonRunConfig,
    model_results: list[ModelRunResult],
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = config.output_dir / f"{timestamp}_materials_{len(config.material_ids)}"
    models_dir = run_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_config.json").write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for result in model_results:
        (models_dir / f"{result.model.slug}.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (run_dir / "comparison.md").write_text(
        build_markdown_report(config, model_results),
        encoding="utf-8",
    )
    return run_dir


async def run_model_comparison(
    config: ComparisonRunConfig,
    model: ModelConfig,
) -> ModelRunResult:
    materials: list[dict] = []
    all_questions: list[dict] = []
    total_stats = {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "duration_seconds": 0.0,
    }
    errors: list[dict] = []

    async with async_session() as session:
        for material_id in config.material_ids:
            title_result = await session.execute(
                select(Material.title).where(Material.id == material_id)
            )
            title = title_result.scalar_one_or_none()
            try:
                result = await question_service.preview_question_bank_from_material(
                    db=session,
                    material_id=material_id,
                    type_distribution=config.type_distribution,
                    difficulty=config.difficulty,
                    bloom_level=config.bloom_level,
                    max_units=config.max_units,
                    custom_prompt=config.custom_prompt,
                    model_config=model,
                    prompt_seed=config.prompt_seed,
                )
                questions = result.get("questions", [])
                stats = result.get("stats", {})
                material_entry = {
                    "material_id": str(material_id),
                    "material_title": title,
                    "questions": questions,
                    "stats": stats,
                    "error": None,
                }
                for error_text in stats.get("errors", []):
                    errors.append({"material_id": str(material_id), "error": error_text})
                all_questions.extend(questions)
                total_stats["total_tokens"] += stats.get("total_tokens", 0)
                total_stats["prompt_tokens"] += stats.get("prompt_tokens", 0)
                total_stats["completion_tokens"] += stats.get("completion_tokens", 0)
                total_stats["duration_seconds"] += stats.get("duration_seconds", 0.0)
            except Exception as exc:  # pragma: no cover - network/runtime failures
                error = {"material_id": str(material_id), "error": str(exc)}
                errors.append(error)
                material_entry = {
                    "material_id": str(material_id),
                    "material_title": title,
                    "questions": [],
                    "stats": {
                        "type_counts": {},
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "duration_seconds": 0.0,
                    },
                    "error": str(exc),
                }
            materials.append(material_entry)

    total_stats["type_counts"] = aggregate_question_counts_by_type(all_questions)
    total_stats["dimension_counts"] = aggregate_question_counts_by_dimension(all_questions)
    total_stats["answer_distribution"] = aggregate_answer_distribution(all_questions)
    return ModelRunResult(
        model=model,
        materials=materials,
        questions=all_questions,
        stats=total_stats,
        errors=errors,
    )


async def run_comparison(config: ComparisonRunConfig) -> Path:
    model_results: list[ModelRunResult] = []
    for model in get_compare_models(config.model_slugs):
        model_results.append(await run_model_comparison(config, model))
    return write_run_outputs(config, model_results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare question generation across models")
    parser.add_argument("--material-id", action="append", required=True, dest="material_ids")
    parser.add_argument("--single-choice", type=int, default=0)
    parser.add_argument("--multiple-choice", type=int, default=0)
    parser.add_argument("--true-false", type=int, default=0)
    parser.add_argument("--fill-blank", type=int, default=0)
    parser.add_argument("--short-answer", type=int, default=0)
    parser.add_argument("--difficulty", type=int, default=3)
    parser.add_argument("--bloom-level", default=None)
    parser.add_argument("--custom-prompt", default=None)
    parser.add_argument("--max-units", type=int, default=10)
    parser.add_argument("--prompt-seed", type=int, default=42)
    parser.add_argument("--models", default=None)
    parser.add_argument(
        "--output-dir",
        default="artifacts/question-compare",
    )
    return parser.parse_args()


def build_run_config(args: argparse.Namespace) -> ComparisonRunConfig:
    type_distribution = {
        "single_choice": args.single_choice,
        "multiple_choice": args.multiple_choice,
        "true_false": args.true_false,
        "fill_blank": args.fill_blank,
        "short_answer": args.short_answer,
    }
    type_distribution = {key: value for key, value in type_distribution.items() if value > 0}
    if not type_distribution:
        raise ValueError("At least one question count must be greater than zero")

    model_slugs = (
        [slug.strip() for slug in args.models.split(",") if slug.strip()]
        if args.models
        else [model.slug for model in get_compare_models()]
    )
    return ComparisonRunConfig(
        material_ids=[UUID(value) for value in args.material_ids],
        type_distribution=type_distribution,
        difficulty=args.difficulty,
        bloom_level=args.bloom_level,
        custom_prompt=args.custom_prompt,
        max_units=args.max_units,
        prompt_seed=args.prompt_seed,
        model_slugs=model_slugs,
        output_dir=Path(args.output_dir),
    )


def main() -> None:
    config = build_run_config(parse_args())
    run_dir = asyncio.run(run_comparison(config))
    print(f"Comparison report written to {run_dir}")


if __name__ == "__main__":
    main()
