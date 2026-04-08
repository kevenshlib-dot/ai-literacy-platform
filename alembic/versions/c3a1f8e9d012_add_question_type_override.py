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
    # Add question_type_override to paper_questions
    op.add_column('paper_questions',
        sa.Column('question_type_override', sa.String(50), nullable=True)
    )
    # Add question_type_override to exam_questions
    op.add_column('exam_questions',
        sa.Column('question_type_override', sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('exam_questions', 'question_type_override')
    op.drop_column('paper_questions', 'question_type_override')
