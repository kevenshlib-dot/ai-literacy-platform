"""merge_score_detail_analysis_heads

Revision ID: d5e6f7a8b9c0
Revises: b2c3d4e5f6a7, c4f5e6a7b8c9
Create Date: 2026-03-20 16:10:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, tuple[str, str], None] = ('b2c3d4e5f6a7', 'c4f5e6a7b8c9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
