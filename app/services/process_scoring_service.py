"""Process-based scoring service for SJT interactive sessions.

Observes the full interaction history and produces three-dimensional
grading with key decision point analysis.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interactive import InteractiveSession, InteractiveSessionStatus
from app.services.interactive_service import get_session_with_turns
from app.agents.interactive_agent import generate_session_summary


async def score_interactive_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> dict:
    """Score a completed interactive session from three dimensions.

    Dimensions:
    - prompt_engineering: 提示工程能力
    - critical_thinking: 批判性思维
    - ethical_decision: 伦理决策

    Also identifies key decision points from the conversation.
    """
    session = await get_session_with_turns(db, session_id)
    if not session:
        raise ValueError("交互会话不存在")
    if session.status != InteractiveSessionStatus.COMPLETED:
        raise ValueError("会话尚未完成，无法评分")

    # If summary already exists, use it
    if session.final_summary and "dimension_scores" in session.final_summary:
        return _format_process_score(session)

    # Generate summary from turns
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

    return _format_process_score(session)


def _format_process_score(session: InteractiveSession) -> dict:
    """Format process scoring result from session data."""
    summary = session.final_summary or {}
    dim_scores = summary.get("dimension_scores", {})

    # Collect per-turn analysis for process tracking
    turn_analyses = []
    key_decisions = []
    for t in session.turns:
        if t.role == "user":
            analysis = {}
            # Get the next system turn's analysis
            for st in session.turns:
                if st.turn_number == t.turn_number + 1 and st.role == "system":
                    analysis = st.ai_analysis or {}
                    break

            turn_data = {
                "turn_number": t.turn_number,
                "user_response": t.content[:200],  # Truncate for summary
                "scores": {
                    "prompt_engineering": analysis.get("prompt_engineering", 0),
                    "critical_thinking": analysis.get("critical_thinking", 0),
                    "ethical_decision": analysis.get("ethical_decision", 0),
                },
            }
            turn_analyses.append(turn_data)

            # Identify key decisions (turns with strong ethical/critical scores)
            pe = analysis.get("prompt_engineering", 0)
            ct = analysis.get("critical_thinking", 0)
            ed = analysis.get("ethical_decision", 0)
            if pe >= 7 or ct >= 7 or ed >= 7:
                key_decisions.append({
                    "turn": t.turn_number,
                    "type": "positive",
                    "description": f"在第{t.turn_number}轮表现出色",
                    "highlight_dim": (
                        "prompt_engineering" if pe >= ct and pe >= ed
                        else "critical_thinking" if ct >= ed
                        else "ethical_decision"
                    ),
                })
            elif pe <= 3 and ct <= 3 and ed <= 3:
                key_decisions.append({
                    "turn": t.turn_number,
                    "type": "concern",
                    "description": f"第{t.turn_number}轮回答需要改进",
                    "highlight_dim": "overall",
                })

    # Calculate trend (improvement over turns)
    trend = "stable"
    if len(turn_analyses) >= 2:
        first_avg = sum(turn_analyses[0]["scores"].values()) / 3
        last_avg = sum(turn_analyses[-1]["scores"].values()) / 3
        if last_avg > first_avg + 1:
            trend = "improving"
        elif last_avg < first_avg - 1:
            trend = "declining"

    return {
        "session_id": str(session.id),
        "scenario": session.scenario,
        "dimension": session.dimension,
        "status": session.status.value if hasattr(session.status, 'value') else session.status,
        "overall_score": summary.get("overall_score", 0),
        "dimension_scores": {
            "prompt_engineering": dim_scores.get("prompt_engineering", {"score": 0, "comment": ""}),
            "critical_thinking": dim_scores.get("critical_thinking", {"score": 0, "comment": ""}),
            "ethical_decision": dim_scores.get("ethical_decision", {"score": 0, "comment": ""}),
        },
        "turn_analyses": turn_analyses,
        "key_decisions": key_decisions or summary.get("key_decisions", []),
        "trend": trend,
        "total_turns": len(session.turns),
        "user_turns": len(turn_analyses),
        "strengths": summary.get("strengths", []),
        "weaknesses": summary.get("weaknesses", []),
        "recommendations": summary.get("recommendations", []),
    }
