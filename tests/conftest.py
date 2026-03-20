import os
from pathlib import Path

from dotenv import dotenv_values


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for key, value in dotenv_values(path).items():
        if value is not None:
            os.environ[key] = value


# Load repository-local test overrides before any app settings are imported.
_load_env_file(Path(__file__).resolve().parent.parent / ".env.test")

# Force pytest runs into testing mode before test modules import app settings.
os.environ["TESTING"] = "true"
os.environ.setdefault("TEST_POSTGRES_DB", "ai_literacy_test")
