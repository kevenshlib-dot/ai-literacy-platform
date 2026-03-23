import pytest
import os
from pathlib import Path

from dotenv import dotenv_values


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for key, value in dotenv_values(path).items():
        if value is not None:
            os.environ[key] = value


_load_env_file(Path(__file__).resolve().parent.parent / ".env.test")
os.environ["TESTING"] = "true"
os.environ.setdefault("TEST_POSTGRES_DB", "ai_literacy_test")


@pytest.fixture(autouse=True)
def disable_diagnostic_llm(monkeypatch):
    """Keep tests deterministic by forcing diagnostic report fallback generation."""
    from app.services import diagnostic_service

    def _raise(*args, **kwargs):
        raise RuntimeError("diagnostic llm disabled in tests")

    monkeypatch.setattr(diagnostic_service, "generate_structured_diagnostic_sections", _raise)
