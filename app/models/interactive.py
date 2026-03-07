"""Models for situational interactive Q&A sessions."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Enum, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InteractiveSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InteractiveSession(Base):
    """A multi-turn interactive assessment session."""
    __tablename__ = "interactive_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    answer_sheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_sheets.id"), nullable=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=True
    )
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(InteractiveSessionStatus),
        default=InteractiveSessionStatus.ACTIVE,
    )
    current_difficulty: Mapped[int] = mapped_column(Integer, default=3)
    max_turns: Mapped[int] = mapped_column(Integer, default=6)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True)
    evaluation_criteria: Mapped[dict] = mapped_column(JSONB, nullable=True)
    final_summary: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    turns: Mapped[list["InteractiveTurn"]] = relationship(
        back_populates="session", order_by="InteractiveTurn.turn_number"
    )


class InteractiveTurn(Base):
    """A single turn in an interactive session."""
    __tablename__ = "interactive_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interactive_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "system" or "user"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    difficulty_adjustment: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["InteractiveSession"] = relationship(back_populates="turns")
