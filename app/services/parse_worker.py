"""Async parsing worker - processes uploaded materials in background."""
import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Material, MaterialStatus, KnowledgeUnit
from app.services.minio_service import get_minio_client
from app.services.parsing_service import parse_material, chunk_text

logger = logging.getLogger(__name__)


async def fetch_file_from_minio(file_path: str) -> bytes:
    """Download file content from MinIO."""
    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts
    client = get_minio_client()

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: client.get_object(bucket, object_name)
    )
    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()
    return data


async def parse_and_store(db: AsyncSession, material_id: uuid.UUID) -> bool:
    """Parse a material and store extracted knowledge units."""
    result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        logger.error(f"Material {material_id} not found")
        return False

    # Update status to parsing
    material.status = MaterialStatus.PARSING
    await db.flush()

    try:
        # Fetch file from MinIO
        file_data = await fetch_file_from_minio(material.file_path)

        # Extract filename from path
        filename = material.file_path.rsplit("/", 1)[-1]

        # Parse the material
        text = parse_material(file_data, filename, material.format.value)

        if not text or not text.strip():
            logger.warning(f"No text extracted from material {material_id}")
            material.status = MaterialStatus.PARSED
            await db.flush()
            return True

        # Chunk the text
        chunks = chunk_text(text, chunk_size=500, overlap=50)

        # Store each chunk as a knowledge unit
        for i, chunk_content in enumerate(chunks):
            ku = KnowledgeUnit(
                material_id=material.id,
                title=f"{material.title} - 片段 {i + 1}",
                content=chunk_content,
                chunk_index=i,
                dimension=material.category,
            )
            db.add(ku)

        material.status = MaterialStatus.PARSED
        await db.flush()

        logger.info(
            f"Material {material_id} parsed: {len(chunks)} knowledge units created"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to parse material {material_id}: {e}")
        await db.rollback()
        result = await db.execute(
            select(Material).where(Material.id == material_id)
        )
        material = result.scalar_one_or_none()
        if not material:
            logger.error(f"Material {material_id} not found after rollback")
            return False

        material.status = MaterialStatus.FAILED
        await db.flush()
        return False


async def trigger_parse(material_id: uuid.UUID):
    """Trigger async parsing for a material. Runs as a background task."""
    from app.core.database import async_session

    async with async_session() as db:
        try:
            await parse_and_store(db, material_id)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Parse worker error for {material_id}: {e}")
