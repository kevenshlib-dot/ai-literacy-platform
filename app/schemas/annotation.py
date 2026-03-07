"""Annotation schemas."""
from datetime import datetime
from typing import Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class ManualAnnotationRequest(BaseModel):
    content: Optional[str] = None
    highlighted_text: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    dimension: Optional[str] = None
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    knowledge_unit_id: Optional[UUID] = None


class AutoAnnotateRequest(BaseModel):
    """Trigger auto-annotation for a material."""
    pass  # material_id comes from path


class AnnotationResponse(BaseModel):
    id: UUID
    material_id: UUID
    knowledge_unit_id: Optional[UUID] = None
    annotator_id: UUID
    annotation_type: str
    content: Optional[str] = None
    highlighted_text: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    dimension: Optional[str] = None
    difficulty: Optional[int] = None
    knowledge_points: Optional[Any] = None
    ai_confidence: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsistencyResponse(BaseModel):
    consistent: bool
    annotator_count: int
    conflicts: list
