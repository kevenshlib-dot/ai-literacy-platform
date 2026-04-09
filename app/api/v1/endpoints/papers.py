"""Paper management API endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.schemas.paper import (
    PaperCreate,
    PaperUpdate,
    PaperResponse,
    PaperListResponse,
    PaperSectionCreate,
    PaperSectionUpdate,
    PaperSectionResponse,
    PaperQuestionAdd,
    PaperQuestionUpdate,
    PaperQuestionResponse,
    ReorderPayload,
    AutoAssemblePayload,
    AssignToExamPayload,
    SyncToBankExecutePayload,
)
from app.services.paper_service import (
    create_paper,
    get_paper_by_id,
    list_papers,
    update_paper,
    delete_paper,
    publish_paper,
    archive_paper,
    restore_paper,
    duplicate_paper,
    add_section,
    update_section,
    delete_section,
    reorder_sections,
    add_questions_manual,
    auto_assemble,
    reorder_questions,
    update_paper_question,
    remove_paper_question,
    get_paper_detail,
    materialize_to_exam,
    sync_questions_to_bank_preview,
    sync_questions_to_bank_execute,
)
from app.services.paper_io_service import export_paper, import_paper

router = APIRouter(prefix="/papers", tags=["试卷管理"])


# ──────────────────────────────────────────────
# Paper CRUD
# ──────────────────────────────────────────────

@router.post("", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def create_new_paper(
    body: PaperCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Create a new paper (draft)."""
    paper = await create_paper(
        db=db,
        title=body.title,
        created_by=current_user.id,
        description=body.description,
        time_limit_minutes=body.time_limit_minutes,
        tags=body.tags,
    )
    await db.commit()
    await db.refresh(paper)
    return paper


@router.get("", response_model=PaperListResponse)
async def list_all_papers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """List papers with pagination and filtering."""
    papers, total = await list_papers(
        db=db, skip=skip, limit=limit,
        status=status_filter, keyword=keyword, tag=tag,
    )
    # papers now have question_count attached dynamically
    data = []
    for p in papers:
        resp = PaperResponse.model_validate(p)
        resp.question_count = getattr(p, "question_count", 0)
        data.append(resp)
    return PaperListResponse(
        data=data,
        total=total, skip=skip, limit=limit,
    )


@router.get("/{paper_id}")
async def get_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Get paper detail with all sections and questions."""
    detail = await get_paper_detail(db, paper_id)
    if not detail:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return detail


@router.put("/{paper_id}", response_model=PaperResponse)
async def update_existing_paper(
    paper_id: UUID,
    body: PaperUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update paper metadata."""
    paper = await update_paper(
        db, paper_id,
        title=body.title,
        description=body.description,
        time_limit_minutes=body.time_limit_minutes,
        tags=body.tags,
        total_score=body.total_score,
    )
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")
    await db.commit()
    await db.refresh(paper)
    return paper


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Delete a draft or archived paper."""
    try:
        deleted = await delete_paper(db, paper_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="试卷不存在")
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────

@router.post("/{paper_id}/publish", response_model=PaperResponse)
async def publish_existing_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Publish a paper (must have at least one question)."""
    try:
        paper = await publish_paper(db, paper_id)
        await db.commit()
        await db.refresh(paper)
        return paper
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/archive", response_model=PaperResponse)
async def archive_existing_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Archive a paper."""
    try:
        paper = await archive_paper(db, paper_id)
        await db.commit()
        await db.refresh(paper)
        return paper
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/restore", response_model=PaperResponse)
async def restore_archived_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Restore an archived paper back to draft."""
    try:
        paper = await restore_paper(db, paper_id)
        await db.commit()
        await db.refresh(paper)
        return paper
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/duplicate", response_model=PaperResponse)
async def duplicate_existing_paper(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Deep-copy a paper as a new draft."""
    try:
        paper = await duplicate_paper(db, paper_id, current_user.id)
        await db.commit()
        await db.refresh(paper)
        return paper
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# Sections
# ──────────────────────────────────────────────

@router.post("/{paper_id}/sections", response_model=PaperSectionResponse, status_code=status.HTTP_201_CREATED)
async def create_section(
    paper_id: UUID,
    body: PaperSectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Add a section to a paper."""
    try:
        section = await add_section(
            db, paper_id,
            title=body.title,
            description=body.description,
            score_rule=body.score_rule,
        )
        await db.commit()
        await db.refresh(section)
        return section
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sections/{section_id}", response_model=PaperSectionResponse)
async def update_existing_section(
    section_id: UUID,
    body: PaperSectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update a paper section."""
    section = await update_section(
        db, section_id,
        title=body.title,
        description=body.description,
        order_num=body.order_num,
        score_rule=body.score_rule,
    )
    if not section:
        raise HTTPException(status_code=404, detail="分节不存在")
    await db.commit()
    await db.refresh(section)
    return section


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_section(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Delete a paper section (questions become unsectioned)."""
    deleted = await delete_section(db, section_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="分节不存在")
    await db.commit()


@router.post("/{paper_id}/sections/reorder")
async def reorder_paper_sections(
    paper_id: UUID,
    body: ReorderPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Reorder sections by providing an ordered list of section IDs."""
    try:
        ordered_uuids = [UUID(sid) for sid in body.ordered_ids]
        sections = await reorder_sections(db, paper_id, ordered_uuids)
        await db.commit()
        return {"reordered": len(sections)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# Questions in paper
# ──────────────────────────────────────────────

@router.post("/{paper_id}/questions")
async def add_questions_to_paper(
    paper_id: UUID,
    items: list[PaperQuestionAdd],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Manually add one or more questions to a paper."""
    try:
        pqs = await add_questions_manual(
            db, paper_id,
            items=[item.model_dump() for item in items],
        )
        await db.commit()
        return {"added": len(pqs)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/auto-assemble")
async def auto_assemble_paper(
    paper_id: UUID,
    body: AutoAssemblePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Automatically assemble questions into a paper based on rules."""
    try:
        pqs = await auto_assemble(
            db, paper_id,
            rules=[r.model_dump() for r in body.rules],
        )
        await db.commit()
        return {"assembled": len(pqs)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/questions/reorder")
async def reorder_paper_questions(
    paper_id: UUID,
    body: ReorderPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Reorder questions by providing an ordered list of PaperQuestion IDs."""
    try:
        ordered_uuids = [UUID(sid) for sid in body.ordered_ids]
        await reorder_questions(db, paper_id, ordered_uuids)
        await db.commit()
        return {"reordered": len(ordered_uuids)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/questions/{pq_id}")
async def update_paper_question_endpoint(
    pq_id: UUID,
    body: PaperQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Update a paper question (score, overrides, etc.)."""
    pq = await update_paper_question(
        db, pq_id,
        score=body.score,
        order_num=body.order_num,
        section_id=body.section_id,
        options_override=body.options_override,
        stem_override=body.stem_override,
        question_type_override=body.question_type_override,
        correct_answer_override=body.correct_answer_override,
    )
    if not pq:
        raise HTTPException(status_code=404, detail="试卷题目不存在")
    await db.commit()
    return {"updated": True}


@router.delete("/questions/{pq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_question_from_paper(
    pq_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Remove a question from a paper."""
    deleted = await remove_paper_question(db, pq_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="试卷题目不存在")
    await db.commit()


# ──────────────────────────────────────────────
# Export / Import
# ──────────────────────────────────────────────

@router.get("/{paper_id}/export")
async def export_paper_endpoint(
    paper_id: UUID,
    format: str = Query("json", description="Export format: json or docx"),
    include_answers: bool = Query(True, description="Include answer key in Word export"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Export a paper to JSON or Word (.docx) format.

    - format=json: Standard JSON format (default)
    - format=docx: Word document for traditional exam use
    """
    try:
        if format == "docx":
            from fastapi.responses import Response
            from app.services.paper_word_exporter import export_paper_to_word

            # Get the full detail for export
            detail = await get_paper_detail(db, paper_id)
            if not detail:
                raise ValueError("试卷不存在")

            docx_bytes = export_paper_to_word(detail, include_answers=include_answers)
            raw_filename = f"{detail['title']}.docx"

            # URL-encode filename for Content-Disposition (RFC 5987)
            from urllib.parse import quote
            encoded_filename = quote(raw_filename)

            return Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                },
            )
        else:
            data = await export_paper(db, paper_id)
            return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_paper_endpoint(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Import a paper from JSON. Creates paper + questions in draft."""
    try:
        paper = await import_paper(db, data, current_user.id)
        await db.commit()
        await db.refresh(paper)
        return PaperResponse.model_validate(paper)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import-file", status_code=status.HTTP_201_CREATED)
async def import_paper_from_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Import a paper from a Word (.docx) or JSON file upload.

    Supports:
    - .docx: Parses exam structure (sections, questions, options, answers)
    - .json: Standard paper JSON format
    """
    filename = file.filename or "paper"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_data = await file.read()

    if not file_data:
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    try:
        if ext in ("docx", "doc"):
            from app.services.paper_word_parser import parse_word_paper
            parsed = parse_word_paper(file_data, filename)
        elif ext == "json":
            import json as json_lib
            try:
                parsed = json_lib.loads(file_data.decode("utf-8"))
            except (json_lib.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"JSON解析失败: {e}")
        else:
            raise ValueError(f"不支持的文件格式: .{ext}，仅支持 .docx 和 .json")

        # Extract warnings before import (they are not part of the paper format)
        warnings = parsed.pop("warnings", [])

        paper = await import_paper(db, parsed, current_user.id)
        await db.commit()
        await db.refresh(paper)

        response = PaperResponse.model_validate(paper).model_dump()
        if warnings:
            response["warnings"] = warnings
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview-file")
async def preview_paper_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Parse a paper file and return structure analysis WITHOUT saving.

    Returns a preview with:
    - Paper title, section count, total question count
    - Per-section question breakdown by type
    - Answer type validation warnings (e.g. single_choice with multi-letter answer)
    """
    filename = file.filename or "paper"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_data = await file.read()

    if not file_data:
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    try:
        if ext in ("docx", "doc"):
            from app.services.paper_word_parser import parse_word_paper
            parsed = parse_word_paper(file_data, filename)
        elif ext == "json":
            import json as json_lib
            try:
                parsed = json_lib.loads(file_data.decode("utf-8"))
            except (json_lib.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"JSON解析失败: {e}")
        else:
            raise ValueError(f"不支持的文件格式: .{ext}，仅支持 .docx 和 .json")

        warnings = list(parsed.pop("warnings", []))

        paper_data = parsed.get("paper", parsed)
        title = paper_data.get("title", "未命名试卷")

        # Collect all questions from sections and unsectioned
        all_questions: list[dict] = []
        sections_summary: list[dict] = []

        for sec in paper_data.get("sections", []):
            qs = sec.get("questions", [])
            all_questions.extend(qs)
            sec_types: dict[str, int] = {}
            for q in qs:
                qt = (q.get("question") or q).get("question_type", "unknown")
                sec_types[qt] = sec_types.get(qt, 0) + 1
            sections_summary.append({"title": sec.get("title", ""), "count": len(qs), "types": sec_types})

        for q in paper_data.get("unsectioned_questions", []):
            all_questions.append(q)

        # Build type statistics
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

        for idx, pq in enumerate(all_questions, 1):
            q = pq.get("question") or pq
            qt = q.get("question_type", "unknown")
            answer = (q.get("correct_answer") or "").strip()

            if qt not in type_stats:
                type_stats[qt] = {"label": TYPE_LABELS.get(qt, qt), "count": 0, "sample_answer": answer}
            type_stats[qt]["count"] += 1

            # Validate answer format vs question type
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
                warnings.append(issue)

        return {
            "title": title,
            "total_questions": len(all_questions),
            "sections": sections_summary,
            "type_stats": list(type_stats.values()),
            "answer_issues": answer_issues,
            "warnings": warnings,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# Sync paper questions to question bank
# ──────────────────────────────────────────────

@router.get("/{paper_id}/sync-to-bank/preview")
async def preview_sync_to_bank(
    paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Preview which paper questions will be imported to the question bank.

    Returns per-question comparison:
    - in_bank: already approved in bank → skip
    - draft_in_bank: exists but not approved → will promote
    - has_override: paper modified the question → will create new variant
    """
    try:
        result = await sync_questions_to_bank_preview(db, paper_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{paper_id}/sync-to-bank")
async def execute_sync_to_bank(
    paper_id: UUID,
    body: SyncToBankExecutePayload = SyncToBankExecutePayload(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Execute sync: import paper questions into the question bank.

    - Override questions → creates new approved Question, updates paper link
    - Draft questions → promotes to approved status
    - Already approved → skips

    Optionally specify pq_ids to sync only selected questions.
    """
    try:
        result = await sync_questions_to_bank_execute(
            db, paper_id,
            pq_ids=body.pq_ids,
            created_by=current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────
# Assign to exam
# ──────────────────────────────────────────────

@router.post("/{paper_id}/assign-exam")
async def assign_paper_to_exam(
    paper_id: UUID,
    body: AssignToExamPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Create an exam from a published paper."""
    try:
        exam = await materialize_to_exam(
            db=db,
            paper_id=paper_id,
            exam_title=body.exam_title,
            exam_description=body.exam_description,
            start_time=body.start_time,
            end_time=body.end_time,
            created_by=current_user.id,
        )
        await db.commit()
        return {
            "exam_id": str(exam.id),
            "title": exam.title,
            "status": exam.status.value if hasattr(exam.status, "value") else exam.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
