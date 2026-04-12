import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Enum, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PaperStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(PaperStatus), default=PaperStatus.DRAFT
    )
    total_score: Mapped[float] = mapped_column(Float, default=0)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=True)
    metadata_extra: Mapped[dict] = mapped_column(JSONB, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sections: Mapped[list["PaperSection"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    questions: Mapped[list["PaperQuestion"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class PaperSection(Base):
    __tablename__ = "paper_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    order_num: Mapped[int] = mapped_column(Integer, nullable=False)
    score_rule: Mapped[dict] = mapped_column(JSONB, nullable=True)

    paper: Mapped["Paper"] = relationship(back_populates="sections")
    questions: Mapped[list["PaperQuestion"]] = relationship(back_populates="section")


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_sections.id", ondelete="SET NULL"), nullable=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False
    )
    order_num: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=5.0)
    options_override: Mapped[dict] = mapped_column(JSONB, nullable=True)
    stem_override: Mapped[str] = mapped_column(Text, nullable=True)
    question_type_override: Mapped[str] = mapped_column(String(50), nullable=True)
    correct_answer_override: Mapped[str] = mapped_column(Text, nullable=True)

    paper: Mapped["Paper"] = relationship(back_populates="questions")
    section: Mapped["PaperSection"] = relationship(back_populates="questions")
