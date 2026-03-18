import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Enum, DateTime, ForeignKey, Float, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QuestionType(str, enum.Enum):
    SINGLE_CHOICE = "single_choice"     # 单选题
    MULTIPLE_CHOICE = "multiple_choice" # 多选题
    TRUE_FALSE = "true_false"           # 判断题
    FILL_BLANK = "fill_blank"           # 填空题
    SHORT_ANSWER = "short_answer"       # 简答题
    ESSAY = "essay"                     # 论述题
    SJT = "sjt"                         # 情境判断题


class QuestionStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class BloomLevel(str, enum.Enum):
    REMEMBER = "remember"       # 记忆
    UNDERSTAND = "understand"   # 理解
    APPLY = "apply"             # 应用
    ANALYZE = "analyze"         # 分析
    EVALUATE = "evaluate"       # 评价
    CREATE = "create"           # 创造


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_dimension_difficulty", "dimension", "difficulty"),
        Index("ix_questions_status_type", "status", "question_type"),
        Index("ix_questions_dimension_status_type", "dimension", "status", "question_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_type: Mapped[str] = mapped_column(
        Enum(QuestionType), nullable=False, index=True
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    rubric: Mapped[dict] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, index=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    knowledge_tags: Mapped[dict] = mapped_column(JSONB, nullable=True)
    bloom_level: Mapped[str] = mapped_column(
        Enum(BloomLevel), nullable=True
    )
    source_material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id"), nullable=True
    )
    source_knowledge_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_units.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(QuestionStatus), default=QuestionStatus.DRAFT, index=True
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_rate: Mapped[float] = mapped_column(Float, nullable=True)
    discrimination: Mapped[float] = mapped_column(Float, nullable=True)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ReviewRecord(Base):
    """Audit trail for question reviews."""
    __tablename__ = "review_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approve/reject/ai_check
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    ai_scores: Mapped[dict] = mapped_column(JSONB, nullable=True)  # AI quality check scores
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class QuestionLike(Base):
    __tablename__ = "question_likes"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id", name="uq_question_likes_question_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class QuestionFavorite(Base):
    __tablename__ = "question_favorites"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id", name="uq_question_favorites_question_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class QuestionFeedback(Base):
    __tablename__ = "question_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)  # error/unclear/wrong_answer/other
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
