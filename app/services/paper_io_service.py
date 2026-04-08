"""Paper import/export service - handles paper serialization and deserialization."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper, PaperSection, PaperQuestion, PaperStatus
from app.models.question import Question, QuestionStatus, QuestionType

FORMAT_VERSION = "1.0"


async def export_paper(db: AsyncSession, paper_id: uuid.UUID) -> dict:
    """Export a paper to the standard JSON format with full question data."""
    from app.services.paper_service import get_paper_by_id

    paper = await get_paper_by_id(db, paper_id, load_relations=True)
    if not paper:
        raise ValueError("试卷不存在")

    # Load all referenced questions
    question_ids = [pq.question_id for pq in paper.questions]
    if question_ids:
        q_result = await db.execute(
            select(Question).where(Question.id.in_(question_ids))
        )
        questions_map = {q.id: q for q in q_result.scalars().all()}
    else:
        questions_map = {}

    def _serialize_question_full(q: Question) -> dict:
        return {
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else q.question_type,
            "stem": q.stem,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
            "dimension": q.dimension,
            "knowledge_tags": q.knowledge_tags,
            "bloom_level": q.bloom_level.value if q.bloom_level and hasattr(q.bloom_level, "value") else q.bloom_level,
        }

    def _serialize_pq(pq: PaperQuestion) -> dict:
        q = questions_map.get(pq.question_id)
        return {
            "order_num": pq.order_num,
            "score": pq.score,
            "stem_override": pq.stem_override,
            "options_override": pq.options_override,
            "question": _serialize_question_full(q) if q else None,
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
            "title": sec.title,
            "description": sec.description,
            "order_num": sec.order_num,
            "score_rule": sec.score_rule,
            "questions": [_serialize_pq(pq) for pq in section_pqs[sec.id]],
        })

    return {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "paper": {
            "title": paper.title,
            "description": paper.description,
            "total_score": paper.total_score,
            "time_limit_minutes": paper.time_limit_minutes,
            "tags": paper.tags,
            "sections": sections_data,
            "unsectioned_questions": [_serialize_pq(pq) for pq in unsectioned],
        },
    }


async def import_paper(
    db: AsyncSession,
    data: dict,
    created_by: uuid.UUID,
) -> Paper:
    """Import a paper from the standard JSON format.

    1. Validate format_version
    2. For each question: try to match existing by stem+question_type; if not found, create new in draft
    3. Create paper, sections, paper_questions
    4. Set paper status to draft
    5. Return created paper
    """
    # 1. Validate format_version
    version = data.get("format_version")
    if not version:
        raise ValueError("缺少 format_version 字段")
    if version != FORMAT_VERSION:
        raise ValueError(f"不支持的格式版本: {version}，当前支持: {FORMAT_VERSION}")

    paper_data = data.get("paper")
    if not paper_data:
        raise ValueError("缺少 paper 数据")

    # 2. Create the paper
    paper = Paper(
        title=paper_data.get("title", "导入试卷"),
        description=paper_data.get("description"),
        total_score=paper_data.get("total_score", 0),
        time_limit_minutes=paper_data.get("time_limit_minutes"),
        tags=paper_data.get("tags"),
        created_by=created_by,
        status=PaperStatus.DRAFT,
    )
    db.add(paper)
    await db.flush()

    # 3. Process sections and their questions
    total_score = 0.0
    global_order = 1

    for sec_data in paper_data.get("sections", []):
        section = PaperSection(
            paper_id=paper.id,
            title=sec_data.get("title", "未命名分节"),
            description=sec_data.get("description"),
            order_num=sec_data.get("order_num", global_order),
            score_rule=sec_data.get("score_rule"),
        )
        db.add(section)
        await db.flush()

        for q_item in sec_data.get("questions", []):
            question = await _resolve_or_create_question(db, q_item.get("question"), created_by)
            if not question:
                continue

            score = q_item.get("score", 5.0)
            pq = PaperQuestion(
                paper_id=paper.id,
                section_id=section.id,
                question_id=question.id,
                order_num=q_item.get("order_num", global_order),
                score=score,
                stem_override=q_item.get("stem_override"),
                options_override=q_item.get("options_override"),
            )
            db.add(pq)
            total_score += score
            global_order += 1

    # 4. Process unsectioned questions
    for q_item in paper_data.get("unsectioned_questions", []):
        question = await _resolve_or_create_question(db, q_item.get("question"), created_by)
        if not question:
            continue

        score = q_item.get("score", 5.0)
        pq = PaperQuestion(
            paper_id=paper.id,
            section_id=None,
            question_id=question.id,
            order_num=q_item.get("order_num", global_order),
            score=score,
            stem_override=q_item.get("stem_override"),
            options_override=q_item.get("options_override"),
        )
        db.add(pq)
        total_score += score
        global_order += 1

    # 5. Update total score
    paper.total_score = total_score
    await db.flush()

    return paper


async def _resolve_or_create_question(
    db: AsyncSession,
    q_data: Optional[dict],
    created_by: uuid.UUID,
) -> Optional[Question]:
    """Try to match an existing question by stem + question_type; if not found, create a new one in draft status."""
    if not q_data:
        return None

    stem = q_data.get("stem", "").strip()
    qtype_str = q_data.get("question_type", "")

    if not stem or not qtype_str:
        return None

    try:
        qtype = QuestionType(qtype_str)
    except ValueError:
        return None

    # Try to find existing question by stem + type
    result = await db.execute(
        select(Question).where(
            and_(
                Question.stem == stem,
                Question.question_type == qtype,
            )
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Update correct_answer if it was missing and now available
        new_answer = q_data.get("correct_answer", "")
        if new_answer and (not existing.correct_answer or existing.correct_answer.strip() == ""):
            existing.correct_answer = new_answer
        # Also update explanation if missing
        new_explanation = q_data.get("explanation")
        if new_explanation and not existing.explanation:
            existing.explanation = new_explanation
        return existing

    # Create new question in draft status
    from app.models.question import BloomLevel

    bloom = None
    bloom_str = q_data.get("bloom_level")
    if bloom_str:
        try:
            bloom = BloomLevel(bloom_str)
        except ValueError:
            bloom = None

    tags = q_data.get("knowledge_tags")
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        tags = None

    question = Question(
        question_type=qtype,
        stem=stem,
        options=q_data.get("options"),
        correct_answer=q_data.get("correct_answer", ""),
        explanation=q_data.get("explanation"),
        difficulty=q_data.get("difficulty", 3),
        dimension=q_data.get("dimension"),
        knowledge_tags=tags,
        bloom_level=bloom,
        created_by=created_by,
        status=QuestionStatus.DRAFT,
    )
    db.add(question)
    await db.flush()
    return question
