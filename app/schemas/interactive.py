"""Schemas for interactive SJT scenario sessions."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class StartInteractiveRequest(BaseModel):
    scenario: str = Field(..., min_length=5, description="Scenario description")
    role_description: Optional[str] = None
    dimension: Optional[str] = None
    difficulty: int = Field(default=3, ge=1, le=5)
    max_turns: int = Field(default=6, ge=2, le=20)
    answer_sheet_id: Optional[UUID] = None
    question_id: Optional[UUID] = None


class InteractiveResponseRequest(BaseModel):
    message: str = Field(..., min_length=1)


class InteractiveTurnResponse(BaseModel):
    id: UUID
    turn_number: int
    role: str
    content: str
    ai_analysis: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InteractiveSessionResponse(BaseModel):
    id: UUID
    scenario: str
    role_description: Optional[str] = None
    dimension: Optional[str] = None
    status: str
    current_difficulty: int
    max_turns: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    final_summary: Optional[dict] = None

    model_config = {"from_attributes": True}


class InteractiveSessionDetailResponse(InteractiveSessionResponse):
    turns: List[InteractiveTurnResponse] = []


class InteractiveTurnResultResponse(BaseModel):
    turn_number: int
    ai_response: str
    analysis: Optional[dict] = None
    difficulty: int
    is_completed: bool
    summary: Optional[dict] = None
