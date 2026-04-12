"""sync all missing tables and columns

This migration brings alembic in sync with the actual database schema.
It creates all tables/columns that exist in SQLAlchemy models but were
never covered by a migration script. Each operation uses IF NOT EXISTS
or checks to be safely re-runnable.

Revision ID: e5c3f2a4b789
Revises: d4b2e1f3a567
Create Date: 2026-04-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import inspect as sa_inspect


revision = 'e5c3f2a4b789'
down_revision = 'd4b2e1f3a567'
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    return table_name in insp.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def _create_enum_if_not_exists(enum_name: str, values: list[str]):
    """Create a PostgreSQL enum type if it doesn't already exist."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": enum_name}
    )
    if result.fetchone() is None:
        enum = sa.Enum(*values, name=enum_name)
        enum.create(bind)


def upgrade() -> None:
    # ── 1. Create enum types ─────────────────────────────────────────────
    _create_enum_if_not_exists('paperstatus', ['draft', 'published', 'archived'])
    _create_enum_if_not_exists('interactivesessionstatus', ['active', 'completed', 'abandoned'])
    _create_enum_if_not_exists('proposalstatus', ['draft', 'submitted', 'under_review', 'approved', 'rejected'])
    _create_enum_if_not_exists('coursestatus', ['draft', 'published', 'archived'])
    _create_enum_if_not_exists('learningpathstatus', ['active', 'completed', 'abandoned'])
    _create_enum_if_not_exists('learningsteptype', ['course', 'quiz', 'practice', 'reading', 'sandbox'])
    _create_enum_if_not_exists('learningstepstatus', ['pending', 'in_progress', 'completed', 'skipped'])
    _create_enum_if_not_exists('sandboxtype', ['prompt_engineering', 'data_analysis', 'ethical_reasoning', 'tool_usage', 'creative_writing'])
    _create_enum_if_not_exists('sandboxsessionstatus', ['active', 'completed', 'abandoned'])

    # ── 2. organizations ─────────────────────────────────────────────────
    if not _table_exists('organizations'):
        op.create_table(
            'organizations',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(200), nullable=False, unique=True, index=True),
            sa.Column('slug', sa.String(100), nullable=False, unique=True, index=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('logo_url', sa.String(500), nullable=True),
            sa.Column('contact_email', sa.String(200), nullable=True),
            sa.Column('contact_phone', sa.String(50), nullable=True),
            sa.Column('config', JSONB, nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('max_users', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 3. papers ────────────────────────────────────────────────────────
    if not _table_exists('papers'):
        op.create_table(
            'papers',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('total_score', sa.Float(), nullable=False, server_default='0'),
            sa.Column('time_limit_minutes', sa.Integer(), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('tags', JSONB, nullable=True),
            sa.Column('metadata_extra', JSONB, nullable=True),
            sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 4. paper_sections ────────────────────────────────────────────────
    if not _table_exists('paper_sections'):
        op.create_table(
            'paper_sections',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('paper_id', UUID(as_uuid=True), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('order_num', sa.Integer(), nullable=False),
            sa.Column('score_rule', JSONB, nullable=True),
        )

    # ── 5. paper_questions ───────────────────────────────────────────────
    if not _table_exists('paper_questions'):
        op.create_table(
            'paper_questions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('paper_id', UUID(as_uuid=True), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('section_id', UUID(as_uuid=True), sa.ForeignKey('paper_sections.id', ondelete='SET NULL'), nullable=True),
            sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id'), nullable=False),
            sa.Column('order_num', sa.Integer(), nullable=False),
            sa.Column('score', sa.Float(), nullable=False, server_default='5.0'),
            sa.Column('options_override', JSONB, nullable=True),
            sa.Column('stem_override', sa.Text(), nullable=True),
            sa.Column('question_type_override', sa.String(50), nullable=True),
            sa.Column('correct_answer_override', sa.Text(), nullable=True),
        )

    # ── 6. interactive_sessions ──────────────────────────────────────────
    if not _table_exists('interactive_sessions'):
        op.create_table(
            'interactive_sessions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
            sa.Column('answer_sheet_id', UUID(as_uuid=True), sa.ForeignKey('answer_sheets.id'), nullable=True),
            sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id'), nullable=True),
            sa.Column('scenario', sa.Text(), nullable=False),
            sa.Column('role_description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='active'),
            sa.Column('current_difficulty', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('max_turns', sa.Integer(), nullable=False, server_default='6'),
            sa.Column('dimension', sa.String(100), nullable=True),
            sa.Column('evaluation_criteria', JSONB, nullable=True),
            sa.Column('final_summary', JSONB, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )

    # ── 7. interactive_turns ─────────────────────────────────────────────
    if not _table_exists('interactive_turns'):
        op.create_table(
            'interactive_turns',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('interactive_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('turn_number', sa.Integer(), nullable=False),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('ai_analysis', JSONB, nullable=True),
            sa.Column('difficulty_adjustment', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 8. annotations ───────────────────────────────────────────────────
    if not _table_exists('annotations'):
        op.create_table(
            'annotations',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('material_id', UUID(as_uuid=True), sa.ForeignKey('materials.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('knowledge_unit_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_units.id', ondelete='SET NULL'), nullable=True),
            sa.Column('annotator_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('annotation_type', sa.String(50), nullable=False, server_default='manual'),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('highlighted_text', sa.Text(), nullable=True),
            sa.Column('start_offset', sa.Integer(), nullable=True),
            sa.Column('end_offset', sa.Integer(), nullable=True),
            sa.Column('dimension', sa.String(100), nullable=True),
            sa.Column('difficulty', sa.Integer(), nullable=True),
            sa.Column('knowledge_points', JSONB, nullable=True),
            sa.Column('ai_confidence', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 9. indicator_proposals ───────────────────────────────────────────
    if not _table_exists('indicator_proposals'):
        op.create_table(
            'indicator_proposals',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('dimension', sa.String(100), nullable=False),
            sa.Column('proposal_type', sa.String(50), nullable=False, server_default='new_indicator'),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('rationale', sa.Text(), nullable=True),
            sa.Column('source_references', JSONB, nullable=True),
            sa.Column('research_summary', sa.Text(), nullable=True),
            sa.Column('consultant_mapping', JSONB, nullable=True),
            sa.Column('review_result', JSONB, nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('confidence_score', sa.Float(), nullable=True),
            sa.Column('created_by', sa.String(50), nullable=False, server_default='system'),
            sa.Column('reviewed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 10. courses ──────────────────────────────────────────────────────
    if not _table_exists('courses'):
        op.create_table(
            'courses',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('cover_image', sa.String(500), nullable=True),
            sa.Column('dimension', sa.String(100), nullable=True, index=True),
            sa.Column('difficulty', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('duration_minutes', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('tags', JSONB, nullable=True),
            sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 11. course_chapters ──────────────────────────────────────────────
    if not _table_exists('course_chapters'):
        op.create_table(
            'course_chapters',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('course_id', UUID(as_uuid=True), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('content_type', sa.String(50), nullable=False, server_default='text'),
            sa.Column('video_url', sa.String(500), nullable=True),
            sa.Column('order_num', sa.Integer(), nullable=False),
            sa.Column('duration_minutes', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 12. learning_paths ───────────────────────────────────────────────
    if not _table_exists('learning_paths'):
        op.create_table(
            'learning_paths',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='active'),
            sa.Column('weakness_dimensions', JSONB, nullable=True),
            sa.Column('target_dimensions', JSONB, nullable=True),
            sa.Column('progress_percent', sa.Float(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 13. learning_steps ───────────────────────────────────────────────
    if not _table_exists('learning_steps'):
        op.create_table(
            'learning_steps',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('path_id', UUID(as_uuid=True), sa.ForeignKey('learning_paths.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('order_num', sa.Integer(), nullable=False),
            sa.Column('step_type', sa.String(50), nullable=False),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('dimension', sa.String(100), nullable=True),
            sa.Column('resource_id', UUID(as_uuid=True), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )

    # ── 14. sandbox_sessions ─────────────────────────────────────────────
    if not _table_exists('sandbox_sessions'):
        op.create_table(
            'sandbox_sessions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
            sa.Column('sandbox_type', sa.String(50), nullable=False),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('task_prompt', sa.Text(), nullable=False),
            sa.Column('dimension', sa.String(100), nullable=True, index=True),
            sa.Column('difficulty', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('status', sa.String(50), nullable=False, server_default='active'),
            sa.Column('evaluation', JSONB, nullable=True),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )

    # ── 15. sandbox_attempts ─────────────────────────────────────────────
    if not _table_exists('sandbox_attempts'):
        op.create_table(
            'sandbox_attempts',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('sandbox_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('attempt_number', sa.Integer(), nullable=False),
            sa.Column('user_input', sa.Text(), nullable=False),
            sa.Column('ai_output', sa.Text(), nullable=True),
            sa.Column('feedback', JSONB, nullable=True),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 16. review_records ───────────────────────────────────────────────
    if not _table_exists('review_records'):
        op.create_table(
            'review_records',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('reviewer_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('action', sa.String(20), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('ai_scores', JSONB, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 17. Missing columns on existing tables ───────────────────────────

    # exams.paper_id
    if _table_exists('exams') and not _column_exists('exams', 'paper_id'):
        op.add_column('exams',
            sa.Column('paper_id', UUID(as_uuid=True), sa.ForeignKey('papers.id'), nullable=True)
        )

    # exam_questions.correct_answer_override
    if _table_exists('exam_questions') and not _column_exists('exam_questions', 'correct_answer_override'):
        op.add_column('exam_questions',
            sa.Column('correct_answer_override', sa.Text(), nullable=True)
        )

    # paper_questions.correct_answer_override (in case table was created without it)
    if _table_exists('paper_questions') and not _column_exists('paper_questions', 'correct_answer_override'):
        op.add_column('paper_questions',
            sa.Column('correct_answer_override', sa.Text(), nullable=True)
        )

    # reports.content, reports.period_start, reports.period_end
    if _table_exists('reports'):
        if not _column_exists('reports', 'content'):
            op.add_column('reports',
                sa.Column('content', JSONB, nullable=True)
            )
        if not _column_exists('reports', 'period_start'):
            op.add_column('reports',
                sa.Column('period_start', sa.DateTime(timezone=True), nullable=True)
            )
        if not _column_exists('reports', 'period_end'):
            op.add_column('reports',
                sa.Column('period_end', sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    # Remove added columns
    if _table_exists('reports'):
        if _column_exists('reports', 'period_end'):
            op.drop_column('reports', 'period_end')
        if _column_exists('reports', 'period_start'):
            op.drop_column('reports', 'period_start')
        if _column_exists('reports', 'content'):
            op.drop_column('reports', 'content')
    if _table_exists('paper_questions') and _column_exists('paper_questions', 'correct_answer_override'):
        op.drop_column('paper_questions', 'correct_answer_override')
    if _table_exists('exam_questions') and _column_exists('exam_questions', 'correct_answer_override'):
        op.drop_column('exam_questions', 'correct_answer_override')
    if _table_exists('exams') and _column_exists('exams', 'paper_id'):
        op.drop_column('exams', 'paper_id')

    # Drop tables in reverse dependency order
    for table in [
        'review_records', 'sandbox_attempts', 'sandbox_sessions',
        'learning_steps', 'learning_paths',
        'course_chapters', 'courses',
        'indicator_proposals', 'annotations',
        'interactive_turns', 'interactive_sessions',
        'paper_questions', 'paper_sections', 'papers',
        'organizations',
    ]:
        if _table_exists(table):
            op.drop_table(table)
