"""Question management API endpoints."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_role
from app.models.user import User
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
    QuestionListResponse,
    GenerateRequest,
    BatchGenerateRequest,
    GenerateResponse,
    ReviewRequest,
    BatchReviewRequest,
    BatchSubmitRequest,
    BatchDeleteRequest,
    BatchExportRequest,
    ReviewRecordResponse,
    AIReviewResponse,
    QuestionBankBuildRequest,
    QuestionBankSuggestResponse,
    FreeGenerateRequest,
)
from app.services import question_service
from app.services.question_io_service import export_questions_to_md, parse_md_to_questions

router = APIRouter(prefix="/questions", tags=["题库管理"])


def _to_response(q) -> QuestionResponse:
    return QuestionResponse(
        id=q.id,
        question_type=q.question_type.value if hasattr(q.question_type, 'value') else q.question_type,
        stem=q.stem,
        options=q.options,
        correct_answer=q.correct_answer,
        explanation=q.explanation,
        rubric=q.rubric,
        difficulty=q.difficulty,
        dimension=q.dimension,
        knowledge_tags=q.knowledge_tags,
        bloom_level=q.bloom_level.value if q.bloom_level and hasattr(q.bloom_level, 'value') else q.bloom_level,
        source_material_id=q.source_material_id,
        source_knowledge_unit_id=q.source_knowledge_unit_id,
        status=q.status.value if hasattr(q.status, 'value') else q.status,
        usage_count=q.usage_count,
        correct_rate=q.correct_rate,
        discrimination=q.discrimination,
        review_comment=q.review_comment,
        created_by=q.created_by,
        reviewed_by=q.reviewed_by,
        created_at=q.created_at,
        updated_at=q.updated_at,
    )


# ---- Fixed-path routes MUST come before /{question_id} routes ----

@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    body: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Manually create a question."""
    q = await question_service.create_question(
        db=db,
        question_type=body.question_type,
        stem=body.stem,
        correct_answer=body.correct_answer,
        options=body.options,
        explanation=body.explanation,
        rubric=body.rubric,
        difficulty=body.difficulty,
        dimension=body.dimension,
        knowledge_tags=body.knowledge_tags,
        bloom_level=body.bloom_level,
        source_material_id=body.source_material_id,
        source_knowledge_unit_id=body.source_knowledge_unit_id,
        created_by=current_user.id,
    )
    await db.commit()
    return _to_response(q)


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    question_type: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List questions with filters."""
    items, total = await question_service.list_questions(
        db=db,
        skip=skip,
        limit=limit,
        status=status_filter,
        question_type=question_type,
        dimension=dimension,
        difficulty=difficulty,
        keyword=keyword,
    )
    return QuestionListResponse(
        total=total,
        items=[_to_response(q) for q in items],
    )


@router.get("/stats")
async def question_stats(
    dimension: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get question bank statistics."""
    stats = await question_service.get_question_stats(db, dimension)
    return stats


@router.post("/calibration/auto-flag")
async def auto_flag_questions(
    min_sample: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Auto-flag and archive low-quality questions based on CTT analysis."""
    from app.services.question_calibration_service import auto_flag_low_quality
    result = await auto_flag_low_quality(db, min_sample=min_sample)
    await db.commit()
    return result


@router.post("/calibration/{question_id}")
async def calibrate_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Recalibrate a question's difficulty based on actual answer data."""
    from app.services.question_calibration_service import calibrate_question_difficulty
    result = await calibrate_question_difficulty(db, question_id)
    await db.commit()
    return result


@router.get("/calibration/similar")
async def find_similar(
    threshold: float = Query(0.9, ge=0.5, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Find potentially duplicate questions (semantic similarity)."""
    from app.services.question_calibration_service import find_similar_questions
    return await find_similar_questions(db, threshold=threshold, limit=limit)


@router.get("/analysis/report")
async def question_quality_report(
    min_sample: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Generate a global question quality report (CTT/IRT)."""
    from app.services.question_analysis_service import get_question_quality_report
    return await get_question_quality_report(db, min_sample)


@router.get("/analysis/{question_id}")
async def analyze_single_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer", "reviewer"])),
):
    """Get CTT/IRT analysis for a single question."""
    from app.services.question_analysis_service import analyze_question
    result = await analyze_question(db, question_id)
    await db.commit()
    return result


@router.get("/review/pending", response_model=QuestionListResponse)
async def get_pending_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Get questions pending review."""
    items, total = await question_service.get_pending_reviews(db, skip, limit)
    return QuestionListResponse(
        total=total,
        items=[_to_response(q) for q in items],
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_questions(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Generate questions from a knowledge unit using AI."""
    try:
        questions = await question_service.generate_from_knowledge_unit(
            db=db,
            knowledge_unit_id=body.knowledge_unit_id,
            question_types=body.question_types,
            count=body.count,
            difficulty=body.difficulty,
            bloom_level=body.bloom_level,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return GenerateResponse(
        generated=len(questions),
        questions=[_to_response(q) for q in questions],
    )


@router.post("/generate/material/{material_id}", response_model=GenerateResponse)
async def batch_generate_from_material(
    material_id: UUID,
    body: BatchGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Batch generate questions from all knowledge units of a material."""
    try:
        questions = await question_service.batch_generate_from_material(
            db=db,
            material_id=material_id,
            question_types=body.question_types,
            count_per_unit=body.count_per_unit,
            difficulty=body.difficulty,
            bloom_level=body.bloom_level,
            max_units=body.max_units,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return GenerateResponse(
        generated=len(questions),
        questions=[_to_response(q) for q in questions],
    )


@router.post("/batch/submit", response_model=QuestionListResponse)
async def batch_submit_for_review(
    body: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Batch submit draft questions for review."""
    try:
        questions = await question_service.batch_submit_for_review(db, body.question_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return QuestionListResponse(
        total=len(questions),
        items=[_to_response(q) for q in questions],
    )


@router.post("/batch/review", response_model=QuestionListResponse)
async def batch_review(
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Batch approve or reject questions."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
    try:
        questions = await question_service.batch_review(
            db, body.question_ids, body.action, current_user.id, body.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return QuestionListResponse(
        total=len(questions),
        items=[_to_response(q) for q in questions],
    )


@router.post("/batch/delete")
async def batch_delete_questions(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Batch delete questions (admin only)."""
    deleted = await question_service.batch_delete(db, body.question_ids)
    await db.commit()
    return {"deleted": deleted, "total": len(body.question_ids)}


@router.post("/generate/bank/{material_id}", response_model=GenerateResponse)
async def build_question_bank(
    material_id: UUID,
    body: QuestionBankBuildRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Build question bank from a material with specific type distribution."""
    try:
        questions = await question_service.build_question_bank_from_material(
            db=db,
            material_id=material_id,
            type_distribution=body.type_distribution,
            difficulty=body.difficulty,
            bloom_level=body.bloom_level,
            max_units=body.max_units,
            created_by=current_user.id,
            custom_prompt=body.custom_prompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return GenerateResponse(
        generated=len(questions),
        questions=[_to_response(q) for q in questions],
    )


@router.get("/generate/suggest/{material_id}", response_model=QuestionBankSuggestResponse)
async def suggest_distribution(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Analyze a material and suggest optimal question type distribution."""
    try:
        result = await question_service.suggest_question_distribution(db, material_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return QuestionBankSuggestResponse(**result)


@router.post("/generate/free", response_model=GenerateResponse)
async def generate_free(
    body: FreeGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Generate questions without material, using LLM's own knowledge."""
    try:
        questions = await question_service.generate_questions_free(
            db=db,
            type_distribution=body.type_distribution,
            difficulty=body.difficulty,
            bloom_level=body.bloom_level,
            custom_prompt=body.custom_prompt,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return GenerateResponse(
        generated=len(questions),
        questions=[_to_response(q) for q in questions],
    )


@router.post("/batch/export-md")
async def batch_export_md(
    body: BatchExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Export selected questions as a Markdown file."""
    import io
    from urllib.parse import quote

    questions = []
    for qid in body.question_ids:
        q = await question_service.get_question_by_id(db, qid)
        if q:
            questions.append(q)

    if not questions:
        raise HTTPException(status_code=404, detail="未找到指定题目")

    md_content = export_questions_to_md(questions)
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"题库导出_{now_str}.md"
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(md_content.encode("utf-8")),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.post("/batch/preview-md")
async def batch_preview_md(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Parse a Markdown question file and return structure analysis WITHOUT saving.

    Returns type statistics and answer-format validation warnings.
    """
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持 .md 文件")

    content = await file.read()
    try:
        md_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8")

    parsed = parse_md_to_questions(md_text)
    if not parsed:
        raise HTTPException(status_code=400, detail="未能从文件中解析出任何题目")

    TYPE_LABELS = {
        "single_choice": "单选题",
        "multiple_choice": "多选题",
        "true_false": "判断题",
        "fill_blank": "填空题",
        "short_answer": "简答题",
        "essay": "论述题",
        "sjt": "情境判断题",
    }

    type_stats: dict[str, dict] = {}
    answer_issues: list[dict] = []

    for idx, q in enumerate(parsed, 1):
        qt = q.get("question_type", "unknown")
        answer = (q.get("correct_answer") or "").strip()

        if qt not in type_stats:
            type_stats[qt] = {"label": TYPE_LABELS.get(qt, qt), "count": 0, "sample_answer": answer}
        type_stats[qt]["count"] += 1

        issue = None
        if qt == "single_choice":
            if len(answer) > 1:
                issue = f'第{idx}题（单选题）答案"{answer}"含多个字符，单选题答案应为单个字母'
        elif qt == "multiple_choice":
            if len(answer) == 1:
                issue = f'第{idx}题（多选题）答案"{answer}"只有1个字母，多选题通常有2个以上选项'
        elif qt == "true_false":
            valid_tf = {"a", "b", "对", "错", "√", "×", "正确", "错误", "true", "false", "t", "f", "是", "否"}
            if answer.lower() not in valid_tf and answer:
                issue = f'第{idx}题（判断题）答案"{answer}"格式不标准（期望 T/F 或 对/错/√/×）'

        if issue:
            answer_issues.append({"question_index": idx, "message": issue})

    return {
        "total": len(parsed),
        "type_stats": list(type_stats.values()),
        "answer_issues": answer_issues,
    }


@router.post("/batch/import-md")
async def batch_import_md(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Import questions from a Markdown file. All imported questions are set to draft status."""
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持 .md 文件")

    content = await file.read()
    try:
        md_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8")

    parsed = parse_md_to_questions(md_text)
    if not parsed:
        raise HTTPException(status_code=400, detail="未能从文件中解析出任何题目")

    imported = 0
    failed = 0
    errors: list[str] = []

    for i, q_data in enumerate(parsed, 1):
        try:
            await question_service.create_question(
                db=db,
                question_type=q_data["question_type"],
                stem=q_data["stem"],
                correct_answer=q_data["correct_answer"],
                options=q_data.get("options"),
                explanation=q_data.get("explanation"),
                rubric=q_data.get("rubric"),
                difficulty=q_data.get("difficulty", 3),
                dimension=q_data.get("dimension"),
                knowledge_tags=q_data.get("knowledge_tags"),
                bloom_level=q_data.get("bloom_level"),
                created_by=current_user.id,
            )
            imported += 1
        except Exception as e:
            failed += 1
            errors.append(f"第{i}题: {str(e)}")

    await db.commit()
    return {"imported": imported, "failed": failed, "errors": errors}


# ---- Dynamic path routes (/{question_id}) ----

@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = await question_service.get_question_by_id(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _to_response(q)


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    body: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update a question."""
    q = await question_service.update_question(
        db=db,
        question_id=question_id,
        **body.model_dump(exclude_unset=True),
    )
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    await db.commit()
    return _to_response(q)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Delete a question (admin only)."""
    deleted = await question_service.delete_question(db, question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="题目不存在")
    await db.commit()


@router.post("/{question_id}/submit", response_model=QuestionResponse)
async def submit_for_review(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Submit a draft question for review."""
    try:
        q = await question_service.submit_for_review(db, question_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    await db.commit()
    return _to_response(q)


@router.post("/{question_id}/review", response_model=QuestionResponse)
async def review_question(
    question_id: UUID,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Review (approve/reject) a question."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
    try:
        q = await question_service.review_question(
            db=db,
            question_id=question_id,
            action=body.action,
            reviewer_id=current_user.id,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    await db.commit()
    return _to_response(q)


@router.post("/{question_id}/ai-check", response_model=AIReviewResponse)
async def ai_check_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Run AI quality check on a question."""
    try:
        result = await question_service.ai_check_question(db, question_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return AIReviewResponse(**result)


@router.get("/{question_id}/review-history", response_model=list[ReviewRecordResponse])
async def get_review_history(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get review history for a question."""
    records = await question_service.get_review_history(db, question_id)
    return [
        ReviewRecordResponse(
            id=r.id,
            question_id=r.question_id,
            reviewer_id=r.reviewer_id,
            action=r.action,
            comment=r.comment,
            ai_scores=r.ai_scores,
            created_at=r.created_at,
        )
        for r in records
    ]
