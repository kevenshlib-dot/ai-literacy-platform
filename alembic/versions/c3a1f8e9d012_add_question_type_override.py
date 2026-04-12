"""add question_type_override to paper_questions and exam_questions

Revision ID: c3a1f8e9d012
Revises: b65dddd8fdaa
Create Date: 2026-04-08 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3a1f8e9d012'
down_revision = 'b65dddd8fdaa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()

    # paper_questions may not exist yet if running from scratch
    # (created by later migration e5c3f2a4b789_sync_all)
    if 'paper_questions' in tables:
        cols = [c['name'] for c in inspector.get_columns('paper_questions')]
        if 'question_type_override' not in cols:
            op.add_column('paper_questions',
                sa.Column('question_type_override', sa.String(50), nullable=True)
            )

    if 'exam_questions' in tables:
        cols = [c['name'] for c in inspector.get_columns('exam_questions')]
        if 'question_type_override' not in cols:
            op.add_column('exam_questions',
                sa.Column('question_type_override', sa.String(50), nullable=True)
            )


def downgrade() -> None:
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if 'exam_questions' in tables:
        op.drop_column('exam_questions', 'question_type_override')
    if 'paper_questions' in tables:
        op.drop_column('paper_questions', 'question_type_override')
