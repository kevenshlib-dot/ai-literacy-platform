from datetime import datetime
from typing import Literal, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class PromptOverrideMixin(BaseModel):
    system_prompt: Optional[str] = Field(default=None, max_length=20000)
    user_prompt_template: Optional[str] = Field(default=None, max_length=20000)
    prompt_seed: Optional[int] = None


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
    source_material_title: Optional[str] = None
    source_knowledge_unit_title: Optional[str] = None
    source_knowledge_unit_excerpt: Optional[str] = None
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


class GenerateRequest(PromptOverrideMixin):
    """Request to generate questions from a knowledge unit."""
    knowledge_unit_id: UUID
    question_types: List[str] = Field(
        default=["single_choice"],
        description="Types of questions to generate",
    )
    count: int = Field(default=3, ge=1, le=10)
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None


class BatchGenerateRequest(PromptOverrideMixin):
    """Request to generate questions from a material's knowledge units."""
    question_types: List[str] = Field(default=["single_choice"])
    count_per_unit: int = Field(default=2, ge=1, le=5)
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    max_units: int = Field(default=10, ge=1, le=50)
    selection_mode: Literal["stable", "coverage"] = "stable"


class GenerateStats(BaseModel):
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_seconds: float = 0.0
    type_counts: dict = Field(default_factory=dict)
    fallback_count: int = 0
    errors: List[str] = Field(default_factory=list)
    generation_attempts: int = 0
    validation_reasons: List[str] = Field(default_factory=list)
    requested_total: int = 0
    generated_total: int = 0
    quality_gate_failed: bool = False
    save_blocked: bool = False
    quality_review_count: int = 0
    quality_review_blocked: int = 0
    factual_risk_count: int = 0
    distractor_risk_count: int = 0
    type_mismatch_count: int = 0
    difficulty_risk_count: int = 0
    near_duplicate_count: int = 0
    existing_near_duplicate_count: int = 0
    calibration_review_count: int = 0
    calibration_warning_count: int = 0
    difficulty_mismatch_count: int = 0
    difficulty_severe_mismatch_count: int = 0
    bloom_mismatch_count: int = 0
    bloom_severe_mismatch_count: int = 0
    selection_mode: Literal["stable", "coverage"] = "stable"
    configured_max_units: int = 0
    effective_max_units: int = 0
    selected_unit_count: int = 0
    history_window_size: int = 0
    cooled_unit_count: int = 0
    ai_review_pending: bool = False
    ai_review_completed: bool = False
    timings: dict = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    generated: int
    questions: List[QuestionResponse]
    stats: Optional[GenerateStats] = None
    model_name: Optional[str] = None


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
    risk_tags: List[str] = Field(default_factory=list)


class QuestionBankBuildRequest(PromptOverrideMixin):
    """Request to build question bank from a material with type distribution."""
    type_distribution: dict = Field(
        description="Question type to count mapping, e.g. {'single_choice': 10, 'true_false': 5}",
    )
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    max_units: int = Field(default=10, ge=1, le=50)
    selection_mode: Literal["stable", "coverage"] = "stable"
    custom_prompt: Optional[str] = Field(default=None, max_length=500)


class FreeGenerateRequest(PromptOverrideMixin):
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
    configured_max_units: int = 0
    effective_max_units: int = 0
    suggested_distribution: dict
    suggested_total: int
    difficulty: int


class PreviewQuestionItem(BaseModel):
    """预览题目（未保存），匹配 generate_questions_via_llm() 的原始dict结构。"""
    preview_item_id: Optional[str] = None
    question_type: str
    stem: str
    options: Optional[dict] = None
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: int = Field(default=3, ge=1, le=5)
    dimension: Optional[str] = None
    knowledge_tags: Optional[list] = None
    bloom_level: Optional[str] = None
    source_material_id: Optional[UUID] = None
    source_knowledge_unit_id: Optional[UUID] = None
    source_material_title: Optional[str] = None
    source_knowledge_unit_title: Optional[str] = None
    quality_review: Optional[dict] = None
    calibration_review: Optional[dict] = None


class PreviewResponse(BaseModel):
    """预览生成结果（不存DB）。"""
    questions: List[PreviewQuestionItem]
    total: int
    stats: Optional[GenerateStats] = None
    model_name: Optional[str] = None


class BatchCreateFromRawRequest(BaseModel):
    """批量保存预览题目到数据库。"""
    questions: List[PreviewQuestionItem]


class QuestionPromptPlaceholderResponse(BaseModel):
    key: str
    description: str
    source: str


class QuestionPromptConfigResponse(BaseModel):
    system_prompt: str
    user_prompt_template: str
    has_saved_config: bool
    defaults: dict
    placeholders: List[QuestionPromptPlaceholderResponse]


class QuestionPromptConfigUpdateRequest(BaseModel):
    system_prompt: str = Field(..., min_length=1, max_length=20000)
    user_prompt_template: str = Field(..., min_length=1, max_length=20000)


class QuestionPromptPreviewRequest(PromptOverrideMixin):
    type_distribution: dict = Field(description="Question type to count mapping")
    difficulty: int = Field(default=3, ge=1, le=5)
    bloom_level: Optional[str] = None
    custom_prompt: Optional[str] = Field(default=None, max_length=500)
    max_units: int = Field(default=10, ge=1, le=50)
    selection_mode: Literal["stable", "coverage"] = "stable"
    material_ids: List[UUID] = Field(default_factory=list)


class QuestionPromptPreviewItemResponse(BaseModel):
    title: str
    rendered_user_prompt: str


class QuestionPromptPreviewResponse(BaseModel):
    system_prompt: str
    user_prompt_template: str
    rendered_user_prompt: str
    rendered_user_prompts: List[QuestionPromptPreviewItemResponse]
    placeholders: List[QuestionPromptPlaceholderResponse]
    preview_note: Optional[str] = None
    prompt_seed: int


class QuestionInteractionsResponse(BaseModel):
    liked: bool
    favorited: bool
    like_count: int
    favorite_count: int


class FeedbackRequest(BaseModel):
    feedback_type: str
    comment: Optional[str] = None
