"""merge main and saved work migration heads

Revision ID: 20260422a001
Revises: e5c3f2a4b789, 7f1a2b3c4d5e
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "20260422a001"
down_revision: Union[str, tuple[str, str], None] = ("e5c3f2a4b789", "7f1a2b3c4d5e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _enum_exists(enum_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": enum_name},
    )
    return result.fetchone() is not None


def _normalize_enum_values(
    enum_name: str,
    values: list[str],
    columns: list[tuple[str, str]],
) -> None:
    """Replace legacy uppercase PostgreSQL enums with lowercase app values."""
    existing_columns = [
        (table_name, column_name)
        for table_name, column_name in columns
        if _column_exists(table_name, column_name)
    ]
    if not existing_columns:
        return

    bind = op.get_bind()
    temp_name = f"{enum_name}_20260422"
    old_name = f"{enum_name}_old_20260422"

    bind.execute(sa.text(f'DROP TYPE IF EXISTS "{temp_name}" CASCADE'))
    bind.execute(sa.text(f'DROP TYPE IF EXISTS "{old_name}" CASCADE'))
    quoted_values = ", ".join(f"'{value}'" for value in values)
    bind.execute(sa.text(f'CREATE TYPE "{temp_name}" AS ENUM ({quoted_values})'))

    for table_name, column_name in existing_columns:
        bind.execute(sa.text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'))
        bind.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" '
                f'ALTER COLUMN "{column_name}" TYPE "{temp_name}" '
                f'USING lower("{column_name}"::text)::"{temp_name}"'
            )
        )

    if _enum_exists(enum_name):
        bind.execute(sa.text(f'ALTER TYPE "{enum_name}" RENAME TO "{old_name}"'))
    bind.execute(sa.text(f'ALTER TYPE "{temp_name}" RENAME TO "{enum_name}"'))
    bind.execute(sa.text(f'DROP TYPE IF EXISTS "{old_name}"'))


def upgrade() -> None:
    _normalize_enum_values(
        "roleenum",
        ["admin", "organizer", "examinee", "reviewer"],
        [("roles", "name")],
    )
    _normalize_enum_values(
        "examstatus",
        ["draft", "published", "closed", "archived"],
        [("exams", "status")],
    )
    _normalize_enum_values(
        "materialformat",
        ["pdf", "word", "epub", "markdown", "html", "image", "video", "audio", "csv", "json"],
        [("materials", "format")],
    )
    _normalize_enum_values(
        "materialstatus",
        ["uploaded", "parsing", "parsed", "vectorized", "failed"],
        [("materials", "status")],
    )
    _normalize_enum_values(
        "answersheetstatus",
        ["in_progress", "submitted", "scored"],
        [("answer_sheets", "status")],
    )
    _normalize_enum_values(
        "questiontype",
        ["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer", "essay", "sjt"],
        [("questions", "question_type")],
    )
    _normalize_enum_values(
        "bloomlevel",
        ["remember", "understand", "apply", "analyze", "evaluate", "create"],
        [("questions", "bloom_level")],
    )
    _normalize_enum_values(
        "questionstatus",
        ["draft", "pending_review", "approved", "rejected", "archived"],
        [("questions", "status")],
    )


def downgrade() -> None:
    # This merge revision normalizes deployed schemas from two production lines.
    # Downgrading enum rewrites is intentionally unsupported.
    pass
