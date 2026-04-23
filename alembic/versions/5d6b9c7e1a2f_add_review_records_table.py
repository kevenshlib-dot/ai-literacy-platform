"""add review_records table

Revision ID: 5d6b9c7e1a2f
Revises: e08fd89ac436
Create Date: 2026-03-10 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5d6b9c7e1a2f"
down_revision: Union[str, None] = "e08fd89ac436"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "review_records" not in inspector.get_table_names():
        op.create_table(
            "review_records",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("question_id", sa.UUID(), nullable=False),
            sa.Column("reviewer_id", sa.UUID(), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("ai_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_review_records_question_id"), "review_records", ["question_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "review_records" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("review_records")}
        index_name = op.f("ix_review_records_question_id")
        if index_name in indexes:
            op.drop_index(index_name, table_name="review_records")
        op.drop_table("review_records")
