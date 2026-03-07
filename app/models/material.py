import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Enum, DateTime, ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MaterialFormat(str, enum.Enum):
    PDF = "pdf"
    WORD = "word"
    MARKDOWN = "markdown"
    HTML = "html"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CSV = "csv"
    JSON = "json"


class MaterialStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    VECTORIZED = "vectorized"
    FAILED = "failed"


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        Index("ix_materials_status_category", "status", "category"),
        Index("ix_materials_format_status", "format", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(
        Enum(MaterialFormat), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(MaterialStatus), default=MaterialStatus.UPLOADED
    )
    category: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=True)
    metadata_extra: Mapped[dict] = mapped_column(JSONB, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
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

    knowledge_units: Mapped[list["KnowledgeUnit"]] = relationship(
        back_populates="material"
    )


class KnowledgeUnit(Base):
    __tablename__ = "knowledge_units"
    __table_args__ = (
        Index("ix_knowledge_units_material_dimension", "material_id", "dimension"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=True)
    keywords: Mapped[dict] = mapped_column(JSONB, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=True)
    vector_id: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    material: Mapped["Material"] = relationship(back_populates="knowledge_units")
