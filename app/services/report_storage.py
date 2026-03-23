"""Helpers for storing multiple report types in Score.report."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.models.score import Score

SCORE_REPORT_KEY = "score_report"
DIAGNOSTIC_REPORT_KEY = "diagnostic_report"
REPORT_METADATA_KEY = "report_metadata"


def get_report_namespace(score: Score, key: str) -> dict | None:
    report = score.report or {}
    namespaced = report.get(key)
    if isinstance(namespaced, dict):
        return deepcopy(namespaced)

    if isinstance(report, dict) and key == DIAGNOSTIC_REPORT_KEY:
        if "radar_data" in report or "comparison" in report:
            return deepcopy(report)
    if isinstance(report, dict) and key == SCORE_REPORT_KEY:
        if "total_questions" in report or "correct_count" in report:
            return deepcopy(report)
    return None


def set_report_namespace(score: Score, key: str, value: dict) -> None:
    report = deepcopy(score.report) if isinstance(score.report, dict) else {}
    report[key] = deepcopy(value)

    metadata = report.get(REPORT_METADATA_KEY)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[key] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": 2,
    }
    report[REPORT_METADATA_KEY] = metadata
    score.report = report
