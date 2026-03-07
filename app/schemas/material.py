from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class MaterialCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list] = None
    source_url: Optional[str] = None


class MaterialUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list] = None
    source_url: Optional[str] = None


class MaterialResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    format: str
    file_path: str
    file_size: Optional[int] = None
    status: str
    category: Optional[str] = None
    tags: Optional[list] = None
    source_url: Optional[str] = None
    quality_score: Optional[float] = None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MaterialListResponse(BaseModel):
    data: List[MaterialResponse]
    total: int
    skip: int
    limit: int


class MaterialDownloadResponse(BaseModel):
    download_url: str
    filename: str
