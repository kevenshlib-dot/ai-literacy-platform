"""Question service - handles question CRUD, generation, and review."""
import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question, QuestionType, QuestionStatus, BloomLevel, ReviewRecord
from app.models.material import Material, KnowledgeUnit
from app.agents.question_agent import generate_questions_via_llm, classify_dimension
from app.agents.review_agent import ai_review_question

logger = logging.getLogger(__name__)


def _coerce_uuid(value: Optional[uuid.UUID | str]) -> Optional[uuid.UUID]:
    """Accept UUID objects or strings from preview payloads."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


async def create_question(
    db: AsyncSession,
    question_type: str,
    stem: str,
    correct_answer: str,
    options: Optional[dict] = None,
    explanation: Optional[str] = None,
    rubric: Optional[dict] = None,
    difficulty: int = 3,
    dimension: Optional[str] = None,
    knowledge_tags: Optional[list] = None,
    bloom_level: Optional[str] = None,
    source_material_id: Optional[uuid.UUID] = None,
    source_knowledge_unit_id: Optional[uuid.UUID] = None,
    created_by: Optional[uuid.UUID] = None,
) -> Question:
    """Create a single question."""
    q = Question(
        question_type=QuestionType(question_type),
        stem=stem,
        correct_answer=correct_answer,
        options=options,
        explanation=explanation,
        rubric=rubric,
        difficulty=difficulty,
        dimension=dimension,
        knowledge_tags=knowledge_tags,
        bloom_level=BloomLevel(bloom_level) if bloom_level else None,
        source_material_id=source_material_id,
        source_knowledge_unit_id=source_knowledge_unit_id,
        created_by=created_by,
        status=QuestionStatus.DRAFT,
    )
    db.add(q)
    await db.flush()
    return q


async def get_question_by_id(
    db: AsyncSession, question_id: uuid.UUID
) -> Optional[Question]:
    result = await db.execute(
        select(Question).where(Question.id == question_id)
    )
    return result.scalar_one_or_none()


async def list_questions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    question_type: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: Optional[int] = None,
    keyword: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
) -> tuple[list[Question], int]:
    """List questions with filters and pagination."""
    conditions = []
    if status:
        conditions.append(Question.status == QuestionStatus(status))
    if question_type:
        conditions.append(Question.question_type == QuestionType(question_type))
    if dimension:
        conditions.append(Question.dimension == dimension)
    if difficulty:
        conditions.append(Question.difficulty == difficulty)
    if keyword:
        conditions.append(Question.stem.ilike(f"%{keyword}%"))
    if created_by:
        conditions.append(Question.created_by == created_by)

    where_clause = and_(*conditions) if conditions else True

    # Count
    count_q = select(func.count(Question.id)).where(where_clause)
    total = (await db.execute(count_q)).scalar()

    # Items
    items_q = (
        select(Question)
        .where(where_clause)
        .order_by(Question.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(items_q)
    items = list(result.scalars().all())

    return items, total


async def update_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    **kwargs,
) -> Optional[Question]:
    """Update a question's fields."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(q, key):
            if key == "bloom_level":
                setattr(q, key, BloomLevel(value))
            else:
                setattr(q, key, value)

    await db.flush()
    return q


async def delete_question(
    db: AsyncSession, question_id: uuid.UUID
) -> bool:
    q = await get_question_by_id(db, question_id)
    if not q:
        return False
    await db.delete(q)
    await db.flush()
    return True


async def batch_delete(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> int:
    """Batch delete questions. Returns count of actually deleted."""
    deleted = 0
    for qid in question_ids:
        ok = await delete_question(db, qid)
        if ok:
            deleted += 1
    return deleted


async def review_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    action: str,
    reviewer_id: uuid.UUID,
    comment: Optional[str] = None,
) -> Optional[Question]:
    """Approve or reject a question, with audit trail."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None

    if action == "approve":
        q.status = QuestionStatus.APPROVED
    elif action == "reject":
        q.status = QuestionStatus.REJECTED
    else:
        raise ValueError(f"Invalid review action: {action}")

    q.reviewed_by = reviewer_id
    q.review_comment = comment
    await db.flush()

    # Create audit record
    record = ReviewRecord(
        question_id=question_id,
        reviewer_id=reviewer_id,
        action=action,
        comment=comment,
    )
    db.add(record)
    await db.flush()

    return q


async def ai_check_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict:
    """Run AI quality check on a question. Returns scores and recommendation."""
    q = await get_question_by_id(db, question_id)
    if not q:
        raise ValueError(f"Question {question_id} not found")

    result = ai_review_question(
        stem=q.stem,
        options=q.options,
        correct_answer=q.correct_answer,
        explanation=q.explanation,
        question_type=q.question_type.value if hasattr(q.question_type, 'value') else q.question_type,
        difficulty=q.difficulty,
        dimension=q.dimension,
    )

    # Save AI check as review record
    record = ReviewRecord(
        question_id=question_id,
        reviewer_id=reviewer_id,
        action="ai_check",
        comment=result.get("comments"),
        ai_scores=result.get("scores"),
    )
    db.add(record)
    await db.flush()

    return result


async def get_review_history(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> list[ReviewRecord]:
    """Get review history for a question."""
    result = await db.execute(
        select(ReviewRecord)
        .where(ReviewRecord.question_id == question_id)
        .order_by(ReviewRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def get_pending_reviews(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Question], int]:
    """Get questions pending review."""
    return await list_questions(db, skip=skip, limit=limit, status="pending_review")


async def batch_submit_for_review(
    db: AsyncSession,
    question_ids: list[uuid.UUID],
) -> list[Question]:
    """Submit multiple draft questions for review. Skips non-draft questions."""
    submitted = []
    for qid in question_ids:
        try:
            q = await submit_for_review(db, qid)
            if q:
                submitted.append(q)
        except ValueError:
            # Skip questions that aren't in draft status
            continue
    return submitted


async def batch_review(
    db: AsyncSession,
    question_ids: list[uuid.UUID],
    action: str,
    reviewer_id: uuid.UUID,
    comment: Optional[str] = None,
) -> list[Question]:
    """Batch approve or reject questions."""
    reviewed = []
    for qid in question_ids:
        q = await review_question(db, qid, action, reviewer_id, comment)
        if q:
            reviewed.append(q)
    return reviewed


async def submit_for_review(
    db: AsyncSession, question_id: uuid.UUID
) -> Optional[Question]:
    """Submit a draft question for review."""
    q = await get_question_by_id(db, question_id)
    if not q:
        return None
    if q.status != QuestionStatus.DRAFT:
        raise ValueError(f"Only draft questions can be submitted, current status: {q.status.value}")
    q.status = QuestionStatus.PENDING_REVIEW
    await db.flush()
    return q


async def generate_from_knowledge_unit(
    db: AsyncSession,
    knowledge_unit_id: uuid.UUID,
    question_types: list[str],
    count: int = 3,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
    custom_prompt: Optional[str] = None,
) -> list[Question]:
    """Generate questions from a knowledge unit using LLM."""
    # Fetch KU
    result = await db.execute(
        select(KnowledgeUnit).where(KnowledgeUnit.id == knowledge_unit_id)
    )
    ku = result.scalar_one_or_none()
    if not ku:
        raise ValueError(f"Knowledge unit {knowledge_unit_id} not found")

    # Generate via LLM/template
    llm_result = generate_questions_via_llm(
        content=ku.content,
        question_types=question_types,
        count=count,
        difficulty=difficulty,
        bloom_level=bloom_level,
        custom_prompt=custom_prompt,
    )
    raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
    usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}

    # Create question records (with per-question error handling)
    questions = []
    for raw in raw_questions:
        try:
            # Validate question_type is a valid enum value
            qt = raw.get("question_type", question_types[0])
            try:
                QuestionType(qt)
            except ValueError:
                logger.warning(f"Invalid question_type '{qt}', skipping")
                continue

            # Ensure knowledge_tags is a list (DB column is JSONB)
            tags = raw.get("knowledge_tags")
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                tags = None

            # 维度：优先KU维度，其次LLM输出，最后自动分类
            dim = ku.dimension or raw.get("dimension")
            if not dim:
                dim = classify_dimension(raw.get("stem", ""), tags)

            q = await create_question(
                db=db,
                question_type=qt,
                stem=raw.get("stem", ""),
                correct_answer=raw.get("correct_answer", ""),
                options=raw.get("options"),
                explanation=raw.get("explanation", ""),
                difficulty=difficulty,
                dimension=dim,
                knowledge_tags=tags,
                bloom_level=bloom_level,
                source_material_id=ku.material_id,
                source_knowledge_unit_id=ku.id,
                created_by=created_by,
            )
            questions.append(q)
        except Exception as e:
            logger.error(
                f"Failed to create question from KU {knowledge_unit_id}: {e}",
                exc_info=True,
            )
            continue

    return {"questions": questions, "usage": usage}


async def batch_generate_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    question_types: list[str],
    count_per_unit: int = 2,
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    created_by: Optional[uuid.UUID] = None,
) -> list[Question]:
    """Generate questions from all knowledge units of a material."""
    # Verify material exists
    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"Material {material_id} not found")

    # Fetch knowledge units
    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
        .limit(max_units)
    )
    units = list(ku_result.scalars().all())

    if not units:
        raise ValueError(f"Material {material_id} has no knowledge units. Parse the material first.")

    all_questions = []
    for ku in units:
        try:
            questions = await generate_from_knowledge_unit(
                db=db,
                knowledge_unit_id=ku.id,
                question_types=question_types,
                count=count_per_unit,
                difficulty=difficulty,
                bloom_level=bloom_level,
                created_by=created_by,
            )
            all_questions.extend(questions)
        except Exception as e:
            logger.error(
                f"Batch generation failed for KU {ku.id} in material {material_id}: {e}"
            )
            continue

    return all_questions


async def build_question_bank_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    created_by: Optional[uuid.UUID] = None,
    custom_prompt: Optional[str] = None,
) -> list[Question]:
    """Build question bank from a material with specific type distribution.

    type_distribution maps question_type -> desired count, e.g.:
    {"single_choice": 10, "true_false": 5, "short_answer": 3}
    Questions are distributed evenly across knowledge units.
    """
    from app.models.material import MaterialStatus

    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    mat_status = material.status.value if hasattr(material.status, 'value') else material.status
    if mat_status not in ("parsed", "vectorized"):
        raise ValueError(f"素材尚未解析完成，当前状态: {mat_status}")

    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
        .limit(max_units)
    )
    units = list(ku_result.scalars().all())
    if not units:
        raise ValueError("该素材没有知识单元，请先解析素材")

    all_questions: list[Question] = []
    num_units = len(units)
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {}
    start_time = time.time()

    for qtype, total_count in type_distribution.items():
        if total_count <= 0:
            continue
        # Distribute count across units
        base = total_count // num_units
        remainder = total_count % num_units

        for i, ku in enumerate(units):
            count_for_unit = base + (1 if i < remainder else 0)
            if count_for_unit <= 0:
                continue
            result = await generate_from_knowledge_unit(
                db=db,
                knowledge_unit_id=ku.id,
                question_types=[qtype],
                count=count_for_unit,
                difficulty=difficulty,
                bloom_level=bloom_level,
                created_by=created_by,
                custom_prompt=custom_prompt,
            )
            questions = result.get("questions", result) if isinstance(result, dict) else result
            usage = result.get("usage", {}) if isinstance(result, dict) else {}
            all_questions.extend(questions)
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

        type_counts[qtype] = len([q for q in all_questions if q.question_type.value == qtype or q.question_type == qtype])

    duration = round(time.time() - start_time, 2)
    stats = {**total_usage, "duration_seconds": duration, "type_counts": type_counts}
    return {"questions": all_questions, "stats": stats}


async def suggest_question_distribution(
    db: AsyncSession,
    material_id: uuid.UUID,
) -> dict:
    """Analyze a material and suggest optimal question type distribution."""
    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
    )
    units = list(ku_result.scalars().all())
    total_units = len(units)

    if total_units == 0:
        raise ValueError("该素材没有知识单元，请先解析素材")

    total_content_length = sum(len(u.content or "") for u in units)

    # Determine total question count based on material size
    if total_units <= 3:
        total_questions = min(max(total_units * 3, 6), 12)
    elif total_units <= 8:
        total_questions = min(total_units * 3, 25)
    else:
        total_questions = min(total_units * 3, 40)

    # Boost for longer content
    if total_content_length > 5000:
        total_questions = min(total_questions + 5, 40)

    # Distribute by type ratios: single 40%, true_false 20%, multiple 15%, short_answer 15%, fill_blank 10%
    dist = {
        "single_choice": max(1, round(total_questions * 0.40)),
        "multiple_choice": max(0, round(total_questions * 0.15)),
        "true_false": max(1, round(total_questions * 0.20)),
        "fill_blank": max(0, round(total_questions * 0.10)),
        "short_answer": max(0, round(total_questions * 0.15)),
    }

    # Determine average difficulty from knowledge units
    difficulties = [u.difficulty for u in units if u.difficulty]
    avg_difficulty = round(sum(difficulties) / len(difficulties)) if difficulties else 3

    actual_total = sum(dist.values())

    return {
        "material_id": str(material_id),
        "material_title": material.title,
        "total_units": total_units,
        "suggested_distribution": dist,
        "suggested_total": actual_total,
        "difficulty": avg_difficulty,
    }


async def generate_questions_free(
    db: AsyncSession,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    created_by: Optional[uuid.UUID] = None,
) -> list[Question]:
    """Generate questions without material, using LLM's own knowledge."""
    all_questions: list[Question] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {}
    start_time = time.time()

    for qtype, count in type_distribution.items():
        if count <= 0:
            continue
        llm_result = generate_questions_via_llm(
            content="",
            question_types=[qtype],
            count=count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
        )
        raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
        usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)
        for raw in raw_questions:
            try:
                qt = raw.get("question_type", qtype)
                try:
                    QuestionType(qt)
                except ValueError:
                    logger.warning(f"Free generate: invalid question_type '{qt}', skipping")
                    continue

                tags = raw.get("knowledge_tags")
                if isinstance(tags, str):
                    tags = [tags]
                if not isinstance(tags, list):
                    tags = None

                # 维度：优先使用LLM输出的dimension，否则自动分类
                dim = raw.get("dimension")
                if not dim:
                    dim = classify_dimension(raw.get("stem", ""), tags)

                q = await create_question(
                    db=db,
                    question_type=qt,
                    stem=raw.get("stem", ""),
                    correct_answer=raw.get("correct_answer", ""),
                    options=raw.get("options"),
                    explanation=raw.get("explanation", ""),
                    difficulty=difficulty,
                    dimension=dim,
                    knowledge_tags=tags,
                    bloom_level=bloom_level,
                    source_material_id=None,
                    source_knowledge_unit_id=None,
                    created_by=created_by,
                )
                all_questions.append(q)
            except Exception as e:
                logger.error(f"Free generate: failed to create question: {e}")
                continue

        type_counts[qtype] = len([q for q in all_questions if q.question_type.value == qtype or q.question_type == qtype])

    duration = round(time.time() - start_time, 2)
    stats = {**total_usage, "duration_seconds": duration, "type_counts": type_counts}
    return {"questions": all_questions, "stats": stats}


async def preview_question_bank_from_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    max_units: int = 10,
    custom_prompt: Optional[str] = None,
) -> dict:
    """Preview question bank generation WITHOUT saving to DB.

    Same LLM logic as build_question_bank_from_material but returns raw dicts.
    """
    from app.models.material import MaterialStatus

    mat_result = await db.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_result.scalar_one_or_none()
    if not material:
        raise ValueError(f"素材 {material_id} 不存在")

    mat_status = material.status.value if hasattr(material.status, 'value') else material.status
    if mat_status not in ("parsed", "vectorized"):
        raise ValueError(f"素材尚未解析完成，当前状态: {mat_status}")

    ku_result = await db.execute(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.material_id == material_id)
        .order_by(KnowledgeUnit.chunk_index)
        .limit(max_units)
    )
    units = list(ku_result.scalars().all())
    if not units:
        raise ValueError("该素材没有知识单元，请先解析素材")

    all_preview: list[dict] = []
    num_units = len(units)
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {}
    start_time = time.time()

    for qtype, total_count in type_distribution.items():
        if total_count <= 0:
            continue
        base = total_count // num_units
        remainder = total_count % num_units
        type_generated = 0

        for i, ku in enumerate(units):
            count_for_unit = base + (1 if i < remainder else 0)
            if count_for_unit <= 0:
                continue

            llm_result = generate_questions_via_llm(
                content=ku.content,
                question_types=[qtype],
                count=count_for_unit,
                difficulty=difficulty,
                bloom_level=bloom_level,
                custom_prompt=custom_prompt,
            )
            raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
            usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

            for raw in raw_questions:
                tags = raw.get("knowledge_tags")
                if isinstance(tags, str):
                    tags = [tags]
                if not isinstance(tags, list):
                    tags = None

                dim = ku.dimension or raw.get("dimension")
                if not dim:
                    dim = classify_dimension(raw.get("stem", ""), tags)

                all_preview.append({
                    "question_type": raw.get("question_type", qtype),
                    "stem": raw.get("stem", ""),
                    "options": raw.get("options"),
                    "correct_answer": raw.get("correct_answer", ""),
                    "explanation": raw.get("explanation", ""),
                    "difficulty": difficulty,
                    "dimension": dim,
                    "knowledge_tags": tags,
                    "bloom_level": bloom_level,
                    "source_material_id": str(ku.material_id),
                    "source_knowledge_unit_id": str(ku.id),
                })
                type_generated += 1

        type_counts[qtype] = type_generated

    duration = round(time.time() - start_time, 2)
    stats = {**total_usage, "duration_seconds": duration, "type_counts": type_counts}
    return {"questions": all_preview, "stats": stats}


def preview_questions_free(
    type_distribution: dict[str, int],
    difficulty: int = 3,
    bloom_level: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> dict:
    """Preview question generation without material. No DB involvement."""
    all_preview: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    type_counts: dict[str, int] = {}
    start_time = time.time()

    for qtype, count in type_distribution.items():
        if count <= 0:
            continue
        llm_result = generate_questions_via_llm(
            content="",
            question_types=[qtype],
            count=count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            custom_prompt=custom_prompt,
        )
        raw_questions = llm_result.get("questions", llm_result) if isinstance(llm_result, dict) else llm_result
        usage = llm_result.get("usage", {}) if isinstance(llm_result, dict) else {}
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)

        type_generated = 0
        for raw in raw_questions:
            tags = raw.get("knowledge_tags")
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                tags = None

            dim = raw.get("dimension")
            if not dim:
                dim = classify_dimension(raw.get("stem", ""), tags)

            all_preview.append({
                "question_type": raw.get("question_type", qtype),
                "stem": raw.get("stem", ""),
                "options": raw.get("options"),
                "correct_answer": raw.get("correct_answer", ""),
                "explanation": raw.get("explanation", ""),
                "difficulty": difficulty,
                "dimension": dim,
                "knowledge_tags": tags,
                "bloom_level": bloom_level,
                "source_material_id": None,
                "source_knowledge_unit_id": None,
            })
            type_generated += 1

        type_counts[qtype] = type_generated

    duration = round(time.time() - start_time, 2)
    stats = {**total_usage, "duration_seconds": duration, "type_counts": type_counts}
    return {"questions": all_preview, "stats": stats}


async def batch_create_from_raw(
    db: AsyncSession,
    raw_questions: list[dict],
    created_by: Optional[uuid.UUID] = None,
) -> list:
    """Batch save preview question dicts to DB. Used after user review."""
    questions = []
    for raw in raw_questions:
        try:
            qt = raw.get("question_type", "single_choice")
            try:
                QuestionType(qt)
            except ValueError:
                logger.warning(f"batch_create_from_raw: invalid type '{qt}', skipping")
                continue

            q = await create_question(
                db=db,
                question_type=qt,
                stem=raw.get("stem", ""),
                correct_answer=raw.get("correct_answer", ""),
                options=raw.get("options"),
                explanation=raw.get("explanation", ""),
                difficulty=raw.get("difficulty", 3),
                dimension=raw.get("dimension"),
                knowledge_tags=raw.get("knowledge_tags"),
                bloom_level=raw.get("bloom_level"),
                source_material_id=_coerce_uuid(raw.get("source_material_id")),
                source_knowledge_unit_id=_coerce_uuid(raw.get("source_knowledge_unit_id")),
                created_by=created_by,
            )
            questions.append(q)
        except Exception as e:
            logger.error(f"batch_create_from_raw: failed: {e}", exc_info=True)
            continue
    return questions


async def get_question_stats(
    db: AsyncSession,
    dimension: Optional[str] = None,
) -> dict:
    """Get question bank statistics."""
    conditions = []
    if dimension:
        conditions.append(Question.dimension == dimension)

    where_clause = and_(*conditions) if conditions else True

    total = (await db.execute(
        select(func.count(Question.id)).where(where_clause)
    )).scalar()

    # Count by status
    status_q = (
        select(Question.status, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.status)
    )
    status_result = await db.execute(status_q)
    by_status = {row[0].value: row[1] for row in status_result.all()}

    # Count by type
    type_q = (
        select(Question.question_type, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.question_type)
    )
    type_result = await db.execute(type_q)
    by_type = {row[0].value: row[1] for row in type_result.all()}

    # Count by difficulty
    diff_q = (
        select(Question.difficulty, func.count(Question.id))
        .where(where_clause)
        .group_by(Question.difficulty)
    )
    diff_result = await db.execute(diff_q)
    by_difficulty = {str(row[0]): row[1] for row in diff_result.all()}

    return {
        "total": total,
        "by_status": by_status,
        "by_type": by_type,
        "by_difficulty": by_difficulty,
    }
