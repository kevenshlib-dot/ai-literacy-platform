from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    question_type: str
    stem: str
    options: Optional[dict] = None
    correct_answer: str
    explanation: Optional[str] = None
    rubric: Optional[dict] = None
    difficulty: int = Field(default=3, ge=1, le=5)
    dimension: Optional[str] = None
    knowledge_tags: Optional[list] = None
    bloom_level: Optional[str] = None
    source_material_id: Optional[UUID] = None
    source_knowledge_unit_id: Optional[UUID] = None


class QuestionUpdate(BaseModel):
    stem: Optional[str] = None
    options: Optional[dict] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    rubric: Optional[dict] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    dimension: Optional[str] = None
    knowledge_tags: Optional[list] = None
    bloom_level: Optional[str] = None


class QuestionResponse(BaseModel):
    id: UUID
    question_type: str
    stem: str
    options: Optional[dict] = None
    correct_answer: str
    explanation: Optional[str] = None
    rubric: Optional[dict] = None
    difficulty: int
    dimension: Optional[str] = None
    knowledge_tags: Optional[list] = None
    bloom_level: Optional[str] = None
    source_material_id: Optional[UUID] = None
    source_knowledge_unit_id: Optional[UUID] = None
    status: str
    usage_count: int
    correct_rate: Optional[float] = None
    discrimination: Optional[float] = None
    review_comment: Optional[str] = None
    created_by: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    total: int
    items: List[QuestionResponse]


class GenerateRequest(BaseModel):
    """Request to generate questions from a knowledge unit."""
    knowledge_unit_id: UUID
    question_types: List[str] = Field(
        default=["single_choice"],
        description="Types of questions to generate",
    )
    count: int = Field(default=3, ge=1, le=10)
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    """Request to generate questions from a material's knowledge units."""
    question_types: List[str] = Field(default=["single_choice"])
    count_per_unit: int = Field(default=2, ge=1, le=5)
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    max_units: int = Field(default=10, ge=1, le=50)


class GenerateResponse(BaseModel):
    generated: int
    questions: List[QuestionResponse]


class ReviewRequest(BaseModel):
    action: str = Field(description="approve or reject")
    comment: Optional[str] = None


class BatchReviewRequest(BaseModel):
    question_ids: List[UUID]
    action: str = Field(description="approve or reject")
    comment: Optional[str] = None


class BatchSubmitRequest(BaseModel):
    question_ids: List[UUID]


class BatchDeleteRequest(BaseModel):
    question_ids: List[UUID]


class BatchExportRequest(BaseModel):
    question_ids: List[UUID]


class ReviewRecordResponse(BaseModel):
    id: UUID
    question_id: UUID
    reviewer_id: UUID
    action: str
    comment: Optional[str] = None
    ai_scores: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIReviewResponse(BaseModel):
    scores: dict
    overall_score: float
    recommendation: str
    comments: str


class QuestionBankBuildRequest(BaseModel):
    """Request to build question bank from a material with type distribution."""
    type_distribution: dict = Field(
        description="Question type to count mapping, e.g. {'single_choice': 10, 'true_false': 5}",
    )
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    max_units: int = Field(default=10, ge=1, le=50)
    custom_prompt: Optional[str] = Field(default=None, max_length=500)


class FreeGenerateRequest(BaseModel):
    """Request to generate questions without material, using LLM knowledge."""
    type_distribution: dict = Field(
        description="Question type to count mapping",
    )
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    custom_prompt: Optional[str] = Field(default=None, max_length=500)


class QuestionBankSuggestResponse(BaseModel):
    """Response with auto-suggested type distribution for a material."""
    material_id: UUID
    material_title: str
    total_units: int
    suggested_distribution: dict
    suggested_total: int
    difficulty: int
