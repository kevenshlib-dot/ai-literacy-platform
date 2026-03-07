"""Indicator service - orchestrates three-agent pipeline for indicator proposals."""
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.indicator import IndicatorProposal, ProposalStatus
from app.agents.indicator_agents import research_agent, consultant_agent, review_agent


async def generate_indicator_proposals(
    db: AsyncSession,
    topic: Optional[str] = None,
) -> dict:
    """Run the three-agent pipeline to generate indicator update proposals.

    1. Research Agent: identify AI field trends
    2. Consultant Agent: map to five-dimension framework
    3. Review Agent: red-team audit
    """
    # Step 1: Research
    research_findings = research_agent(topic)

    # Step 2: Consult
    proposals = consultant_agent(research_findings)

    # Step 3: Review
    reviews = review_agent(proposals)

    # Save approved proposals
    saved = []
    for i, proposal in enumerate(proposals):
        review = reviews[i] if i < len(reviews) else {}
        approved = review.get("approved", False)

        record = IndicatorProposal(
            title=proposal.get("title", "未命名建议"),
            dimension=proposal.get("dimension", "AI基础知识"),
            proposal_type=proposal.get("proposal_type", "new_indicator"),
            description=proposal.get("description", ""),
            rationale=proposal.get("rationale"),
            research_summary=_summarize_finding(research_findings, i),
            consultant_mapping=proposal,
            review_result=review,
            status=ProposalStatus.REVIEWED if approved else ProposalStatus.DRAFT,
            confidence_score=review.get("confidence_score"),
            created_by="system",
        )
        db.add(record)
        saved.append({
            "title": record.title,
            "dimension": record.dimension,
            "status": record.status.value if hasattr(record.status, 'value') else record.status,
            "approved": approved,
            "confidence": review.get("confidence_score"),
        })

    await db.flush()

    return {
        "research_findings_count": len(research_findings.get("findings", [])),
        "proposals_generated": len(proposals),
        "proposals_approved": sum(1 for s in saved if s["approved"]),
        "proposals": saved,
        "research_summary": research_findings,
    }


async def list_proposals(
    db: AsyncSession,
    status: Optional[str] = None,
    dimension: Optional[str] = None,
) -> list[dict]:
    """List indicator proposals with optional filters."""
    conditions = []
    if status:
        conditions.append(IndicatorProposal.status == status)
    if dimension:
        conditions.append(IndicatorProposal.dimension == dimension)

    query = select(IndicatorProposal).order_by(IndicatorProposal.created_at.desc())
    if conditions:
        query = query.where(*conditions)

    result = await db.execute(query)
    proposals = list(result.scalars().all())

    return [
        {
            "id": str(p.id),
            "title": p.title,
            "dimension": p.dimension,
            "proposal_type": p.proposal_type,
            "description": p.description,
            "rationale": p.rationale,
            "status": p.status.value if hasattr(p.status, 'value') else p.status,
            "confidence_score": p.confidence_score,
            "review_result": p.review_result,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in proposals
    ]


async def approve_proposal(
    db: AsyncSession,
    proposal_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict:
    """Manually approve a proposal (human confirmation step)."""
    proposal = (await db.execute(
        select(IndicatorProposal).where(IndicatorProposal.id == proposal_id)
    )).scalar_one_or_none()

    if not proposal:
        raise ValueError("建议不存在")

    proposal.status = ProposalStatus.APPROVED
    proposal.reviewed_by = reviewer_id
    await db.flush()

    return {
        "id": str(proposal.id),
        "title": proposal.title,
        "status": "approved",
    }


async def reject_proposal(
    db: AsyncSession,
    proposal_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict:
    """Manually reject a proposal."""
    proposal = (await db.execute(
        select(IndicatorProposal).where(IndicatorProposal.id == proposal_id)
    )).scalar_one_or_none()

    if not proposal:
        raise ValueError("建议不存在")

    proposal.status = ProposalStatus.REJECTED
    proposal.reviewed_by = reviewer_id
    await db.flush()

    return {
        "id": str(proposal.id),
        "title": proposal.title,
        "status": "rejected",
    }


def _summarize_finding(research: dict, index: int) -> Optional[str]:
    """Get summary text for a specific finding."""
    findings = research.get("findings", [])
    if index < len(findings):
        f = findings[index]
        return f"{f.get('title', '')}: {f.get('summary', '')}"
    return None
