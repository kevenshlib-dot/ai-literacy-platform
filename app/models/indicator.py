"""Models for dynamic indicator proposals."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Float, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class IndicatorProposal(Base):
    """A proposed update to the assessment indicator framework."""
    __tablename__ = "indicator_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    proposal_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="new_indicator"
    )  # new_indicator, update, deprecate
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)
    source_references: Mapped[dict] = mapped_column(JSONB, nullable=True)
    research_summary: Mapped[str] = mapped_column(Text, nullable=True)
    consultant_mapping: Mapped[dict] = mapped_column(JSONB, nullable=True)
    review_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(ProposalStatus), default=ProposalStatus.DRAFT
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="system")
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
