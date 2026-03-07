"""Models for material annotations."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Annotation(Base):
    """Text annotation on a knowledge unit or material."""
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    knowledge_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    annotator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    annotation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # "manual", "ai_auto", "highlight"
    content: Mapped[str] = mapped_column(Text, nullable=True)
    highlighted_text: Mapped[str] = mapped_column(Text, nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=True)
    knowledge_points: Mapped[dict] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
