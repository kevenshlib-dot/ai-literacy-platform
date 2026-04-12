"""Paper service - handles paper CRUD, section management, question assembly, and lifecycle."""
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.paper import Paper, PaperSection, PaperQuestion, PaperStatus
from app.models.question import Question, QuestionStatus, QuestionType, BloomLevel
from app.models.exam import Exam, ExamQuestion, ExamStatus


# ──────────────────────────────────────────────
# Paper CRUD
# ──────────────────────────────────────────────

async def create_paper(
    db: AsyncSession,
    title: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
    time_limit_minutes: Optional[int] = None,
    tags: Optional[list] = None,
) -> Paper:
    paper = Paper(
        title=title,
        description=description,
        time_limit_minutes=time_limit_minutes,
        tags=tags,
        created_by=created_by,
        status=PaperStatus.DRAFT,
    )
    db.add(paper)
    await db.flush()
    return paper


async def get_paper_by_id(
    db: AsyncSession,
    paper_id: uuid.UUID,
    load_relations: bool = False,
) -> Optional[Paper]:
    stmt = select(Paper).where(Paper.id == paper_id)
    if load_relations:
        stmt = stmt.options(
            selectinload(Paper.sections),
            selectinload(Paper.questions),
        )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_papers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
) -> tuple[list[dict], int]:
    """List papers with pagination, filtering, and question_count."""
    conditions = []
    if status:
        conditions.append(Paper.status == PaperStatus(status))
    else:
        # By default, exclude archived papers (they only appear on the archive page)
        conditions.append(Paper.status != PaperStatus.ARCHIVED)
    if keyword:
        conditions.append(Paper.title.ilike(f"%{keyword}%"))
    if tag:
        # tags is JSONB list – use contains operator
        conditions.append(Paper.tags.contains([tag]))

    where_clause = and_(*conditions) if conditions else True

    total = (await db.execute(
        select(func.count(Paper.id)).where(where_clause)
    )).scalar()

    # Sub-query for question count per paper
    q_count_sub = (
        select(
            PaperQuestion.paper_id,
            func.count(PaperQuestion.id).label("question_count"),
        )
        .group_by(PaperQuestion.paper_id)
        .subquery()
    )

    items_q = (
        select(Paper, func.coalesce(q_count_sub.c.question_count, 0).label("question_count"))
        .outerjoin(q_count_sub, Paper.id == q_count_sub.c.paper_id)
        .where(where_clause)
        .order_by(Paper.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(items_q)
    rows = result.all()

    papers_with_count = []
    for row in rows:
        paper = row[0]
        count = row[1]
        paper.question_count = count  # attach count to object
        papers_with_count.append(paper)

    return papers_with_count, total


async def update_paper(
    db: AsyncSession,
    paper_id: uuid.UUID,
    **kwargs,
) -> Optional[Paper]:
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(paper, key):
            setattr(paper, key, value)
    await db.flush()
    return paper


async def delete_paper(db: AsyncSession, paper_id: uuid.UUID) -> bool:
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        return False
    if paper.status not in (PaperStatus.DRAFT, PaperStatus.ARCHIVED):
        raise ValueError("只能删除草稿或已归档的试卷")

    # Detach related exams (set paper_id to NULL) to avoid FK constraint error
    await db.execute(
        update(Exam).where(Exam.paper_id == paper_id).values(paper_id=None)
    )

    await db.delete(paper)
    await db.flush()
    return True


async def publish_paper(db: AsyncSession, paper_id: uuid.UUID) -> Paper:
    """Publish a paper and auto-create a corresponding published exam."""
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")
    if not paper.questions:
        raise ValueError("试卷没有题目，无法发布")
    paper.status = PaperStatus.PUBLISHED
    await db.flush()

    # Auto-create a published exam from this paper
    exam = Exam(
        title=paper.title,
        description=paper.description,
        total_score=paper.total_score,
        time_limit_minutes=paper.time_limit_minutes,
        created_by=paper.created_by,
        status=ExamStatus.PUBLISHED,
        paper_id=paper.id,
    )
    db.add(exam)
    await db.flush()

    for pq in sorted(paper.questions, key=lambda q: q.order_num):
        eq = ExamQuestion(
            exam_id=exam.id,
            question_id=pq.question_id,
            order_num=pq.order_num,
            score=pq.score,
        )
        db.add(eq)

    paper.usage_count = (paper.usage_count or 0) + 1
    await db.flush()
    return paper


async def archive_paper(db: AsyncSession, paper_id: uuid.UUID) -> Paper:
    """Archive a paper (soft delete) and close its associated exams."""
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        raise ValueError("试卷不存在")
    paper.status = PaperStatus.ARCHIVED

    # Close all published exams linked to this paper
    await db.execute(
        update(Exam)
        .where(Exam.paper_id == paper_id, Exam.status == ExamStatus.PUBLISHED)
        .values(status=ExamStatus.CLOSED)
    )
    await db.flush()
    return paper


async def restore_paper(db: AsyncSession, paper_id: uuid.UUID) -> Paper:
    """Restore an archived paper back to draft status."""
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        raise ValueError("试卷不存在")
    if paper.status != PaperStatus.ARCHIVED:
        raise ValueError("只能恢复已归档的试卷")
    paper.status = PaperStatus.DRAFT
    await db.flush()
    return paper


async def duplicate_paper(
    db: AsyncSession,
    paper_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Paper:
    """Deep copy a paper with its sections and questions, reset to draft."""
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")

    # Create new paper
    new_paper = Paper(
        title=f"{paper.title} (副本)",
        description=paper.description,
        time_limit_minutes=paper.time_limit_minutes,
        total_score=paper.total_score,
        tags=paper.tags,
        metadata_extra=paper.metadata_extra,
        created_by=created_by,
        status=PaperStatus.DRAFT,
    )
    db.add(new_paper)
    await db.flush()

    # Map old section ids to new section ids
    section_id_map: dict[uuid.UUID, uuid.UUID] = {}
    for sec in sorted(paper.sections, key=lambda s: s.order_num):
        new_sec = PaperSection(
            paper_id=new_paper.id,
            title=sec.title,
            description=sec.description,
            order_num=sec.order_num,
            score_rule=sec.score_rule,
        )
        db.add(new_sec)
        await db.flush()
        section_id_map[sec.id] = new_sec.id

    # Copy paper questions
    for pq in sorted(paper.questions, key=lambda q: q.order_num):
        new_pq = PaperQuestion(
            paper_id=new_paper.id,
            section_id=section_id_map.get(pq.section_id) if pq.section_id else None,
            question_id=pq.question_id,
            order_num=pq.order_num,
            score=pq.score,
            stem_override=pq.stem_override,
            options_override=pq.options_override,
            question_type_override=pq.question_type_override,
            correct_answer_override=pq.correct_answer_override,
        )
        db.add(new_pq)

    await db.flush()
    return new_paper


# ──────────────────────────────────────────────
# Section management
# ──────────────────────────────────────────────

async def add_section(
    db: AsyncSession,
    paper_id: uuid.UUID,
    title: str,
    description: Optional[str] = None,
    order_num: Optional[int] = None,
    score_rule: Optional[dict] = None,
) -> PaperSection:
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        raise ValueError("试卷不存在")

    if order_num is None:
        # Auto-calculate: max existing order_num + 1
        result = await db.execute(
            select(func.coalesce(func.max(PaperSection.order_num), 0))
            .where(PaperSection.paper_id == paper_id)
        )
        order_num = result.scalar() + 1

    section = PaperSection(
        paper_id=paper_id,
        title=title,
        description=description,
        order_num=order_num,
        score_rule=score_rule,
    )
    db.add(section)
    await db.flush()
    return section


async def update_section(
    db: AsyncSession,
    section_id: uuid.UUID,
    **kwargs,
) -> Optional[PaperSection]:
    result = await db.execute(
        select(PaperSection).where(PaperSection.id == section_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(section, key):
            setattr(section, key, value)
    await db.flush()
    return section


async def delete_section(db: AsyncSession, section_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(PaperSection).where(PaperSection.id == section_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        return False

    # Detach questions from this section (set section_id to NULL)
    await db.execute(
        update(PaperQuestion)
        .where(PaperQuestion.section_id == section_id)
        .values(section_id=None)
    )

    await db.delete(section)
    await db.flush()
    return True


async def reorder_sections(
    db: AsyncSession,
    paper_id: uuid.UUID,
    ordered_ids: list[uuid.UUID],
) -> list[PaperSection]:
    result = await db.execute(
        select(PaperSection).where(PaperSection.paper_id == paper_id)
    )
    sections = {s.id: s for s in result.scalars().all()}

    for idx, sid in enumerate(ordered_ids, start=1):
        if sid not in sections:
            raise ValueError(f"分节 {sid} 不属于该试卷")
        sections[sid].order_num = idx

    await db.flush()
    return [sections[sid] for sid in ordered_ids]


# ──────────────────────────────────────────────
# Question assembly
# ──────────────────────────────────────────────

async def add_questions_manual(
    db: AsyncSession,
    paper_id: uuid.UUID,
    items: list[dict],
) -> list[PaperQuestion]:
    """Manually add questions to a paper.

    Each item: {question_id, section_id?, score?, order_num?}
    Auto-calculate order_num if not provided (append to end).
    """
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        raise ValueError("试卷不存在")
    if paper.status != PaperStatus.DRAFT:
        raise ValueError("只能为草稿状态的试卷添加题目")

    # Get current max order_num
    max_order_result = await db.execute(
        select(func.coalesce(func.max(PaperQuestion.order_num), 0))
        .where(PaperQuestion.paper_id == paper_id)
    )
    next_order = max_order_result.scalar() + 1

    paper_questions = []
    for item in items:
        order = item.get("order_num")
        if order is None:
            order = next_order
            next_order += 1

        pq = PaperQuestion(
            paper_id=paper_id,
            question_id=item["question_id"],
            section_id=item.get("section_id"),
            score=item.get("score", 5.0),
            order_num=order,
        )
        db.add(pq)
        paper_questions.append(pq)

    await db.flush()

    # Recalculate total score
    await recalc_total_score(db, paper_id)

    return paper_questions


async def auto_assemble(
    db: AsyncSession,
    paper_id: uuid.UUID,
    rules: list[dict],
) -> list[PaperQuestion]:
    """Auto-assemble questions into a paper based on rules.

    Each rule: {question_type, count, score_per, difficulty?, dimension?, tags?}
    Queries approved questions from the question bank matching criteria, randomly selects.
    """
    paper = await get_paper_by_id(db, paper_id)
    if not paper:
        raise ValueError("试卷不存在")
    if paper.status != PaperStatus.DRAFT:
        raise ValueError("只能为草稿状态的试卷组卷")

    # Get current max order_num to append after existing questions
    max_order_result = await db.execute(
        select(func.coalesce(func.max(PaperQuestion.order_num), 0))
        .where(PaperQuestion.paper_id == paper_id)
    )
    order = max_order_result.scalar() + 1

    # Collect already-used question ids in this paper to avoid duplicates
    existing_result = await db.execute(
        select(PaperQuestion.question_id).where(PaperQuestion.paper_id == paper_id)
    )
    used_ids = [row[0] for row in existing_result.all()]

    paper_questions = []

    for rule in rules:
        qtype = QuestionType(rule["question_type"])
        count = rule["count"]
        score_per = rule.get("score_per", 5.0)

        conditions = [
            Question.status == QuestionStatus.APPROVED,
            Question.question_type == qtype,
        ]

        difficulty = rule.get("difficulty")
        if difficulty is not None:
            conditions.append(Question.difficulty == difficulty)

        dimension = rule.get("dimension")
        if dimension:
            conditions.append(Question.dimension == dimension)

        tags = rule.get("tags")
        if tags:
            # knowledge_tags JSONB contains any of the specified tags
            conditions.append(Question.knowledge_tags.op("?|")(tags))

        # Exclude already-used questions
        all_excluded = used_ids + [pq.question_id for pq in paper_questions]
        if all_excluded:
            conditions.append(Question.id.notin_(all_excluded))

        result = await db.execute(
            select(Question)
            .where(and_(*conditions))
            .order_by(func.random())
            .limit(count)
        )
        candidates = list(result.scalars().all())

        for q in candidates:
            pq = PaperQuestion(
                paper_id=paper_id,
                question_id=q.id,
                score=score_per,
                order_num=order,
            )
            db.add(pq)
            paper_questions.append(pq)
            order += 1

    await db.flush()
    await recalc_total_score(db, paper_id)

    return paper_questions


async def reorder_questions(
    db: AsyncSession,
    paper_id: uuid.UUID,
    ordered_ids: list[uuid.UUID],
) -> None:
    """Reorder paper questions by providing an ordered list of PaperQuestion ids."""
    result = await db.execute(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)
    )
    pqs = {pq.id: pq for pq in result.scalars().all()}

    for idx, pq_id in enumerate(ordered_ids, start=1):
        if pq_id not in pqs:
            raise ValueError(f"试卷题目 {pq_id} 不属于该试卷")
        pqs[pq_id].order_num = idx

    await db.flush()


async def update_paper_question(
    db: AsyncSession,
    pq_id: uuid.UUID,
    **kwargs,
) -> Optional[PaperQuestion]:
    result = await db.execute(
        select(PaperQuestion).where(PaperQuestion.id == pq_id)
    )
    pq = result.scalar_one_or_none()
    if not pq:
        return None
    # Fields that can be explicitly set to None (cleared)
    nullable_fields = {"stem_override", "options_override", "question_type_override", "correct_answer_override"}
    for key, value in kwargs.items():
        if not hasattr(pq, key):
            continue
        if key in nullable_fields:
            # Always apply (even None) if the key was explicitly passed
            setattr(pq, key, value)
        elif value is not None:
            setattr(pq, key, value)
    await db.flush()

    # Recalculate if score was updated
    if "score" in kwargs:
        await recalc_total_score(db, pq.paper_id)

    return pq


async def remove_paper_question(db: AsyncSession, pq_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(PaperQuestion).where(PaperQuestion.id == pq_id)
    )
    pq = result.scalar_one_or_none()
    if not pq:
        return False
    paper_id = pq.paper_id
    await db.delete(pq)
    await db.flush()
    await recalc_total_score(db, paper_id)
    return True


async def recalc_total_score(db: AsyncSession, paper_id: uuid.UUID) -> float:
    """Sum all paper_questions.score and update paper.total_score."""
    result = await db.execute(
        select(func.coalesce(func.sum(PaperQuestion.score), 0))
        .where(PaperQuestion.paper_id == paper_id)
    )
    total = result.scalar()

    paper = await get_paper_by_id(db, paper_id)
    if paper:
        paper.total_score = total
        await db.flush()
    return total


# ──────────────────────────────────────────────
# Exam integration
# ──────────────────────────────────────────────

async def materialize_to_exam(
    db: AsyncSession,
    paper_id: uuid.UUID,
    exam_title: str,
    exam_description: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    created_by: Optional[uuid.UUID] = None,
) -> Exam:
    """Create an Exam from a paper, populating exam_questions from paper_questions."""
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")
    if paper.status != PaperStatus.PUBLISHED:
        raise ValueError("只能从已发布的试卷创建考试")
    if not paper.questions:
        raise ValueError("试卷没有题目，无法创建考试")

    exam = Exam(
        title=exam_title,
        description=exam_description or paper.description,
        total_score=paper.total_score,
        time_limit_minutes=paper.time_limit_minutes,
        created_by=created_by or paper.created_by,
        status=ExamStatus.DRAFT,
        paper_id=paper_id,
        params={"paper_id": str(paper_id)},
    )
    db.add(exam)
    await db.flush()

    # Populate exam questions from paper questions
    for pq in sorted(paper.questions, key=lambda q: q.order_num):
        eq = ExamQuestion(
            exam_id=exam.id,
            question_id=pq.question_id,
            order_num=pq.order_num,
            score=pq.score,
            question_type_override=pq.question_type_override,
            correct_answer_override=pq.correct_answer_override,
        )
        db.add(eq)

    # Increment paper usage count
    paper.usage_count = (paper.usage_count or 0) + 1

    await db.flush()
    return exam


async def sync_exam_overrides(db: AsyncSession, exam_id: uuid.UUID) -> int:
    """Sync question_type_override and correct_answer_override from paper_questions to exam_questions.

    Returns the number of updated records.
    """
    exam = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam_obj = exam.scalar_one_or_none()
    if not exam_obj or not exam_obj.paper_id:
        return 0

    # Fetch paper_questions with any overrides
    pq_result = await db.execute(
        select(
            PaperQuestion.question_id,
            PaperQuestion.question_type_override,
            PaperQuestion.correct_answer_override,
        )
        .where(PaperQuestion.paper_id == exam_obj.paper_id)
        .where(
            or_(
                PaperQuestion.question_type_override.isnot(None),
                PaperQuestion.correct_answer_override.isnot(None),
            )
        )
    )
    override_map = {row[0]: (row[1], row[2]) for row in pq_result.all()}

    if not override_map:
        return 0

    # Update exam_questions
    updated = 0
    eq_result = await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )
    for eq in eq_result.scalars().all():
        overrides = override_map.get(eq.question_id)
        if not overrides:
            continue
        type_ov, answer_ov = overrides
        changed = False
        if type_ov and eq.question_type_override != type_ov:
            eq.question_type_override = type_ov
            changed = True
        if answer_ov is not None and eq.correct_answer_override != answer_ov:
            eq.correct_answer_override = answer_ov
            changed = True
        if changed:
            updated += 1

    await db.flush()
    return updated


# ──────────────────────────────────────────────
# Detail loading
# ──────────────────────────────────────────────

async def get_paper_detail(db: AsyncSession, paper_id: uuid.UUID) -> Optional[dict]:
    """Load paper with all sections (ordered) and questions (ordered), with question details joined."""
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        return None

    # Load all referenced questions in one query
    question_ids = [pq.question_id for pq in paper.questions]
    if question_ids:
        q_result = await db.execute(
            select(Question).where(Question.id.in_(question_ids))
        )
        questions_map = {q.id: q for q in q_result.scalars().all()}
    else:
        questions_map = {}

    def _serialize_question(q: Question) -> dict:
        return {
            "id": str(q.id),
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
            "stem": q.stem,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
            "dimension": q.dimension,
            "knowledge_tags": q.knowledge_tags,
            "bloom_level": q.bloom_level.value if q.bloom_level and hasattr(q.bloom_level, "value") else q.bloom_level,
            "status": q.status.value if hasattr(q.status, "value") else q.status,
        }

    def _serialize_pq(pq: PaperQuestion) -> dict:
        q = questions_map.get(pq.question_id)
        return {
            "id": str(pq.id),
            "question_id": str(pq.question_id),
            "order_num": pq.order_num,
            "score": pq.score,
            "stem_override": pq.stem_override,
            "options_override": pq.options_override,
            "question_type_override": pq.question_type_override,
            "correct_answer_override": pq.correct_answer_override,
            "question": _serialize_question(q) if q else None,
        }

    # Group questions by section
    sorted_sections = sorted(paper.sections, key=lambda s: s.order_num)
    section_pqs: dict[uuid.UUID, list[PaperQuestion]] = {s.id: [] for s in sorted_sections}
    unsectioned = []

    for pq in sorted(paper.questions, key=lambda q: q.order_num):
        if pq.section_id and pq.section_id in section_pqs:
            section_pqs[pq.section_id].append(pq)
        else:
            unsectioned.append(pq)

    sections_data = []
    for sec in sorted_sections:
        sections_data.append({
            "id": str(sec.id),
            "title": sec.title,
            "description": sec.description,
            "order_num": sec.order_num,
            "score_rule": sec.score_rule,
            "questions": [_serialize_pq(pq) for pq in section_pqs[sec.id]],
        })

    return {
        "id": str(paper.id),
        "title": paper.title,
        "description": paper.description,
        "status": paper.status.value if hasattr(paper.status, "value") else paper.status,
        "total_score": paper.total_score,
        "time_limit_minutes": paper.time_limit_minutes,
        "version": paper.version,
        "tags": paper.tags,
        "usage_count": paper.usage_count,
        "created_by": str(paper.created_by),
        "created_at": paper.created_at.isoformat() if paper.created_at else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
        "sections": sections_data,
        "unsectioned_questions": [_serialize_pq(pq) for pq in unsectioned],
    }


# ──────────────────────────────────────────────
# Sync paper questions to question bank
# ──────────────────────────────────────────────

async def sync_questions_to_bank_preview(
    db: AsyncSession,
    paper_id: uuid.UUID,
) -> dict:
    """Preview which paper questions can be synced to the question bank.

    For each paper question, determines one of these statuses:
    - 'in_bank': already in bank as approved, no overrides → skip
    - 'draft_in_bank': exists in bank but in draft/pending status → can promote
    - 'has_override': has stem/options override → will create a new question variant
    - 'missing': referenced question not found → skip (error)

    Returns summary and per-question details.
    """
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")

    question_ids = [pq.question_id for pq in paper.questions]
    if not question_ids:
        return {"items": [], "to_import": 0, "already_in_bank": 0, "total": 0}

    q_result = await db.execute(
        select(Question).where(Question.id.in_(question_ids))
    )
    questions_map = {q.id: q for q in q_result.scalars().all()}

    items = []
    to_import = 0
    already_in_bank = 0

    for pq in sorted(paper.questions, key=lambda q: q.order_num):
        q = questions_map.get(pq.question_id)
        if not q:
            items.append({
                "pq_id": str(pq.id),
                "question_id": str(pq.question_id),
                "stem": pq.stem_override or "（题目缺失）",
                "status": "missing",
                "action": "skip",
                "reason": "题目记录不存在",
            })
            continue

        has_override = bool(pq.stem_override or pq.options_override)
        is_approved = (q.status == QuestionStatus.APPROVED)

        # Determine the effective stem for display
        effective_stem = pq.stem_override or q.stem

        if has_override:
            # Paper has customized this question → create new variant in bank
            items.append({
                "pq_id": str(pq.id),
                "question_id": str(pq.question_id),
                "stem": effective_stem,
                "original_stem": q.stem,
                "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
                "status": "has_override",
                "action": "create_new",
                "reason": "题目已在试卷中被修改，将创建为新题目入库",
            })
            to_import += 1
        elif is_approved:
            # Already properly in the bank
            items.append({
                "pq_id": str(pq.id),
                "question_id": str(pq.question_id),
                "stem": q.stem,
                "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
                "status": "in_bank",
                "action": "skip",
                "reason": "已在题库中（已审核）",
            })
            already_in_bank += 1
        else:
            # Draft or pending in bank → can promote to approved
            items.append({
                "pq_id": str(pq.id),
                "question_id": str(pq.question_id),
                "stem": q.stem,
                "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
                "status": "draft_in_bank",
                "action": "promote",
                "reason": f"题目状态为「{q.status.value}」，将提升为已审核",
            })
            to_import += 1

    return {
        "items": items,
        "to_import": to_import,
        "already_in_bank": already_in_bank,
        "total": len(items),
    }


async def sync_questions_to_bank_execute(
    db: AsyncSession,
    paper_id: uuid.UUID,
    pq_ids: Optional[list[str]] = None,
    created_by: Optional[uuid.UUID] = None,
) -> dict:
    """Execute the sync: import paper questions into the question bank.

    - 'has_override' questions → create a new Question, link paper_question to it, clear overrides
    - 'draft_in_bank' questions → promote to approved status
    - 'in_bank' / 'missing' → skip

    If pq_ids is provided, only process those specific paper questions.
    Returns summary of actions taken.
    """
    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")

    question_ids = [pq.question_id for pq in paper.questions]
    if not question_ids:
        return {"created": 0, "promoted": 0, "skipped": 0, "details": []}

    q_result = await db.execute(
        select(Question).where(Question.id.in_(question_ids))
    )
    questions_map = {q.id: q for q in q_result.scalars().all()}

    created_count = 0
    promoted_count = 0
    skipped_count = 0
    details = []

    pq_id_set = set(pq_ids) if pq_ids else None

    for pq in paper.questions:
        # If specific pq_ids given, only process those
        if pq_id_set and str(pq.id) not in pq_id_set:
            continue

        q = questions_map.get(pq.question_id)
        if not q:
            skipped_count += 1
            details.append({"pq_id": str(pq.id), "action": "skipped", "reason": "题目缺失"})
            continue

        has_override = bool(pq.stem_override or pq.options_override)
        is_approved = (q.status == QuestionStatus.APPROVED)

        if has_override:
            # Create a new question from the overridden content
            new_q = Question(
                question_type=q.question_type,
                stem=pq.stem_override or q.stem,
                options=pq.options_override or q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                rubric=q.rubric,
                difficulty=q.difficulty,
                dimension=q.dimension,
                knowledge_tags=q.knowledge_tags,
                bloom_level=q.bloom_level,
                source_material_id=q.source_material_id,
                source_knowledge_unit_id=q.source_knowledge_unit_id,
                created_by=created_by or q.created_by,
                status=QuestionStatus.APPROVED,
            )
            db.add(new_q)
            await db.flush()

            # Update paper_question to point to the new question and clear overrides
            pq.question_id = new_q.id
            pq.stem_override = None
            pq.options_override = None

            created_count += 1
            details.append({
                "pq_id": str(pq.id),
                "action": "created",
                "new_question_id": str(new_q.id),
                "stem": new_q.stem[:60],
            })

        elif is_approved:
            skipped_count += 1
            details.append({"pq_id": str(pq.id), "action": "skipped", "reason": "已在题库中"})

        else:
            # Promote draft/pending question to approved
            q.status = QuestionStatus.APPROVED
            promoted_count += 1
            details.append({
                "pq_id": str(pq.id),
                "action": "promoted",
                "question_id": str(q.id),
                "stem": q.stem[:60],
            })

    await db.flush()
    return {
        "created": created_count,
        "promoted": promoted_count,
        "skipped": skipped_count,
        "details": details,
    }
