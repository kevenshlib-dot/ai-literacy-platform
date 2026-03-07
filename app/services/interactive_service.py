"""Interactive session service - manages multi-turn SJT scenario dialogues."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.interactive import (
    InteractiveSession,
    InteractiveTurn,
    InteractiveSessionStatus,
)
from app.agents.interactive_agent import generate_scenario_response, generate_session_summary


async def start_interactive_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    scenario: str,
    role_description: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: int = 3,
    max_turns: int = 6,
    answer_sheet_id: Optional[uuid.UUID] = None,
    question_id: Optional[uuid.UUID] = None,
    evaluation_criteria: Optional[dict] = None,
) -> InteractiveSession:
    """Start a new interactive scenario session."""
    session = InteractiveSession(
        user_id=user_id,
        answer_sheet_id=answer_sheet_id,
        question_id=question_id,
        scenario=scenario,
        role_description=role_description,
        dimension=dimension,
        current_difficulty=difficulty,
        max_turns=max_turns,
        evaluation_criteria=evaluation_criteria,
    )
    db.add(session)
    await db.flush()

    # Generate opening scenario message
    opening = generate_scenario_response(
        scenario=scenario,
        role_description=role_description or "AI评测教练",
        dimension=dimension or "AI综合素养",
        difficulty=difficulty,
        conversation_history=[],
        user_message="[开始情境对话]",
    )

    turn = InteractiveTurn(
        session_id=session.id,
        turn_number=1,
        role="system",
        content=opening["response"],
        ai_analysis=opening.get("analysis"),
    )
    db.add(turn)
    await db.flush()

    return session


async def submit_interactive_response(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message: str,
) -> dict:
    """Process user response and generate next scenario turn."""
    session = await get_session_with_turns(db, session_id)
    if not session:
        raise ValueError("交互会话不存在")
    if session.user_id != user_id:
        raise ValueError("无权操作此会话")
    if session.status != InteractiveSessionStatus.ACTIVE:
        raise ValueError("会话已结束")

    # Count user turns
    user_turns = [t for t in session.turns if t.role == "user"]
    current_turn = len(session.turns) + 1

    # Add user turn
    user_turn = InteractiveTurn(
        session_id=session_id,
        turn_number=current_turn,
        role="user",
        content=user_message,
    )
    db.add(user_turn)

    # Build conversation history
    history = [
        {"role": t.role, "content": t.content, "ai_analysis": t.ai_analysis}
        for t in session.turns
    ]

    # Generate AI response
    result = generate_scenario_response(
        scenario=session.scenario,
        role_description=session.role_description or "AI评测教练",
        dimension=session.dimension or "AI综合素养",
        difficulty=session.current_difficulty,
        conversation_history=history,
        user_message=user_message,
    )

    # Apply difficulty adjustment
    diff_adj = result.get("difficulty_adjustment", 0)
    new_difficulty = max(1, min(5, session.current_difficulty + diff_adj))
    session.current_difficulty = new_difficulty

    # Check if session should end
    max_user_turns = session.max_turns // 2  # Each round = 1 user + 1 system turn
    should_end = result.get("should_end", False) or len(user_turns) + 1 >= max_user_turns

    # Add system response turn
    system_turn = InteractiveTurn(
        session_id=session_id,
        turn_number=current_turn + 1,
        role="system",
        content=result["response"],
        ai_analysis=result.get("analysis"),
        difficulty_adjustment=diff_adj,
    )
    db.add(system_turn)

    if should_end:
        session.status = InteractiveSessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)

        # Generate summary
        all_turns = history + [
            {"role": "user", "content": user_message, "ai_analysis": None},
            {"role": "system", "content": result["response"], "ai_analysis": result.get("analysis")},
        ]
        summary = generate_session_summary(
            scenario=session.scenario,
            dimension=session.dimension,
            turns=all_turns,
        )
        session.final_summary = summary

    await db.flush()

    return {
        "turn_number": current_turn + 1,
        "ai_response": result["response"],
        "analysis": result.get("analysis"),
        "difficulty": new_difficulty,
        "is_completed": should_end,
        "summary": session.final_summary if should_end else None,
    }


async def get_session_with_turns(
    db: AsyncSession, session_id: uuid.UUID
) -> Optional[InteractiveSession]:
    result = await db.execute(
        select(InteractiveSession)
        .where(InteractiveSession.id == session_id)
        .options(selectinload(InteractiveSession.turns))
    )
    return result.scalar_one_or_none()


async def get_session_by_id(
    db: AsyncSession, session_id: uuid.UUID
) -> Optional[InteractiveSession]:
    result = await db.execute(
        select(InteractiveSession).where(InteractiveSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def list_user_interactive_sessions(
    db: AsyncSession, user_id: uuid.UUID
) -> list[InteractiveSession]:
    result = await db.execute(
        select(InteractiveSession)
        .where(InteractiveSession.user_id == user_id)
        .order_by(InteractiveSession.created_at.desc())
    )
    return list(result.scalars().all())


async def end_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> InteractiveSession:
    """Manually end an interactive session."""
    session = await get_session_with_turns(db, session_id)
    if not session:
        raise ValueError("交互会话不存在")
    if session.user_id != user_id:
        raise ValueError("无权操作此会话")
    if session.status != InteractiveSessionStatus.ACTIVE:
        raise ValueError("会话已结束")

    session.status = InteractiveSessionStatus.COMPLETED
    session.completed_at = datetime.now(timezone.utc)

    # Generate summary from existing turns
    turns_data = [
        {"role": t.role, "content": t.content, "ai_analysis": t.ai_analysis}
        for t in session.turns
    ]
    summary = generate_session_summary(
        scenario=session.scenario,
        dimension=session.dimension,
        turns=turns_data,
    )
    session.final_summary = summary

    await db.flush()
    return session
