"""Tests for five-dimensional diagnostic report (T022)."""
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.models.user import User
from app.models.score import Score


async def override_get_db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="organizer"):
    import uuid
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/register", json={
        "username": f"user_{unique}",
        "email": f"{unique}@test.com",
        "password": "password123",
        "role": role,
    })
    data = resp.json()
    if data.get("access_token"):
        return data["access_token"]

    user_id = data["user"]["id"]
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        user.is_active = True
        await session.commit()
    await engine.dispose()

    login_resp = await client.post("/api/v1/auth/login", json={
        "username": f"user_{unique}",
        "password": "password123",
    })
    return login_resp.json()["access_token"]


def _question_payload(spec: dict, index: int) -> dict:
    qtype = spec.get("question_type", "single_choice")
    payload = {
        "question_type": qtype,
        "stem": spec.get("stem", f"诊断题{index + 1}？"),
        "correct_answer": spec["correct_answer"],
        "difficulty": spec.get("difficulty", 3),
        "dimension": spec.get("dimension"),
    }
    if spec.get("explanation") is not None:
        payload["explanation"] = spec["explanation"]
    if spec.get("rubric") is not None:
        payload["rubric"] = spec["rubric"]
    if spec.get("knowledge_tags") is not None:
        payload["knowledge_tags"] = spec["knowledge_tags"]
    if qtype in {"single_choice", "multiple_choice", "true_false"}:
        payload["options"] = spec.get("options") or {"A": "选A", "B": "选B", "C": "选C", "D": "选D"}
    return payload


async def create_scored_exam_with_questions(client, org_token, ex_token, question_specs):
    """Create exam, take it, grade it. Returns score_id."""
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, spec in enumerate(question_specs):
        resp = await client.post(
            "/api/v1/questions",
            json=_question_payload(spec, i),
            headers=org_headers,
        )
        assert resp.status_code == 201
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
        qids.append(qid)

    exam_resp = await client.post("/api/v1/exams", json={"title": "诊断测试"}, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(
        f"/api/v1/exams/{eid}/assemble/manual",
        json={
            "questions": [
                {"question_id": qids[i], "order_num": i + 1, "score": spec.get("score", 10)}
                for i, spec in enumerate(question_specs)
            ]
        },
        headers=org_headers,
    )
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    for i, spec in enumerate(question_specs):
        answer = spec.get("student_answer")
        if answer is not None:
            await client.post(
                f"/api/v1/sessions/{sid}/answer",
                json={"question_id": qids[i], "answer_content": answer},
                headers=ex_headers,
            )

    await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)
    score_resp = await client.get(
        f"/api/v1/scores/sheet/{sid}",
        headers={"Authorization": f"Bearer {ex_token}"},
    )
    assert score_resp.status_code == 200
    return score_resp.json()["score_id"]


async def create_scored_exam(client, org_token, ex_token, answers):
    specs = []
    for i, (correct, answer) in enumerate(answers):
        specs.append({
            "question_type": "single_choice",
            "stem": f"诊断题{i + 1}？",
            "correct_answer": correct,
            "student_answer": answer,
            "dimension": "AI基础知识" if i % 2 == 0 else "AI伦理安全",
        })
    return await create_scored_exam_with_questions(client, org_token, ex_token, specs)


@pytest.mark.asyncio
async def test_diagnostic_report_basic():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),  # correct
            ("B", "C"),  # wrong
            ("A", "A"),  # correct
            ("B", "B"),  # correct
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "radar_data" in data
    assert len(data["radar_data"]) == 5  # Five dimensions
    assert "dimension_analysis" in data
    assert "strengths" in data
    assert "weaknesses" in data
    assert "recommendations" in data
    assert "comparison" in data
    assert "wrong_answer_summary" in data
    assert "personalized_summary" in data
    assert "improvement_priorities" in data
    assert "actionable_suggestions" in data
    assert "recommended_resources" in data


@pytest.mark.asyncio
async def test_diagnostic_legacy_cache_returns_without_llm_regeneration(monkeypatch):
    from app.services import diagnostic_service

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("legacy cached diagnostic should not call LLM")

    monkeypatch.setattr(
        diagnostic_service,
        "generate_structured_diagnostic_sections",
        _fail_if_called,
    )

    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [("A", "A")])

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            score = (
                await session.execute(select(Score).where(Score.id == uuid.UUID(score_id)))
            ).scalar_one()
            score.report = {
                "diagnostic_report": {
                    "score_id": score_id,
                    "total_score": 10.0,
                    "max_score": 10.0,
                    "ratio": 1.0,
                    "level": "优秀",
                    "percentile_rank": 0,
                    "radar_data": [],
                    "dimension_analysis": {},
                    "strengths": [],
                    "weaknesses": [],
                    "comparison": {"items": []},
                    "recommendations": [],
                }
            }
            await session.commit()
        await engine.dispose()

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["report_version"] == diagnostic_service.DIAGNOSTIC_REPORT_VERSION
    assert data["uncategorized_metrics"]["evaluated"] is False
    assert data["total_score"] == 10.0


@pytest.mark.asyncio
async def test_diagnostic_radar_data_format():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    for item in data["radar_data"]:
        assert "dimension" in item
        assert "score" in item
        assert "max" in item
        assert "level" in item
        assert "evaluated" in item
        if item["score"] is not None:
            assert 0 <= item["score"] <= 100


@pytest.mark.asyncio
async def test_diagnostic_comparison_data():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    comp = data["comparison"]
    assert "items" in comp
    assert "above_average_count" in comp
    assert "below_average_count" in comp
    for item in comp["items"]:
        assert "dimension" in item
        assert "user_score" in item
        assert "avg_score" in item
        assert "diff" in item


@pytest.mark.asyncio
async def test_diagnostic_recommendations():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "B"),  # all wrong
            ("B", "C"),
        ])

        resp = await client.get(f"/api/v1/scores/{score_id}/diagnostic",
                               headers={"Authorization": f"Bearer {ex_token}"})
    data = resp.json()
    recs = data["recommendations"]
    assert len(recs) > 0
    assert isinstance(recs[0], str)


@pytest.mark.asyncio
async def test_diagnostic_wrong_answer_summary_contains_reason_details():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "B"),
            ("B", "C"),
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    wrong_summary = data["wrong_answer_summary"]
    assert "overview" in wrong_summary
    assert len(wrong_summary["items"]) > 0
    item = wrong_summary["items"][0]
    assert "question_id" in item
    assert "reason_summary" in item
    assert "improvement_tip" in item


@pytest.mark.asyncio
async def test_diagnostic_partial_credit_subjective_question_is_listed_as_lost_score():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam_with_questions(client, org_token, ex_token, [
            {
                "question_type": "short_answer",
                "stem": "请说明 AI 伦理评估应重点关注哪些方面？",
                "correct_answer": "公平性，透明度，隐私保护",
                "student_answer": "需要关注公平性和隐私保护。",
                "dimension": "AI批判思维",
                "rubric": {
                    "满分": "完整说明三个要点并联系实际风险",
                    "部分得分": "说明其中两个要点",
                    "低分": "仅说明一个或没有关键要点",
                },
            }
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    items = resp.json()["wrong_answer_summary"]["items"]
    assert len(items) == 1
    assert items[0]["question_type"] == "short_answer"
    assert items[0]["earned_score"] < items[0]["max_score"]


@pytest.mark.asyncio
async def test_full_review_uses_deduction_counts_for_partial_credit_subjective_question(monkeypatch):
    from app.services import score_service

    def _partial_subjective_score(**kwargs):
        return {
            "earned_score": 3.6,
            "is_correct": True,
            "feedback": "回答命中主要要点，但仍有遗漏，缺少透明度说明。",
            "analysis": {
                "earned_ratio": 0.6,
                "judgement": "回答达到基本要求，但未拿满分。",
                "positive_points": ["说明了公平性和隐私保护。"],
                "missed_points": ["缺少透明度说明。"],
                "error_reasons": ["incomplete_answer"],
                "confidence": 0.9,
                "evidence": ["学生答案提到了公平性和隐私保护。"],
                "scoring_source": "llm",
            },
        }

    monkeypatch.setattr(score_service, "score_subjective_answer", _partial_subjective_score)

    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam_with_questions(client, org_token, ex_token, [
            {
                "question_type": "short_answer",
                "stem": "请说明 AI 伦理评估应重点关注哪些方面？",
                "correct_answer": "公平性，透明度，隐私保护",
                "student_answer": "需要关注公平性和隐私保护。",
                "dimension": "AI伦理安全",
                "explanation": "本题考查 AI 伦理评估的核心关注点，包括公平性、透明度与隐私保护。",
                "score": 6,
            },
            {
                "question_type": "single_choice",
                "stem": "基础知识题？",
                "correct_answer": "A",
                "student_answer": "A",
                "dimension": "AI基础知识",
                "explanation": "A 是正确选项。",
                "score": 4,
            },
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/full-review",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["correct_count"] == 2
    assert data["full_score_count"] == 1
    assert data["deducted_count"] == 1
    partial_item = next(item for item in data["items"] if item["question_type"] == "short_answer")
    assert partial_item["is_correct"] is True
    assert partial_item["has_deduction"] is True
    assert partial_item["score_status"] == "partial_score"
    assert "缺少透明度说明" in partial_item["feedback"]
    assert partial_item["explanation"] == "本题考查 AI 伦理评估的核心关注点，包括公平性、透明度与隐私保护。"
    assert "question_analysis_text" not in partial_item
    assert "analysis_text" not in partial_item
    correct_item = next(item for item in data["items"] if item["question_type"] == "single_choice")
    assert correct_item["explanation"] == "A 是正确选项。"
    assert "question_analysis_text" not in correct_item
    assert "analysis_text" not in correct_item


@pytest.mark.asyncio
async def test_diagnostic_uncovered_dimensions_are_marked_not_evaluated():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam_with_questions(client, org_token, ex_token, [
            {
                "question_type": "single_choice",
                "stem": "基础知识题？",
                "correct_answer": "A",
                "student_answer": "A",
                "dimension": "AI基础知识",
            },
            {
                "question_type": "single_choice",
                "stem": "伦理安全题？",
                "correct_answer": "B",
                "student_answer": "C",
                "dimension": "AI伦理安全",
            },
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    innovation = data["dimension_analysis"]["AI创新实践"]
    assert innovation["question_count"] == 0
    assert innovation["evaluated"] is False
    assert innovation["summary"] == "本次测评在该维度没有题目覆盖，暂不评估。"
    assert innovation["detail"] == "本次测评在该维度没有题目覆盖，暂不评估。"
    assert all(item["dimension"] != "AI创新实践" for item in data["improvement_priorities"])
    assert all(item["dimension"] != "AI创新实践" for item in data["weaknesses"])


@pytest.mark.asyncio
async def test_diagnostic_uncategorized_questions_do_not_affect_five_dimension_scores():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam_with_questions(client, org_token, ex_token, [
            {
                "question_type": "single_choice",
                "stem": "基础知识题？",
                "correct_answer": "A",
                "student_answer": "A",
                "dimension": "AI基础知识",
                "score": 10,
            },
            {
                "question_type": "single_choice",
                "stem": "未分类题？",
                "correct_answer": "B",
                "student_answer": "C",
                "dimension": None,
                "score": 10,
            },
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dimension_analysis"]["AI基础知识"]["score"] == 100.0
    assert data["dimension_analysis"]["AI基础知识"]["question_count"] == 1
    assert data["dimension_analysis"]["AI伦理安全"]["evaluated"] is False
    uncategorized = data["uncategorized_metrics"]
    assert uncategorized["evaluated"] is True
    assert uncategorized["question_count"] == 1
    assert uncategorized["wrong_count"] == 1
    assert uncategorized["score"] == 0.0


@pytest.mark.asyncio
async def test_diagnostic_llm_timeout_falls_back_successfully(monkeypatch):
    from app.services import diagnostic_service

    def _slow_llm(*args, **kwargs):
        time.sleep(0.05)
        return {
            "wrong_answer_summary": {"overview": "slow", "items": [], "patterns": []},
            "dimension_analysis": {},
            "personalized_summary": {"summary": "slow", "highlights": [], "cautions": []},
            "improvement_priorities": [],
            "actionable_suggestions": [],
            "recommended_resources": [],
        }

    monkeypatch.setattr(diagnostic_service, "generate_structured_diagnostic_sections", _slow_llm)
    monkeypatch.setattr(diagnostic_service, "DIAGNOSTIC_LLM_TIMEOUT_SECONDS", 0.01)

    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        score_id = await create_scored_exam(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "C"),
        ])

        resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "radar_data" in data
    assert "dimension_analysis" in data
    assert data["wrong_answer_summary"]["overview"]


@pytest.mark.asyncio
async def test_diagnostic_percentile():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex1_token = await register_user(client, "examinee")
        ex2_token = await register_user(client, "examinee")

        # Create shared exam setup - both take the same exam
        rev_token = await register_user(client, "reviewer")
        org_headers = {"Authorization": f"Bearer {org_token}"}

        # Create question
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": "百分位测试？",
            "correct_answer": "A",
            "options": {"A": "正确", "B": "错", "C": "错", "D": "错"},
            "difficulty": 3,
            "dimension": "AI基础",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})

        exam_resp = await client.post("/api/v1/exams", json={"title": "排名测试"}, headers=org_headers)
        eid = exam_resp.json()["id"]
        await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
            "questions": [{"question_id": qid, "order_num": 1, "score": 10}]
        }, headers=org_headers)
        await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

        # Examinee 1: correct
        s1 = await client.post(f"/api/v1/sessions/start/{eid}",
                              headers={"Authorization": f"Bearer {ex1_token}"})
        sid1 = s1.json()["answer_sheet_id"]
        await client.post(f"/api/v1/sessions/{sid1}/answer", json={
            "question_id": qid, "answer_content": "A",
        }, headers={"Authorization": f"Bearer {ex1_token}"})
        await client.post(f"/api/v1/sessions/{sid1}/submit",
                         headers={"Authorization": f"Bearer {ex1_token}"})

        # Examinee 2: wrong
        s2 = await client.post(f"/api/v1/sessions/start/{eid}",
                              headers={"Authorization": f"Bearer {ex2_token}"})
        sid2 = s2.json()["answer_sheet_id"]
        await client.post(f"/api/v1/sessions/{sid2}/answer", json={
            "question_id": qid, "answer_content": "B",
        }, headers={"Authorization": f"Bearer {ex2_token}"})
        await client.post(f"/api/v1/sessions/{sid2}/submit",
                         headers={"Authorization": f"Bearer {ex2_token}"})

        score_1 = await client.get(
            f"/api/v1/scores/sheet/{sid1}",
            headers={"Authorization": f"Bearer {ex1_token}"},
        )
        score_2 = await client.get(
            f"/api/v1/scores/sheet/{sid2}",
            headers={"Authorization": f"Bearer {ex2_token}"},
        )
        score_id_1 = score_1.json()["score_id"]
        score_id_2 = score_2.json()["score_id"]

        # Check diagnostics - ex1 should rank higher
        d1 = await client.get(f"/api/v1/scores/{score_id_1}/diagnostic",
                             headers={"Authorization": f"Bearer {ex1_token}"})
        d2 = await client.get(f"/api/v1/scores/{score_id_2}/diagnostic",
                             headers={"Authorization": f"Bearer {ex2_token}"})
    assert d1.status_code == 200
    assert d2.status_code == 200
    assert d1.json()["percentile_rank"] >= d2.json()["percentile_rank"]
