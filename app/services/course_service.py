"""Course management service."""
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course, CourseChapter, CourseStatus


async def create_course(
    db: AsyncSession,
    title: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: int = 1,
    duration_minutes: Optional[int] = None,
    tags: Optional[list] = None,
) -> Course:
    """Create a new course."""
    course = Course(
        title=title,
        description=description,
        dimension=dimension,
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        tags=tags,
        created_by=created_by,
    )
    db.add(course)
    await db.flush()
    return course


async def get_course(db: AsyncSession, course_id: uuid.UUID) -> Optional[Course]:
    """Get course with chapters."""
    result = await db.execute(
        select(Course)
        .options(selectinload(Course.chapters))
        .where(Course.id == course_id)
    )
    return result.scalar_one_or_none()


async def list_courses(
    db: AsyncSession,
    status: Optional[str] = None,
    dimension: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Course], int]:
    """List courses with filters."""
    conditions = []
    if status:
        conditions.append(Course.status == status)
    if dimension:
        conditions.append(Course.dimension == dimension)

    count_q = select(func.count(Course.id))
    list_q = select(Course).order_by(Course.created_at.desc()).offset(skip).limit(limit)

    if conditions:
        count_q = count_q.where(*conditions)
        list_q = list_q.where(*conditions)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(list_q)
    return list(result.scalars().all()), total


async def update_course(
    db: AsyncSession,
    course_id: uuid.UUID,
    **kwargs,
) -> Optional[Course]:
    """Update course details."""
    course = (await db.execute(
        select(Course).where(Course.id == course_id)
    )).scalar_one_or_none()
    if not course:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(course, key):
            setattr(course, key, value)

    await db.flush()
    return course


async def publish_course(db: AsyncSession, course_id: uuid.UUID) -> Optional[Course]:
    """Publish a draft course."""
    course = (await db.execute(
        select(Course).where(Course.id == course_id)
    )).scalar_one_or_none()
    if not course:
        return None
    if course.status != CourseStatus.DRAFT:
        raise ValueError("只能发布草稿状态的课程")
    course.status = CourseStatus.PUBLISHED
    await db.flush()
    return course


async def archive_course(db: AsyncSession, course_id: uuid.UUID) -> Optional[Course]:
    """Archive a course."""
    course = (await db.execute(
        select(Course).where(Course.id == course_id)
    )).scalar_one_or_none()
    if not course:
        return None
    course.status = CourseStatus.ARCHIVED
    await db.flush()
    return course


async def add_chapter(
    db: AsyncSession,
    course_id: uuid.UUID,
    title: str,
    order_num: int,
    content: Optional[str] = None,
    content_type: str = "text",
    video_url: Optional[str] = None,
    duration_minutes: Optional[int] = None,
) -> CourseChapter:
    """Add a chapter to a course."""
    chapter = CourseChapter(
        course_id=course_id,
        title=title,
        content=content,
        content_type=content_type,
        video_url=video_url,
        order_num=order_num,
        duration_minutes=duration_minutes,
    )
    db.add(chapter)
    await db.flush()
    return chapter


async def update_chapter(
    db: AsyncSession,
    chapter_id: uuid.UUID,
    **kwargs,
) -> Optional[CourseChapter]:
    """Update a chapter."""
    chapter = (await db.execute(
        select(CourseChapter).where(CourseChapter.id == chapter_id)
    )).scalar_one_or_none()
    if not chapter:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(chapter, key):
            setattr(chapter, key, value)

    await db.flush()
    return chapter


async def delete_chapter(db: AsyncSession, chapter_id: uuid.UUID) -> bool:
    """Delete a chapter."""
    chapter = (await db.execute(
        select(CourseChapter).where(CourseChapter.id == chapter_id)
    )).scalar_one_or_none()
    if not chapter:
        return False
    await db.delete(chapter)
    await db.flush()
    return True
