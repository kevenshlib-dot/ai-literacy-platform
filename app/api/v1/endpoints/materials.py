from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.schemas.material import (
    MaterialResponse,
    MaterialListResponse,
    MaterialDownloadResponse,
)
from app.services.material_service import (
    create_material,
    get_material_by_id,
    list_materials as list_materials_svc,
    delete_material,
    get_material_download_url,
)
from app.services.parse_worker import trigger_parse, parse_and_store

router = APIRouter(prefix="/materials", tags=["素材管理"])


@router.get("/files/{bucket}/{rest_of_path:path}")
async def serve_local_file(bucket: str, rest_of_path: str):
    """Serve files from local storage fallback (dev mode, MinIO unavailable)."""
    from fastapi.responses import FileResponse
    from app.services.minio_service import LOCAL_STORAGE_ROOT

    file_path = LOCAL_STORAGE_ROOT / bucket / rest_of_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


@router.post("", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def upload_material(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Upload a single material file. Supports PDF, Word, Markdown, images, video, audio, CSV, JSON.
    Automatically triggers async parsing after upload."""
    file_data = await file.read()
    if not file_data:
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    try:
        material = await create_material(
            db=db,
            title=title,
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type,
            user_id=current_user.id,
            description=description,
            category=category,
            tags=tag_list,
            source_url=source_url,
        )
        await db.commit()

        # Trigger async parsing in background
        background_tasks.add_task(trigger_parse, material.id)

        return material
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def batch_upload_materials(
    files: list[UploadFile] = File(...),
    category: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Batch upload multiple material files."""
    results = []
    errors = []

    for file in files:
        file_data = await file.read()
        if not file_data:
            errors.append({"filename": file.filename, "error": "文件为空"})
            continue

        try:
            material = await create_material(
                db=db,
                title=file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename,
                file_data=file_data,
                filename=file.filename,
                content_type=file.content_type,
                user_id=current_user.id,
                category=category,
            )
            results.append(MaterialResponse.model_validate(material))
        except ValueError as e:
            errors.append({"filename": file.filename, "error": str(e)})

    await db.commit()
    return {
        "uploaded": len(results),
        "failed": len(errors),
        "materials": results,
        "errors": errors,
    }


@router.get("", response_model=MaterialListResponse)
async def list_all_materials(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List materials with filtering and pagination."""
    materials, total = await list_materials_svc(
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        category=category,
        format=format,
        keyword=keyword,
    )
    return MaterialListResponse(
        data=[MaterialResponse.model_validate(m) for m in materials],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/coverage")
async def coverage_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Get material and question coverage analysis across five dimensions."""
    from app.services.coverage_service import get_coverage_analysis
    return await get_coverage_analysis(db)


@router.get("/coverage/{dimension}")
async def dimension_coverage_detail(
    dimension: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Get detailed coverage for a specific dimension."""
    from app.services.coverage_service import get_dimension_detail
    result = await get_dimension_detail(db, dimension)
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single material by ID."""
    material = await get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")
    return material


@router.get("/{material_id}/download", response_model=MaterialDownloadResponse)
async def download_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a presigned download URL for a material file."""
    material = await get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    try:
        url = get_material_download_url(material.file_path)
    except Exception:
        raise HTTPException(status_code=500, detail="无法生成下载链接")

    filename = material.file_path.rsplit("/", 1)[-1] if "/" in material.file_path else material.title
    return MaterialDownloadResponse(download_url=url, filename=filename)


@router.post("/{material_id}/parse")
async def manual_parse_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Manually trigger parsing for a material."""
    material = await get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    success = await parse_and_store(db, material_id)
    await db.commit()
    return {"parsed": success, "material_id": str(material_id)}


@router.get("/{material_id}/knowledge-units")
async def get_material_knowledge_units(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get parsed knowledge units for a material."""
    from sqlalchemy import select
    from app.models.material import KnowledgeUnit

    material = await get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units = result.scalars().all()
    return {
        "material_id": str(material_id),
        "status": material.status.value if hasattr(material.status, 'value') else material.status,
        "total_units": len(units),
        "units": [
            {
                "id": str(u.id),
                "title": u.title,
                "content": u.content[:200] + "..." if len(u.content) > 200 else u.content,
                "chunk_index": u.chunk_index,
                "dimension": u.dimension,
            }
            for u in units
        ],
    }


@router.post("/{material_id}/vectorize")
async def vectorize_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Vectorize a parsed material's knowledge units and store in Milvus."""
    from sqlalchemy import select
    from app.models.material import KnowledgeUnit, MaterialStatus
    from app.services.vector_service import insert_vectors

    material = await get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units = list(result.scalars().all())
    if not units:
        raise HTTPException(status_code=400, detail="素材尚未解析，无知识单元可向量化")

    try:
        count = insert_vectors(
            knowledge_unit_ids=[str(u.id) for u in units],
            material_id=str(material_id),
            chunk_indices=[u.chunk_index or 0 for u in units],
            contents=[u.content for u in units],
        )
        # Update vector_id references
        for u in units:
            u.vector_id = str(u.id)
        # Update material status
        material.status = MaterialStatus.VECTORIZED
        await db.flush()
        await db.commit()
        return {"vectorized": count, "material_id": str(material_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量化失败: {str(e)}")


@router.get("/search/semantic")
async def semantic_search(
    q: str = Query(..., min_length=1, description="搜索查询文本"),
    top_k: int = Query(5, ge=1, le=50),
    material_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Semantic search across material knowledge units using vector similarity."""
    from app.services.vector_service import search_similar

    try:
        results = search_similar(query=q, top_k=top_k, material_id=material_id)
        return {
            "query": q,
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/search/stats")
async def vector_stats(
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Get vector collection statistics."""
    from app.services.vector_service import get_collection_stats
    try:
        return get_collection_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Delete a material and its file from storage."""
    deleted = await delete_material(db, material_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="素材不存在")
    await db.commit()
