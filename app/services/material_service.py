"""Material service - handles material upload, metadata persistence, and queries."""
import uuid
from typing import Optional

from sqlalchemy import select, func, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Material, MaterialStatus, KnowledgeUnit
from app.models.question import Question
from app.services.minio_service import upload_file, delete_file, get_presigned_url


async def create_material(
    db: AsyncSession,
    title: str,
    file_data: bytes,
    filename: str,
    content_type: str,
    user_id: uuid.UUID,
    description: str = None,
    category: str = None,
    tags: list = None,
    source_url: str = None,
) -> Material:
    """Upload file to MinIO and create material record in DB."""
    storage = await upload_file(file_data, filename, content_type, str(user_id))

    material = Material(
        title=title,
        description=description,
        format=storage["format"],
        file_path=storage["file_path"],
        file_size=storage["file_size"],
        status=MaterialStatus.UPLOADED,
        category=category,
        tags=tags,
        source_url=source_url,
        uploaded_by=user_id,
    )
    db.add(material)
    await db.flush()
    await db.refresh(material)
    return material


async def get_material_by_id(
    db: AsyncSession, material_id: uuid.UUID
) -> Optional[Material]:
    result = await db.execute(select(Material).where(Material.id == material_id))
    return result.scalar_one_or_none()


async def list_materials(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    category: str = None,
    format: str = None,
    keyword: str = None,
    uploaded_by: uuid.UUID = None,
) -> tuple[list[Material], int]:
    """List materials with filters and pagination."""
    query = select(Material)
    count_query = select(func.count(Material.id))

    if status:
        query = query.where(Material.status == status)
        count_query = count_query.where(Material.status == status)
    if category:
        query = query.where(Material.category == category)
        count_query = count_query.where(Material.category == category)
    if format:
        query = query.where(Material.format == format)
        count_query = count_query.where(Material.format == format)
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(Material.title.ilike(like_pattern))
        count_query = count_query.where(Material.title.ilike(like_pattern))
    if uploaded_by:
        query = query.where(Material.uploaded_by == uploaded_by)
        count_query = count_query.where(Material.uploaded_by == uploaded_by)

    total = await db.scalar(count_query)
    query = query.order_by(desc(Material.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    materials = list(result.scalars().all())

    return materials, total


async def update_material_status(
    db: AsyncSession, material_id: uuid.UUID, new_status: MaterialStatus
) -> Optional[Material]:
    material = await get_material_by_id(db, material_id)
    if material:
        material.status = new_status
        await db.flush()
        await db.refresh(material)
    return material


async def delete_material(
    db: AsyncSession, material_id: uuid.UUID
) -> bool:
    """Delete material record and its file from MinIO."""
    material = await get_material_by_id(db, material_id)
    if not material:
        return False

    ku_result = await db.execute(
        select(KnowledgeUnit.id).where(KnowledgeUnit.material_id == material_id)
    )
    knowledge_unit_ids = list(ku_result.scalars().all())

    await db.execute(
        update(Question)
        .where(Question.source_material_id == material_id)
        .values(source_material_id=None)
    )

    if knowledge_unit_ids:
        await db.execute(
            update(Question)
            .where(Question.source_knowledge_unit_id.in_(knowledge_unit_ids))
            .values(source_knowledge_unit_id=None)
        )
        await db.execute(
            delete(KnowledgeUnit).where(KnowledgeUnit.material_id == material_id)
        )

    try:
        delete_file(material.file_path)
    except Exception:
        pass  # File may already be gone

    await db.delete(material)
    await db.flush()
    return True


def get_material_download_url(file_path: str) -> str:
    """Get a presigned download URL for a material file."""
    return get_presigned_url(file_path)
