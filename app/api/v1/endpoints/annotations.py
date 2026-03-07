"""Annotation endpoints - manage material annotations."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas.annotation import (
    ManualAnnotationRequest,
    AnnotationResponse,
    ConsistencyResponse,
)
from app.services.annotation_service import (
    auto_annotate_material,
    add_manual_annotation,
    list_annotations,
    delete_annotation,
    get_annotation_consistency,
)

router = APIRouter(prefix="/annotations", tags=["标注管理"])


@router.post("/materials/{material_id}/auto", response_model=list[AnnotationResponse])
async def auto_annotate(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-annotate a material using LLM."""
    try:
        annotations = await auto_annotate_material(db, material_id, current_user.id)
        await db.commit()
        return annotations
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/materials/{material_id}/manual", response_model=AnnotationResponse)
async def create_manual_annotation(
    material_id: uuid.UUID,
    req: ManualAnnotationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a manual annotation to a material."""
    ann = await add_manual_annotation(
        db,
        material_id=material_id,
        annotator_id=current_user.id,
        content=req.content,
        highlighted_text=req.highlighted_text,
        start_offset=req.start_offset,
        end_offset=req.end_offset,
        dimension=req.dimension,
        difficulty=req.difficulty,
        knowledge_unit_id=req.knowledge_unit_id,
    )
    await db.commit()
    return ann


@router.get("/materials/{material_id}", response_model=list[AnnotationResponse])
async def get_annotations(
    material_id: uuid.UUID,
    annotation_type: str = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List annotations for a material."""
    return await list_annotations(db, material_id, annotation_type)


@router.delete("/{annotation_id}", status_code=200)
async def remove_annotation(
    annotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an annotation (only by its creator)."""
    try:
        deleted = await delete_annotation(db, annotation_id, current_user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="标注不存在")
        await db.commit()
        return {"detail": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/materials/{material_id}/consistency", response_model=ConsistencyResponse)
async def check_consistency(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Check annotation consistency between multiple annotators."""
    return await get_annotation_consistency(db, material_id)
