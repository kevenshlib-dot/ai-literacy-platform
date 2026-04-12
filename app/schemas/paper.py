from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# --------------- Create / Update ---------------

class PaperCreate(BaseModel):
    title: str
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    tags: Optional[list] = None


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    tags: Optional[list] = None
    total_score: Optional[float] = None


class PaperSectionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    score_rule: Optional[dict] = None


class PaperSectionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    order_num: Optional[int] = None
    score_rule: Optional[dict] = None


class PaperQuestionAdd(BaseModel):
    question_id: UUID
    section_id: Optional[UUID] = None
    score: float = 5.0
    order_num: Optional[int] = None
    options_override: Optional[dict] = None
    stem_override: Optional[str] = None
    question_type_override: Optional[str] = None
    correct_answer_override: Optional[str] = None


class PaperQuestionUpdate(BaseModel):
    score: Optional[float] = None
    order_num: Optional[int] = None
    section_id: Optional[UUID] = None
    options_override: Optional[dict] = None
    stem_override: Optional[str] = None
    question_type_override: Optional[str] = None
    correct_answer_override: Optional[str] = None


# --------------- Reorder / Auto-assemble ---------------

class ReorderPayload(BaseModel):
    ordered_ids: List[str]


class AutoAssembleRule(BaseModel):
    question_type: str
    count: int
    score_per: float = 5.0
    difficulty: Optional[int] = None
    dimension: Optional[str] = None
    tags: Optional[list] = None


class AutoAssemblePayload(BaseModel):
    rules: List[AutoAssembleRule]


# --------------- Response schemas ---------------

class PaperSectionResponse(BaseModel):
    id: UUID
    paper_id: UUID
    title: str
    description: Optional[str] = None
    order_num: int
    score_rule: Optional[dict] = None

    model_config = {"from_attributes": True}


class PaperQuestionResponse(BaseModel):
    id: UUID
    paper_id: UUID
    section_id: Optional[UUID] = None
    question_id: UUID
    order_num: int
    score: float
    options_override: Optional[dict] = None
    stem_override: Optional[str] = None
    question_type_override: Optional[str] = None
    correct_answer_override: Optional[str] = None
    # Inline question details
    question_type: Optional[str] = None
    stem: Optional[str] = None
    options: Optional[dict] = None
    correct_answer: Optional[str] = None
    difficulty: Optional[int] = None
    dimension: Optional[str] = None

    model_config = {"from_attributes": True}


class PaperResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    status: str
    total_score: float
    time_limit_minutes: Optional[int] = None
    version: int = 1
    tags: Optional[list] = None
    usage_count: int = 0
    question_count: int = 0
    created_by: Optional[UUID] = None
    creator_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaperDetailResponse(PaperResponse):
    sections: List[PaperSectionResponse] = []
    questions: List[PaperQuestionResponse] = []
    metadata_extra: Optional[dict] = None


class PaperListResponse(BaseModel):
    data: List[PaperResponse]
    total: int
    skip: int
    limit: int


# --------------- Export / Import ---------------

class PaperExportFormat(BaseModel):
    format_version: str = "1.0"
    paper: PaperResponse
    sections: List[PaperSectionResponse] = []
    questions: List[PaperQuestionResponse] = []


# --------------- Assign to Exam ---------------

class AssignToExamPayload(BaseModel):
    exam_title: str
    exam_description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


# --------------- Sync to Question Bank ---------------

class SyncToBankExecutePayload(BaseModel):
    """Optional: specify which paper questions to sync. Empty = sync all importable."""
    pq_ids: Optional[List[str]] = None
