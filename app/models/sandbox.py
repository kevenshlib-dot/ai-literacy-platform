"""Models for practice sandbox - prompt engineering & AI tool simulation."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SandboxType(str, enum.Enum):
    PROMPT_ENGINEERING = "prompt_engineering"
    AI_TOOL_SIMULATION = "ai_tool_simulation"
    CODE_GENERATION = "code_generation"
    DATA_ANALYSIS = "data_analysis"


class SandboxSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SandboxSession(Base):
    """A practice sandbox session."""
    __tablename__ = "sandbox_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    sandbox_type: Mapped[str] = mapped_column(
        Enum(SandboxType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    task_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(
        Enum(SandboxSessionStatus, values_callable=lambda x: [e.value for e in x]), default=SandboxSessionStatus.ACTIVE
    )
    evaluation: Mapped[dict] = mapped_column(JSONB, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempts: Mapped[list["SandboxAttempt"]] = relationship(
        back_populates="session", order_by="SandboxAttempt.attempt_number"
    )


class SandboxAttempt(Base):
    """A single attempt within a sandbox session."""
    __tablename__ = "sandbox_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sandbox_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    ai_output: Mapped[str] = mapped_column(Text, nullable=True)
    feedback: Mapped[dict] = mapped_column(JSONB, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["SandboxSession"] = relationship(back_populates="attempts")
