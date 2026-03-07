from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class StartExamResponse(BaseModel):
    answer_sheet_id: UUID
    exam_id: UUID
    exam_title: str
    time_limit_minutes: Optional[int] = None
    total_questions: int
    start_time: datetime


class SubmitAnswerRequest(BaseModel):
    question_id: UUID
    answer_content: str
    time_spent_seconds: Optional[int] = None


class SubmitAnswerResponse(BaseModel):
    id: UUID
    question_id: UUID
    answer_content: str
    is_marked: bool
    answered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarkQuestionRequest(BaseModel):
    question_id: UUID
    is_marked: bool


class SubmitExamResponse(BaseModel):
    answer_sheet_id: UUID
    status: str
    submit_time: datetime
    duration_seconds: Optional[int] = None
    total_answered: int
    total_questions: int


class AnswerSheetResponse(BaseModel):
    id: UUID
    exam_id: UUID
    user_id: UUID
    status: str
    start_time: datetime
    submit_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnswerResponse(BaseModel):
    id: UUID
    question_id: UUID
    answer_content: Optional[str] = None
    is_marked: bool
    time_spent_seconds: Optional[int] = None
    answered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnswerSheetWithScoreResponse(AnswerSheetResponse):
    """Answer sheet with exam title and score data for the scores page."""
    exam_title: str = ""
    total_score: Optional[float] = None
    max_score: Optional[float] = None
    level: Optional[str] = None
    percentile_rank: Optional[float] = None
    score_id: Optional[UUID] = None
    scored_at: Optional[datetime] = None


class AnswerSheetDetailResponse(AnswerSheetResponse):
    answers: List[AnswerResponse] = []


class RandomTestRequest(BaseModel):
    """Request to start a random test."""
    count: int = Field(default=10, ge=5, le=50, description="Number of questions")
    difficulty_mode: str = Field(
        default="real",
        description="easy (自信心爆棚) / real (真实水平) / hell (挑战地狱难度)",
    )


class ExamSessionQuestion(BaseModel):
    """Question data for exam session (no answer revealed)."""
    question_id: UUID
    order_num: int
    score: float
    question_type: str
    stem: str
    options: Optional[dict] = None
    difficulty: int


class ExamSessionResponse(BaseModel):
    """Full exam session data for examinee."""
    answer_sheet_id: UUID
    exam_title: str
    time_limit_minutes: Optional[int] = None
    start_time: datetime
    questions: List[ExamSessionQuestion]
    answers: dict = {}  # question_id -> answer_content mapping
