"""add score_complaints table

Revision ID: d4b2e1f3a567
Revises: c3a1f8e9d012
Create Date: 2026-04-08 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'd4b2e1f3a567'
down_revision = 'c3a1f8e9d012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create complaint_status enum type
    complaint_status = sa.Enum('pending', 'accepted', 'rejected', name='complaint_status')
    complaint_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'score_complaints',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('score_detail_id', UUID(as_uuid=True), sa.ForeignKey('score_details.id'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', complaint_status, nullable=False, server_default='pending', index=True),
        sa.Column('reply', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('score_complaints')
    sa.Enum(name='complaint_status').drop(op.get_bind(), checkfirst=True)
