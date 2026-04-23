"""Async parsing worker - processes uploaded materials in background."""
import asyncio
import logging
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Material, MaterialStatus, KnowledgeUnit
from app.models.question import Question
from app.services.minio_service import get_minio_client
from app.services.parsing_service import parse_material, chunk_text

logger = logging.getLogger(__name__)
MATERIAL_PLACEHOLDER_MARKERS = ("待OCR处理", "待转录处理", "待ASR处理")


async def fetch_file_from_storage(file_path: str) -> bytes:
    """Download file content from MinIO, or read from local fallback."""
    from app.services.minio_service import _minio_available, LOCAL_STORAGE_ROOT

    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts

    if _minio_available():
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

    # Local filesystem fallback
    local_path = LOCAL_STORAGE_ROOT / bucket / object_name
    if local_path.exists():
        return local_path.read_bytes()
    raise FileNotFoundError(f"文件不存在: {file_path}")


def _extract_filename(file_path: str) -> str:
    return file_path.rsplit("/", 1)[-1]


def _contains_placeholder_content(text: str | None) -> bool:
    if not text:
        return False
    return any(marker in text for marker in MATERIAL_PLACEHOLDER_MARKERS)


def _build_knowledge_units(material: Material, chunks: list[str]) -> list[KnowledgeUnit]:
    units: list[KnowledgeUnit] = []
    for i, chunk_content in enumerate(chunks):
        units.append(
            KnowledgeUnit(
                material_id=material.id,
                title=f"{material.title} - 片段 {i + 1}",
                content=chunk_content,
                chunk_index=i,
                dimension=None,
            )
        )
    return units


async def _load_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Material | None:
    stmt = select(Material).where(Material.id == material_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _extract_material_text(material: Material) -> str:
    file_data = await fetch_file_from_storage(material.file_path)
    filename = _extract_filename(material.file_path)
    return parse_material(file_data, filename, material.format.value)


async def parse_and_store(db: AsyncSession, material_id: uuid.UUID) -> bool:
    """Parse a material and store extracted knowledge units."""
    material = await _load_material(db, material_id)
    if not material:
        logger.error(f"Material {material_id} not found")
        return False

    # Update status to parsing
    material.status = MaterialStatus.PARSING
    await db.flush()

    try:
        text = await _extract_material_text(material)

        if not text or not text.strip():
            logger.warning(f"No text extracted from material {material_id}")
            material.status = MaterialStatus.PARSED
            await db.flush()
            return True

        chunks = chunk_text(text, chunk_size=500, overlap=50)

        for ku in _build_knowledge_units(material, chunks):
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
        material = await _load_material(db, material_id)
        if not material:
            logger.error(f"Material {material_id} not found after rollback")
            return False

        material.status = MaterialStatus.FAILED
        await db.flush()
        return False


async def safe_reparse_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    *,
    revectorize: bool | None = None,
) -> dict:
    """Safely replace existing knowledge units for a material.

    This is intended for already-online materials that were parsed with an older
    chunking strategy. The operation detaches linked questions from old
    knowledge units, deletes stale vectors when present, then recreates
    knowledge units from the latest parser/chunker implementation.
    """
    material = await _load_material(db, material_id, for_update=True)
    if not material:
        raise ValueError("素材不存在")
    if material.status == MaterialStatus.PARSING:
        raise ValueError("素材正在解析中，请稍后重试")

    previous_status = material.status
    material.status = MaterialStatus.PARSING
    await db.flush()

    try:
        text = await _extract_material_text(material)
        if _contains_placeholder_content(text):
            raise ValueError("当前素材仍是占位解析结果，请在OCR/ASR完成后再重解析")

        chunks = chunk_text(text, chunk_size=500, overlap=50) if text and text.strip() else []
        old_units_result = await db.execute(
            select(KnowledgeUnit)
            .where(KnowledgeUnit.material_id == material.id)
            .order_by(KnowledgeUnit.chunk_index)
        )
        old_units = list(old_units_result.scalars().all())
        old_unit_ids = [unit.id for unit in old_units]
        old_unit_count = len(old_units)
        had_vectors = (
            previous_status == MaterialStatus.VECTORIZED
            or any(unit.vector_id for unit in old_units)
        )
        should_revectorize = had_vectors if revectorize is None else revectorize

        detached_question_count = 0
        if old_unit_ids:
            detached_question_count = (
                await db.execute(
                    select(func.count(Question.id)).where(
                        Question.source_knowledge_unit_id.in_(old_unit_ids)
                    )
                )
            ).scalar() or 0
            if detached_question_count:
                await db.execute(
                    update(Question)
                    .where(Question.source_knowledge_unit_id.in_(old_unit_ids))
                    .values(
                        source_material_id=material.id,
                        source_knowledge_unit_id=None,
                    )
                )

        deleted_vector_count = 0
        if had_vectors:
            from app.services.vector_service import delete_material_vectors

            deleted_vector_count = delete_material_vectors(str(material.id))

        if old_unit_ids:
            await db.execute(
                delete(KnowledgeUnit).where(KnowledgeUnit.material_id == material.id)
            )

        new_units = _build_knowledge_units(material, chunks)
        for unit in new_units:
            db.add(unit)
        await db.flush()

        vectorized_count = 0
        actual_revectorized = False
        if should_revectorize and new_units:
            from app.services.vector_service import insert_vectors

            vectorized_count = insert_vectors(
                knowledge_unit_ids=[str(unit.id) for unit in new_units],
                material_id=str(material.id),
                chunk_indices=[unit.chunk_index or 0 for unit in new_units],
                contents=[unit.content for unit in new_units],
            )
            for unit in new_units:
                unit.vector_id = str(unit.id)
            actual_revectorized = True
            material.status = MaterialStatus.VECTORIZED
        else:
            material.status = MaterialStatus.PARSED

        await db.flush()
        return {
            "material_id": str(material.id),
            "old_unit_count": old_unit_count,
            "new_unit_count": len(new_units),
            "detached_question_count": int(detached_question_count),
            "deleted_vector_count": int(deleted_vector_count or 0),
            "revectorized": actual_revectorized,
            "vectorized_count": int(vectorized_count or 0),
            "status": material.status.value if hasattr(material.status, "value") else str(material.status),
        }
    except ValueError:
        await db.rollback()
        material = await _load_material(db, material_id)
        if material:
            material.status = previous_status
            await db.flush()
        raise
    except Exception:
        await db.rollback()
        material = await _load_material(db, material_id)
        if material:
            material.status = MaterialStatus.FAILED
            await db.flush()
        raise


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
