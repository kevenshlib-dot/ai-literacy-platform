"""add_score_detail_analysis

Revision ID: c4f5e6a7b8c9
Revises: e08fd89ac436
Create Date: 2026-03-20 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4f5e6a7b8c9'
down_revision: Union[str, None] = 'e08fd89ac436'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('score_details', sa.Column('analysis', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('score_details', 'analysis')
