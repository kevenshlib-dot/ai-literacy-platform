"""add_system_configs_table

Revision ID: b65dddd8fdaa
Revises: e08fd89ac436
Create Date: 2026-04-07 22:24:45.763275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql


# revision identifiers, used by Alembic.
revision: str = 'b65dddd8fdaa'
down_revision: Union[str, None] = 'e08fd89ac436'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_configs',
        sa.Column('key', sa.String(length=100), primary_key=True),
        sa.Column('value', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('system_configs')
