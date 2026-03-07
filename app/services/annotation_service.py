"""Annotation service - manages material annotations."""
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.material import Material, KnowledgeUnit
from app.agents.annotation_agent import auto_annotate_content


async def auto_annotate_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    annotator_id: uuid.UUID,
) -> list[Annotation]:
    """Auto-annotate all knowledge units of a material using LLM."""
    # Load knowledge units
    result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units = list(result.scalars().all())

    if not units:
        # Annotate material itself
        material = (await db.execute(
            select(Material).where(Material.id == material_id)
        )).scalar_one_or_none()
        if not material:
            raise ValueError("素材不存在")

        annotation_data = auto_annotate_content(
            content=material.title or "",
            title=material.title,
        )
        ann = Annotation(
            material_id=material_id,
            annotator_id=annotator_id,
            annotation_type="ai_auto",
            content=annotation_data.get("summary", ""),
            dimension=annotation_data.get("dimension"),
            difficulty=annotation_data.get("difficulty"),
            knowledge_points=annotation_data.get("knowledge_points"),
            ai_confidence=annotation_data.get("confidence"),
        )
        db.add(ann)
        await db.flush()
        return [ann]

    annotations = []
    for unit in units:
        annotation_data = auto_annotate_content(
            content=unit.content,
            title=unit.title,
        )

        # Update the knowledge unit with annotation data
        unit.dimension = annotation_data.get("dimension")
        unit.difficulty = annotation_data.get("difficulty")
        unit.keywords = annotation_data.get("knowledge_points")
        unit.summary = annotation_data.get("summary")

        # Create annotation record
        ann = Annotation(
            material_id=material_id,
            knowledge_unit_id=unit.id,
            annotator_id=annotator_id,
            annotation_type="ai_auto",
            content=annotation_data.get("summary", ""),
            dimension=annotation_data.get("dimension"),
            difficulty=annotation_data.get("difficulty"),
            knowledge_points=annotation_data.get("knowledge_points"),
            ai_confidence=annotation_data.get("confidence"),
        )
        db.add(ann)
        annotations.append(ann)

    await db.flush()
    return annotations


async def add_manual_annotation(
    db: AsyncSession,
    material_id: uuid.UUID,
    annotator_id: uuid.UUID,
    content: Optional[str] = None,
    highlighted_text: Optional[str] = None,
    start_offset: Optional[int] = None,
    end_offset: Optional[int] = None,
    dimension: Optional[str] = None,
    difficulty: Optional[int] = None,
    knowledge_unit_id: Optional[uuid.UUID] = None,
) -> Annotation:
    """Add a manual annotation."""
    ann = Annotation(
        material_id=material_id,
        knowledge_unit_id=knowledge_unit_id,
        annotator_id=annotator_id,
        annotation_type="manual",
        content=content,
        highlighted_text=highlighted_text,
        start_offset=start_offset,
        end_offset=end_offset,
        dimension=dimension,
        difficulty=difficulty,
    )
    db.add(ann)
    await db.flush()
    return ann


async def list_annotations(
    db: AsyncSession,
    material_id: uuid.UUID,
    annotation_type: Optional[str] = None,
) -> list[Annotation]:
    """List annotations for a material."""
    conditions = [Annotation.material_id == material_id]
    if annotation_type:
        conditions.append(Annotation.annotation_type == annotation_type)

    result = await db.execute(
        select(Annotation)
        .where(*conditions)
        .order_by(Annotation.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_annotation(
    db: AsyncSession,
    annotation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Delete an annotation (only by its creator)."""
    ann = (await db.execute(
        select(Annotation).where(Annotation.id == annotation_id)
    )).scalar_one_or_none()

    if not ann:
        return False
    if ann.annotator_id != user_id:
        raise ValueError("只能删除自己的标注")

    await db.delete(ann)
    await db.flush()
    return True


async def get_annotation_consistency(
    db: AsyncSession,
    material_id: uuid.UUID,
) -> dict:
    """Check consistency between multiple annotators."""
    annotations = await list_annotations(db, material_id, "manual")

    if len(annotations) < 2:
        return {"consistent": True, "annotator_count": len(annotations), "conflicts": []}

    # Group by knowledge_unit_id
    by_unit = {}
    for ann in annotations:
        key = str(ann.knowledge_unit_id or "material")
        if key not in by_unit:
            by_unit[key] = []
        by_unit[key].append(ann)

    conflicts = []
    for key, anns in by_unit.items():
        dimensions = set(a.dimension for a in anns if a.dimension)
        difficulties = set(a.difficulty for a in anns if a.difficulty)

        if len(dimensions) > 1:
            conflicts.append({
                "unit": key,
                "type": "dimension",
                "values": list(dimensions),
            })
        if len(difficulties) > 1 and max(difficulties) - min(difficulties) > 1:
            conflicts.append({
                "unit": key,
                "type": "difficulty",
                "values": list(difficulties),
            })

    return {
        "consistent": len(conflicts) == 0,
        "annotator_count": len(set(a.annotator_id for a in annotations)),
        "conflicts": conflicts,
    }
