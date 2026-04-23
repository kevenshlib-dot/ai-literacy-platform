from sqlalchemy.engine import make_url

from app.core.database import ensure_safe_schema_operation


class _DummyBind:
    def __init__(self, url: str):
        self.url = make_url(url)


def test_schema_operation_allows_test_database():
    bind = _DummyBind("postgresql+asyncpg://user:pass@localhost:5432/ai_literacy_test")
    ensure_safe_schema_operation(bind, "create_all")


def test_schema_operation_rejects_non_test_database():
    bind = _DummyBind("postgresql+asyncpg://user:pass@localhost:5432/ai_literacy_db")

    try:
        ensure_safe_schema_operation(bind, "drop_all")
    except RuntimeError as exc:
        assert "non-test database" in str(exc)
        assert "ai_literacy_db" in str(exc)
    else:
        raise AssertionError("expected non-test schema operation to be rejected")
