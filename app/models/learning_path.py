"""Models for adaptive learning engine."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LearningPathStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class LearningPath(Base):
    """A personalized learning path generated for a user."""
    __tablename__ = "learning_paths"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(LearningPathStatus, values_callable=lambda x: [e.value for e in x]), default=LearningPathStatus.ACTIVE
    )
    weakness_dimensions: Mapped[dict] = mapped_column(JSONB, nullable=True)
    target_dimensions: Mapped[dict] = mapped_column(JSONB, nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    steps: Mapped[list["LearningStep"]] = relationship(
        back_populates="path", order_by="LearningStep.order_num"
    )


class LearningStepType(str, enum.Enum):
    COURSE = "course"
    PRACTICE = "practice"
    ASSESSMENT = "assessment"


class LearningStepStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class LearningStep(Base):
    """A single step in a learning path."""
    __tablename__ = "learning_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    path_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_num: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(
        Enum(LearningStepType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(LearningStepStatus, values_callable=lambda x: [e.value for e in x]), default=LearningStepStatus.PENDING
    )
    score: Mapped[float] = mapped_column(Float, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    path: Mapped["LearningPath"] = relationship(back_populates="steps")
