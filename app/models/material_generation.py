import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MaterialGenerationRun(Base):
    __tablename__ = "material_generation_runs"
    __table_args__ = (
        Index(
            "ix_material_generation_runs_material_created_at",
            "material_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selection_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="stable")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    selected_units: Mapped[list["MaterialGenerationRunUnit"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MaterialGenerationRunUnit(Base):
    __tablename__ = "material_generation_run_units"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "knowledge_unit_id",
            name="uq_material_generation_run_units_run_knowledge_unit",
        ),
        Index(
            "ix_material_generation_run_units_knowledge_unit_id",
            "knowledge_unit_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run: Mapped[MaterialGenerationRun] = relationship(back_populates="selected_units")
