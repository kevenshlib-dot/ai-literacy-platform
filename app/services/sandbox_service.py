"""Practice sandbox service - prompt engineering & AI tool simulation."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sandbox import (
    SandboxSession, SandboxAttempt,
    SandboxType, SandboxSessionStatus,
)
from app.core.config import settings

# Pre-built practice tasks
PRACTICE_TASKS = {
    "prompt_engineering": [
        {
            "title": "文本摘要提示词设计",
            "description": "设计一个高质量的文本摘要提示词",
            "task_prompt": "请编写一个提示词，让AI模型能够准确地将一篇长文本压缩为100字以内的摘要，保留关键信息。",
            "dimension": "AI技术应用",
            "difficulty": 2,
        },
        {
            "title": "多轮对话提示词优化",
            "description": "优化多轮对话的提示词策略",
            "task_prompt": "设计一个多轮对话的系统提示词，使AI能够在客服场景中保持上下文连贯性，准确理解用户意图。",
            "dimension": "AI技术应用",
            "difficulty": 3,
        },
        {
            "title": "安全对齐提示词",
            "description": "编写防注入的安全提示词",
            "task_prompt": "设计一个能够防范提示词注入攻击的安全系统提示词，确保AI不会执行恶意指令。",
            "dimension": "AI伦理安全",
            "difficulty": 4,
        },
    ],
    "ai_tool_simulation": [
        {
            "title": "图像分类工具使用",
            "description": "模拟使用AI图像分类API",
            "task_prompt": "使用模拟的图像分类API，完成以下任务：对一组图片进行分类，并解释分类结果的含义和局限性。",
            "dimension": "AI技术应用",
            "difficulty": 2,
        },
        {
            "title": "数据偏见检测",
            "description": "检测AI模型中的数据偏见",
            "task_prompt": "分析给定的AI模型输出结果，识别其中可能存在的数据偏见，并提出改进建议。",
            "dimension": "AI批判思维",
            "difficulty": 3,
        },
    ],
    "code_generation": [
        {
            "title": "AI辅助代码生成",
            "description": "利用AI工具生成代码",
            "task_prompt": "使用提示词引导AI生成一个Python函数，该函数能够计算文本的情感倾向得分。评估AI生成代码的质量。",
            "dimension": "AI创新实践",
            "difficulty": 3,
        },
    ],
    "data_analysis": [
        {
            "title": "AI数据分析任务",
            "description": "使用AI工具进行数据分析",
            "task_prompt": "使用AI工具分析一组学生考试成绩数据，找出成绩分布规律并提出教学改进建议。",
            "dimension": "AI基础知识",
            "difficulty": 2,
        },
    ],
}


async def list_practice_tasks(
    sandbox_type: Optional[str] = None,
    dimension: Optional[str] = None,
) -> list[dict]:
    """List available practice tasks."""
    tasks = []
    for stype, items in PRACTICE_TASKS.items():
        if sandbox_type and stype != sandbox_type:
            continue
        for item in items:
            if dimension and item.get("dimension") != dimension:
                continue
            tasks.append({**item, "sandbox_type": stype})
    return tasks


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    sandbox_type: str,
    title: str,
    task_prompt: str,
    description: Optional[str] = None,
    dimension: Optional[str] = None,
    difficulty: int = 3,
) -> SandboxSession:
    """Create a new sandbox session."""
    session = SandboxSession(
        user_id=user_id,
        sandbox_type=sandbox_type,
        title=title,
        task_prompt=task_prompt,
        description=description,
        dimension=dimension,
        difficulty=difficulty,
    )
    db.add(session)
    await db.flush()
    return session


async def submit_attempt(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_input: str,
) -> SandboxAttempt:
    """Submit an attempt and get AI feedback."""
    # Get session with attempts
    session = (await db.execute(
        select(SandboxSession)
        .options(selectinload(SandboxSession.attempts))
        .where(SandboxSession.id == session_id)
    )).scalar_one_or_none()

    if not session:
        raise ValueError("会话不存在")
    if session.status != SandboxSessionStatus.ACTIVE:
        raise ValueError("会话已结束")

    attempt_num = len(session.attempts) + 1

    # Evaluate the attempt
    evaluation = _evaluate_attempt(
        sandbox_type=session.sandbox_type.value if hasattr(session.sandbox_type, 'value') else session.sandbox_type,
        task_prompt=session.task_prompt,
        user_input=user_input,
        attempt_number=attempt_num,
    )

    attempt = SandboxAttempt(
        session_id=session_id,
        attempt_number=attempt_num,
        user_input=user_input,
        ai_output=evaluation["ai_response"],
        feedback=evaluation["feedback"],
        score=evaluation["score"],
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def complete_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> SandboxSession:
    """Complete a sandbox session and generate final evaluation."""
    session = (await db.execute(
        select(SandboxSession)
        .options(selectinload(SandboxSession.attempts))
        .where(SandboxSession.id == session_id)
    )).scalar_one_or_none()

    if not session:
        raise ValueError("会话不存在")

    # Calculate final score from attempts
    if session.attempts:
        scores = [a.score for a in session.attempts if a.score is not None]
        best_score = max(scores) if scores else 0
        avg_score = sum(scores) / len(scores) if scores else 0
    else:
        best_score = 0
        avg_score = 0

    session.status = SandboxSessionStatus.COMPLETED
    session.completed_at = datetime.now(timezone.utc)
    session.score = best_score
    session.evaluation = {
        "total_attempts": len(session.attempts),
        "best_score": best_score,
        "average_score": round(avg_score, 1),
        "improvement": _calculate_improvement(session.attempts),
        "feedback_summary": _generate_feedback_summary(session.attempts),
    }
    await db.flush()
    return session


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> Optional[SandboxSession]:
    """Get a sandbox session with attempts."""
    result = await db.execute(
        select(SandboxSession)
        .options(selectinload(SandboxSession.attempts))
        .where(SandboxSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def list_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    sandbox_type: Optional[str] = None,
) -> list[SandboxSession]:
    """List sessions for a user."""
    query = (
        select(SandboxSession)
        .options(selectinload(SandboxSession.attempts))
        .where(SandboxSession.user_id == user_id)
        .order_by(SandboxSession.created_at.desc())
    )
    if sandbox_type:
        query = query.where(SandboxSession.sandbox_type == sandbox_type)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_user_practice_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Get practice statistics for a user."""
    sessions = await list_user_sessions(db, user_id)

    total = len(sessions)
    completed = sum(1 for s in sessions if s.status == SandboxSessionStatus.COMPLETED)
    scores = [s.score for s in sessions if s.score is not None]

    by_type = {}
    for s in sessions:
        stype = s.sandbox_type.value if hasattr(s.sandbox_type, 'value') else s.sandbox_type
        if stype not in by_type:
            by_type[stype] = {"total": 0, "completed": 0}
        by_type[stype]["total"] += 1
        if s.status == SandboxSessionStatus.COMPLETED:
            by_type[stype]["completed"] += 1

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "best_score": max(scores) if scores else 0,
        "by_type": by_type,
    }


def _evaluate_attempt(
    sandbox_type: str,
    task_prompt: str,
    user_input: str,
    attempt_number: int,
) -> dict:
    """Evaluate a user's attempt (rule-based fallback)."""
    # Score based on input quality indicators
    score = 50.0  # base score
    feedback_points = []

    input_len = len(user_input)

    # Length check
    if input_len < 20:
        feedback_points.append({"aspect": "长度", "comment": "输入过短，请提供更详细的内容", "delta": -10})
        score -= 10
    elif input_len > 100:
        feedback_points.append({"aspect": "长度", "comment": "内容充实，描述详细", "delta": 10})
        score += 10

    # Structure check
    if any(kw in user_input for kw in ["请", "要求", "步骤", "格式"]):
        feedback_points.append({"aspect": "结构性", "comment": "包含明确的指令结构", "delta": 15})
        score += 15

    # Context/specificity
    if any(kw in user_input for kw in ["例如", "比如", "场景", "上下文", "背景"]):
        feedback_points.append({"aspect": "具体性", "comment": "提供了具体的上下文或示例", "delta": 10})
        score += 10

    # Constraint specification
    if any(kw in user_input for kw in ["限制", "不要", "避免", "约束", "范围"]):
        feedback_points.append({"aspect": "约束条件", "comment": "设定了明确的约束条件", "delta": 10})
        score += 10

    # Role specification
    if any(kw in user_input for kw in ["角色", "作为", "你是", "扮演"]):
        feedback_points.append({"aspect": "角色设定", "comment": "包含角色设定，有助于提高输出质量", "delta": 5})
        score += 5

    score = max(0, min(100, score))

    # Generate AI simulation response
    ai_response = _simulate_ai_response(sandbox_type, user_input)

    return {
        "score": round(score, 1),
        "ai_response": ai_response,
        "feedback": {
            "score": round(score, 1),
            "points": feedback_points,
            "suggestion": _get_improvement_suggestion(score, feedback_points),
        },
    }


def _simulate_ai_response(sandbox_type: str, user_input: str) -> str:
    """Generate a simulated AI response."""
    if sandbox_type == "prompt_engineering":
        return f"[模拟AI输出] 根据您的提示词，AI生成了以下响应：基于您提供的指令，我理解您希望{user_input[:50]}...。以下是根据要求生成的内容。"
    elif sandbox_type == "ai_tool_simulation":
        return "[模拟工具输出] 分类结果：类别A(置信度: 0.85), 类别B(置信度: 0.12), 其他(置信度: 0.03)"
    elif sandbox_type == "code_generation":
        return "[模拟代码输出] def analyze_sentiment(text):\n    # AI生成的情感分析函数\n    positive_words = [...]\n    score = sum(1 for w in text.split() if w in positive_words)\n    return score / len(text.split())"
    else:
        return "[模拟分析输出] 数据分析完成。发现数据呈正态分布，均值为75.3，标准差为12.8。建议关注低于60分的学生群体。"


def _get_improvement_suggestion(score: float, points: list[dict]) -> str:
    """Generate improvement suggestion based on score."""
    if score >= 80:
        return "提示词质量优秀！可以尝试更复杂的场景。"
    elif score >= 60:
        return "提示词质量良好。建议增加更多约束条件和具体示例来进一步提升。"
    elif score >= 40:
        return "提示词需要改进。建议：1)增加具体的上下文描述 2)明确输出格式要求 3)添加约束条件"
    else:
        return "提示词质量较低。建议从基础开始：明确任务目标、提供上下文、设定角色、指定输出格式。"


def _calculate_improvement(attempts: list) -> float:
    """Calculate improvement across attempts."""
    if len(attempts) < 2:
        return 0.0
    scores = [a.score for a in sorted(attempts, key=lambda a: a.attempt_number) if a.score is not None]
    if len(scores) < 2:
        return 0.0
    return round(scores[-1] - scores[0], 1)


def _generate_feedback_summary(attempts: list) -> str:
    """Generate a summary of all attempts."""
    if not attempts:
        return "未完成任何尝试"
    count = len(attempts)
    scores = [a.score for a in attempts if a.score is not None]
    if not scores:
        return f"共{count}次尝试"
    return f"共{count}次尝试，最高分{max(scores):.0f}，平均分{sum(scores)/len(scores):.0f}"
