import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scores.id"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(
        String(50), default="diagnostic", index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    dimension_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    strengths: Mapped[dict] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[dict] = mapped_column(JSONB, nullable=True)
    recommendations: Mapped[dict] = mapped_column(JSONB, nullable=True)
    level: Mapped[str] = mapped_column(String(50), nullable=True)
    percentile_rank: Mapped[dict] = mapped_column(JSONB, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=True)
    full_report: Mapped[dict] = mapped_column(JSONB, nullable=True)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
