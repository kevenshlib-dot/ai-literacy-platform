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
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(op.get_bind())
    tables = inspector.get_table_names()

    # score_complaints may already exist (created by sync_all migration or initial schema)
    if 'score_complaints' in tables:
        return

    # Use raw SQL to avoid SQLAlchemy auto-creating the enum (it already exists from initial schema)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE complaint_status AS ENUM ('pending', 'accepted', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS score_complaints (
            id UUID PRIMARY KEY,
            score_detail_id UUID NOT NULL REFERENCES score_details(id),
            user_id UUID NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            status complaint_status NOT NULL DEFAULT 'pending',
            reply TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_score_complaints_score_detail_id ON score_complaints(score_detail_id);
        CREATE INDEX IF NOT EXISTS ix_score_complaints_user_id ON score_complaints(user_id);
        CREATE INDEX IF NOT EXISTS ix_score_complaints_status ON score_complaints(status);
    """)


def downgrade() -> None:
    op.drop_table('score_complaints')
    sa.Enum(name='complaint_status').drop(op.get_bind(), checkfirst=True)
