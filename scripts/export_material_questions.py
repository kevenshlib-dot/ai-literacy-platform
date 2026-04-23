"""Export preview questions for all parsed materials to JSON files."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.core.database import async_session
from app.models.material import KnowledgeUnit, Material, MaterialStatus
from app.services import question_service


def _enum_value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _dedupe_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


@dataclass
class ExportConfig:
    type_distribution: dict[str, int]
    difficulty: int
    bloom_level: Optional[str]
    max_units: int
    selection_mode: str
    prompt_seed: int
    output_dir: Path

    @property
    def requested_total(self) -> int:
        return sum(count for count in self.type_distribution.values() if count > 0)

    def to_dict(self) -> dict:
        return {
            "type_distribution": self.type_distribution,
            "difficulty": self.difficulty,
            "bloom_level": self.bloom_level,
            "max_units": self.max_units,
            "selection_mode": self.selection_mode,
            "prompt_seed": self.prompt_seed,
            "output_dir": str(self.output_dir),
            "requested_total": self.requested_total,
            "model_name": settings.LLM_MODEL,
        }


@dataclass
class MaterialCatalogItem:
    material_id: UUID
    title: str
    status: str
    format: str
    category: Optional[str]
    knowledge_unit_count: int

    def to_dict(self) -> dict:
        return {
            "id": str(self.material_id),
            "title": self.title,
            "status": self.status,
            "format": self.format,
            "category": self.category,
            "knowledge_unit_count": self.knowledge_unit_count,
        }


@dataclass
class MaterialExportResult:
    material: MaterialCatalogItem
    export_status: str
    question_count: int
    questions: list[dict]
    stats: dict
    errors: list[str]

    def filename(self) -> str:
        return f"{self.material.material_id}.json"

    def to_dict(self, *, batch_id: str) -> dict:
        return {
            "batch_id": batch_id,
            "material": self.material.to_dict(),
            "generation_config": {},
            "export_status": self.export_status,
            "question_count": self.question_count,
            "questions": self.questions,
            "stats": self.stats,
            "errors": self.errors,
        }


def build_manifest(batch_id: str, config: ExportConfig, results: list[MaterialExportResult]) -> dict:
    success_count = sum(1 for result in results if result.export_status == "success")
    items = []
    for result in results:
        items.append(
            {
                "material_id": str(result.material.material_id),
                "title": result.material.title,
                "export_status": result.export_status,
                "question_count": result.question_count,
                "file_path": f"materials/{result.filename()}",
                "errors": result.errors,
            }
        )

    return {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "material_count": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "generation_config": config.to_dict(),
        "materials": items,
    }


def write_export_outputs(config: ExportConfig, results: list[MaterialExportResult]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_id = f"{timestamp}_materials_{len(results)}"
    run_dir = config.output_dir / batch_id
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        payload = result.to_dict(batch_id=batch_id)
        payload["generation_config"] = config.to_dict()
        (materials_dir / result.filename()).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (run_dir / "manifest.json").write_text(
        json.dumps(build_manifest(batch_id, config, results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir


def _collect_export_errors(preview_result: dict, requested_total: int) -> list[str]:
    stats = preview_result.get("stats") or {}
    generated_total = len(preview_result.get("questions") or [])
    errors = _dedupe_texts(
        list(stats.get("errors") or [])
        + list(stats.get("validation_reasons") or [])
        + list(stats.get("warnings") or [])
    )
    if generated_total != requested_total and not errors:
        errors.append(f"实际生成 {generated_total} 道题，未达到目标 {requested_total} 道")
    return errors


async def list_exportable_materials() -> list[MaterialCatalogItem]:
    async with async_session() as session:
        result = await session.execute(
            select(
                Material.id,
                Material.title,
                Material.status,
                Material.format,
                Material.category,
                func.count(KnowledgeUnit.id).label("knowledge_unit_count"),
            )
            .outerjoin(KnowledgeUnit, KnowledgeUnit.material_id == Material.id)
            .where(Material.status.in_([MaterialStatus.PARSED, MaterialStatus.VECTORIZED]))
            .group_by(Material.id)
            .order_by(Material.created_at, Material.id)
        )
        return [
            MaterialCatalogItem(
                material_id=row.id,
                title=row.title,
                status=str(_enum_value(row.status)),
                format=str(_enum_value(row.format)),
                category=row.category,
                knowledge_unit_count=int(row.knowledge_unit_count or 0),
            )
            for row in result
        ]


async def export_all_materials(config: ExportConfig) -> list[MaterialExportResult]:
    materials = await list_exportable_materials()
    if not materials:
        raise ValueError("未找到可导出的已解析素材")

    results: list[MaterialExportResult] = []
    async with async_session() as session:
        for material in materials:
            try:
                preview_result = await question_service.preview_question_bank_from_material(
                    db=session,
                    material_id=material.material_id,
                    type_distribution=config.type_distribution,
                    difficulty=config.difficulty,
                    bloom_level=config.bloom_level,
                    max_units=config.max_units,
                    selection_mode=config.selection_mode,
                    prompt_seed=config.prompt_seed,
                    record_generation_run=False,
                )
                questions = preview_result.get("questions") or []
                stats = preview_result.get("stats") or {}
                question_count = len(questions)
                export_status = "success" if question_count == config.requested_total else "failed"
                errors = [] if export_status == "success" else _collect_export_errors(
                    preview_result,
                    config.requested_total,
                )
                results.append(
                    MaterialExportResult(
                        material=material,
                        export_status=export_status,
                        question_count=question_count,
                        questions=questions if export_status == "success" else [],
                        stats=stats,
                        errors=errors,
                    )
                )
            except Exception as exc:  # pragma: no cover - runtime/network failures
                results.append(
                    MaterialExportResult(
                        material=material,
                        export_status="failed",
                        question_count=0,
                        questions=[],
                        stats={},
                        errors=[str(exc)],
                    )
                )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export material question previews to JSON")
    parser.add_argument("--single-choice", type=int, default=8)
    parser.add_argument("--multiple-choice", type=int, default=4)
    parser.add_argument("--true-false", type=int, default=4)
    parser.add_argument("--fill-blank", type=int, default=2)
    parser.add_argument("--short-answer", type=int, default=2)
    parser.add_argument("--difficulty", type=int, default=3)
    parser.add_argument("--bloom-level", default=None)
    parser.add_argument("--max-units", type=int, default=10)
    parser.add_argument("--selection-mode", choices=["stable", "coverage"], default="stable")
    parser.add_argument("--prompt-seed", type=int, default=42)
    parser.add_argument("--output-dir", default="artifacts/question-compare")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ExportConfig:
    type_distribution = {
        "single_choice": args.single_choice,
        "multiple_choice": args.multiple_choice,
        "true_false": args.true_false,
        "fill_blank": args.fill_blank,
        "short_answer": args.short_answer,
    }
    type_distribution = {
        question_type: count
        for question_type, count in type_distribution.items()
        if count > 0
    }
    if not type_distribution:
        raise ValueError("至少需要一种题型且数量大于 0")

    return ExportConfig(
        type_distribution=type_distribution,
        difficulty=args.difficulty,
        bloom_level=args.bloom_level,
        max_units=args.max_units,
        selection_mode=args.selection_mode,
        prompt_seed=args.prompt_seed,
        output_dir=Path(args.output_dir),
    )


async def run_export(config: ExportConfig) -> Path:
    results = await export_all_materials(config)
    return write_export_outputs(config, results)


def main() -> None:
    config = build_config(parse_args())
    run_dir = asyncio.run(run_export(config))
    print(f"Export written to {run_dir}")


if __name__ == "__main__":
    main()
