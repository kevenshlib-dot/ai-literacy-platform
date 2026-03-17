"""add_epub_to_material_format

Revision ID: 9c3d8f1a6b2e
Revises: 5d6b9c7e1a2f
Create Date: 2026-03-16 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c3d8f1a6b2e"
down_revision: Union[str, None] = "5d6b9c7e1a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE materialformat ADD VALUE IF NOT EXISTS 'EPUB'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be dropped safely in-place.
    pass
