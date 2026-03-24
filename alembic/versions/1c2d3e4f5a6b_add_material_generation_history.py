"""add material generation history

Revision ID: 1c2d3e4f5a6b
Revises: d5e6f7a8b9c0
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "1c2d3e4f5a6b"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selection_mode", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_material_generation_runs_material_created_at",
        "material_generation_runs",
        ["material_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_material_generation_runs_material_id"),
        "material_generation_runs",
        ["material_id"],
        unique=False,
    )

    op.create_table(
        "material_generation_run_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_unit_id"], ["knowledge_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["material_generation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "knowledge_unit_id",
            name="uq_material_generation_run_units_run_knowledge_unit",
        ),
    )
    op.create_index(
        "ix_material_generation_run_units_knowledge_unit_id",
        "material_generation_run_units",
        ["knowledge_unit_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_material_generation_run_units_run_id"),
        "material_generation_run_units",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_material_generation_run_units_run_id"), table_name="material_generation_run_units")
    op.drop_index("ix_material_generation_run_units_knowledge_unit_id", table_name="material_generation_run_units")
    op.drop_table("material_generation_run_units")
    op.drop_index(op.f("ix_material_generation_runs_material_id"), table_name="material_generation_runs")
    op.drop_index("ix_material_generation_runs_material_created_at", table_name="material_generation_runs")
    op.drop_table("material_generation_runs")
