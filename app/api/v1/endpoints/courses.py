"""Course management endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services import course_service

router = APIRouter(prefix="/courses", tags=["课程管理"])


class CourseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    dimension: Optional[str] = None
    difficulty: int = Field(1, ge=1, le=5)
    duration_minutes: Optional[int] = None
    tags: Optional[list] = None


class CourseUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    dimension: Optional[str] = None
    difficulty: Optional[int] = None
    duration_minutes: Optional[int] = None
    tags: Optional[list] = None


class ChapterCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    content_type: str = "text"
    video_url: Optional[str] = None
    order_num: int = 1
    duration_minutes: Optional[int] = None


class ChapterUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    video_url: Optional[str] = None
    order_num: Optional[int] = None
    duration_minutes: Optional[int] = None


def _course_response(c):
    return {
        "id": str(c.id),
        "title": c.title,
        "description": c.description,
        "dimension": c.dimension,
        "difficulty": c.difficulty,
        "duration_minutes": c.duration_minutes,
        "status": c.status.value if hasattr(c.status, 'value') else c.status,
        "tags": c.tags,
        "created_by": str(c.created_by),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _chapter_response(ch):
    return {
        "id": str(ch.id),
        "course_id": str(ch.course_id),
        "title": ch.title,
        "content_type": ch.content_type,
        "order_num": ch.order_num,
        "duration_minutes": ch.duration_minutes,
        "video_url": ch.video_url,
    }


@router.post("")
async def create(
    req: CourseCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Create a new course."""
    c = await course_service.create_course(
        db, title=req.title, created_by=current_user.id,
        description=req.description, dimension=req.dimension,
        difficulty=req.difficulty, duration_minutes=req.duration_minutes,
        tags=req.tags,
    )
    await db.commit()
    return _course_response(c)


@router.get("")
async def list_all(
    status: Optional[str] = Query(None),
    dimension: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List courses."""
    courses, total = await course_service.list_courses(db, status, dimension, skip, limit)
    return {"total": total, "items": [_course_response(c) for c in courses]}


@router.get("/{course_id}")
async def get_detail(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get course with chapters."""
    c = await course_service.get_course(db, course_id)
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    resp = _course_response(c)
    resp["chapters"] = [_chapter_response(ch) for ch in c.chapters]
    return resp


@router.put("/{course_id}")
async def update(
    course_id: uuid.UUID,
    req: CourseUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update a course."""
    c = await course_service.update_course(db, course_id, **req.model_dump(exclude_none=True))
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    await db.commit()
    return _course_response(c)


@router.post("/{course_id}/publish")
async def publish(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Publish a draft course."""
    try:
        c = await course_service.publish_course(db, course_id)
        if not c:
            raise HTTPException(status_code=404, detail="课程不存在")
        await db.commit()
        return _course_response(c)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{course_id}/archive")
async def archive(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Archive a course."""
    c = await course_service.archive_course(db, course_id)
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    await db.commit()
    return _course_response(c)


@router.post("/{course_id}/chapters")
async def add_chapter(
    course_id: uuid.UUID,
    req: ChapterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Add a chapter to a course."""
    ch = await course_service.add_chapter(
        db, course_id=course_id, title=req.title,
        order_num=req.order_num, content=req.content,
        content_type=req.content_type, video_url=req.video_url,
        duration_minutes=req.duration_minutes,
    )
    await db.commit()
    return _chapter_response(ch)


@router.put("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: uuid.UUID,
    req: ChapterUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update a chapter."""
    ch = await course_service.update_chapter(db, chapter_id, **req.model_dump(exclude_none=True))
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    await db.commit()
    return _chapter_response(ch)


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Delete a chapter."""
    deleted = await course_service.delete_chapter(db, chapter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="章节不存在")
    await db.commit()
    return {"deleted": True}
