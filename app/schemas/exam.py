from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    title: str
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    total_score: float = 100.0


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    total_score: Optional[float] = None


class ExamQuestionItem(BaseModel):
    question_id: UUID
    order_num: int
    score: float = 5.0


class ManualAssembleRequest(BaseModel):
    """Manually add questions to an exam."""
    questions: List[ExamQuestionItem]


class AutoAssembleRequest(BaseModel):
    """Auto-assemble an exam based on strategy constraints."""
    type_distribution: dict = Field(
        default={"single_choice": 10},
        description="Question type to count mapping, e.g. {'single_choice': 10, 'true_false': 5}",
    )
    difficulty_target: int = Field(default=3, ge=1, le=5)
    difficulty_tolerance: int = Field(default=1, ge=0, le=2)
    dimensions: Optional[List[str]] = Field(
        default=None,
        description="Knowledge dimensions to cover. None = any dimension.",
    )
    dimension_weights: Optional[dict[str, int]] = Field(
        default=None,
        description="Five fixed knowledge dimensions mapped to ratio weights.",
    )
    score_per_question: float = Field(default=5.0)
    exclude_question_ids: Optional[List[UUID]] = None
    audience_type: Optional[Literal["all", "librarian", "researcher_teacher", "college_student"]] = Field(
        default="all",
        description="Target audience hint for assembly.",
    )
    library_types: Optional[List[Literal["public", "university", "research"]]] = Field(
        default=None,
        description="Optional library types when audience is librarian.",
    )
    job_type: Optional[Literal["general", "technical", "service"]] = Field(
        default=None,
        description="Optional job type when audience is librarian.",
    )
    requirements_prompt: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Free-form detailed requirements for paper generation.",
    )
    difficulty_preset: Optional[Literal["newbie", "backbone", "expert", "custom"]] = Field(
        default=None,
        description="Named difficulty preset shown in UI.",
    )


class ExamQuestionResponse(BaseModel):
    id: UUID
    question_id: UUID
    order_num: int
    score: float

    model_config = {"from_attributes": True}


class ExamQuestionSummaryResponse(BaseModel):
    id: UUID
    question_type: str
    stem: str
    options: Optional[dict] = None
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: int
    dimension: Optional[str] = None
    status: str


class ExamCompositionItemResponse(ExamQuestionResponse):
    question: ExamQuestionSummaryResponse


class ExamCompositionUpdateRequest(BaseModel):
    items: List[ExamQuestionItem]


class ExamResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    status: str
    total_score: float
    time_limit_minutes: Optional[int] = None
    params: Optional[dict] = None
    usage_count: int = 0
    avg_score: Optional[float] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExamDetailResponse(ExamResponse):
    questions: List[ExamQuestionResponse] = []


class ExamCompositionResponse(BaseModel):
    exam: ExamResponse
    items: List[ExamCompositionItemResponse]


class ExamListResponse(BaseModel):
    total: int
    items: List[ExamResponse]


class AssembleResponse(BaseModel):
    exam_id: UUID
    total_questions: int
    total_score: float
    questions: List[ExamQuestionResponse]


class IntentAssembleRequest(BaseModel):
    """Natural language description for intelligent assembly."""
    description: str = Field(
        ...,
        description="Natural language description, e.g. '给新员工出一份20题的入门测试'",
        min_length=2,
    )


class IntentParseResponse(BaseModel):
    """Parsed intent parameters from natural language."""
    title: str
    total_questions: int
    difficulty: int
    time_limit_minutes: Optional[int] = None
    dimensions: Optional[List[str]] = None
    type_distribution: dict
    score_per_question: float = 5.0
    description: Optional[str] = None


class IntentAssembleResponse(BaseModel):
    """Response for intent-based assembly."""
    parsed_params: IntentParseResponse
    exam: ExamResponse
    assembly: AssembleResponse
