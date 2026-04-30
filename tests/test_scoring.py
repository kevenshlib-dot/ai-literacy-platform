"""Tests for scoring engine and report generation (T015-T017)."""
import asyncio
from types import SimpleNamespace
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.agents import scoring_agent
from app.agents.scoring_agent import _rule_based_scoring
from app.models.user import User
from app.services.score_service import _score_objective, normalize_true_false_answer


# ---- Unit Tests for Scoring Agent ----

def test_rule_based_scoring_correct():
    result = _rule_based_scoring(
        stem="什么是AI？",
        correct_answer="人工智能，计算机科学，智能系统",
        student_answer="人工智能是计算机科学的一个分支，用于构建智能系统。",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] > 0
    assert "feedback" in result
    assert result["analysis"]["scoring_source"] == "rule"
    assert "earned_ratio" in result["analysis"]


def test_rule_based_scoring_empty():
    result = _rule_based_scoring(
        stem="什么是ML？",
        correct_answer="机器学习",
        student_answer="",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] == 0.0
    assert result["is_correct"] is False
    assert "未作答" in result["feedback"]
    assert result["analysis"]["error_reasons"] == ["no_answer"]


def test_rule_based_scoring_partial():
    result = _rule_based_scoring(
        stem="深度学习的特点？",
        correct_answer="多层神经网络，自动特征提取，大数据驱动",
        student_answer="深度学习使用多层神经网络来学习。",
        question_type="short_answer",
        max_score=10.0,
    )
    assert 0 < result["earned_score"] <= 10.0
    assert "missed_points" in result["analysis"]


def test_subjective_scoring_llm_output_is_normalized(monkeypatch):
    def _fake_llm(**kwargs):
        return {
            "earned_ratio": 0.72,
            "judgement": "覆盖了主要要点，但遗漏了风险分析。",
            "positive_points": ["说明了AI辅助诊断的主要作用"],
            "missed_points": ["缺少风险控制说明"],
            "error_reasons": ["incomplete_answer"],
            "feedback": "整体较好，但论述不完整。",
            "confidence": 0.81,
            "evidence": ["学生答案提到了效率提升"],
        }

    monkeypatch.setattr(scoring_agent, "_call_subjective_scoring_llm", _fake_llm)

    result = scoring_agent.score_subjective_answer(
        stem="请分析AI辅助诊断的价值与风险。",
        correct_answer="应说明效率提升、辅助医生决策，并分析误判风险和人工复核要求。",
        student_answer="AI可以提升诊断效率，帮助医生判断。",
        question_type="short_answer",
        max_score=10.0,
    )
    assert result["earned_score"] == 7.2
    assert result["analysis"]["scoring_source"] == "llm"
    assert result["analysis"]["missed_points"] == ["缺少风险控制说明"]


def test_true_false_scoring_normalizes_legacy_answer_formats():
    assert normalize_true_false_answer("A") == "T"
    assert normalize_true_false_answer("B") == "F"
    assert normalize_true_false_answer("正确") == "T"
    assert normalize_true_false_answer("错误") == "F"

    question = SimpleNamespace(id="q1", question_type="true_false", correct_answer="A")
    assert _score_objective(question, "T", 5.0, effective_type="true_false")["is_correct"] is True
    assert _score_objective(question, "F", 5.0, effective_type="true_false")["is_correct"] is False

    question.correct_answer = "F"
    assert _score_objective(question, "B", 5.0, effective_type="true_false")["is_correct"] is True
    assert _score_objective(question, "A", 5.0, effective_type="true_false")["is_correct"] is False


# ---- Integration Tests ----

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


async def setup_exam_and_submit(client, org_token, ex_token, answers_map):
    """Full flow: create exam -> examinee takes it -> submit.

    answers_map: list of (correct_answer_for_question, student_answer) tuples.
    Returns (sheet_id, org_token).
    """
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, (correct, _) in enumerate(answers_map):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"测评题目{i+1}？",
            "correct_answer": correct,
            "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
            "difficulty": 3,
            "dimension": f"维度{i % 2 + 1}",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(f"/api/v1/questions/{qid}/review",
                         json={"action": "approve"},
                         headers={"Authorization": f"Bearer {rev_token}"})
        qids.append(qid)

    # Create and publish exam
    exam_resp = await client.post("/api/v1/exams", json={
        "title": "评分测试考试",
    }, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(f"/api/v1/exams/{eid}/assemble/manual", json={
        "questions": [
            {"question_id": qids[i], "order_num": i + 1, "score": 10}
            for i in range(len(qids))
        ]
    }, headers=org_headers)

    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    # Examinee takes exam
    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    # Submit answers
    for i, (_, student_answer) in enumerate(answers_map):
        if student_answer is not None:
            await client.post(f"/api/v1/sessions/{sid}/answer", json={
                "question_id": qids[i],
                "answer_content": student_answer,
            }, headers=ex_headers)

    # Submit exam
    await client.post(f"/api/v1/sessions/{sid}/submit", headers=ex_headers)

    return sid


async def setup_exam_submit_only(client, org_token, ex_token, answers_map):
    rev_token = await register_user(client, "reviewer")
    org_headers = {"Authorization": f"Bearer {org_token}"}
    ex_headers = {"Authorization": f"Bearer {ex_token}"}

    qids = []
    for i, (correct, _) in enumerate(answers_map):
        resp = await client.post("/api/v1/questions", json={
            "question_type": "single_choice",
            "stem": f"流程题目{i+1}？",
            "correct_answer": correct,
            "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
            "difficulty": 3,
            "dimension": f"维度{i % 2 + 1}",
        }, headers=org_headers)
        qid = resp.json()["id"]
        await client.post(f"/api/v1/questions/{qid}/submit", headers=org_headers)
        await client.post(
            f"/api/v1/questions/{qid}/review",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {rev_token}"},
        )
        qids.append(qid)

    exam_resp = await client.post("/api/v1/exams", json={"title": "提交后处理考试"}, headers=org_headers)
    eid = exam_resp.json()["id"]

    await client.post(
        f"/api/v1/exams/{eid}/assemble/manual",
        json={
            "questions": [
                {"question_id": qids[i], "order_num": i + 1, "score": 10}
                for i in range(len(qids))
            ]
        },
        headers=org_headers,
    )
    await client.post(f"/api/v1/exams/{eid}/publish", headers=org_headers)

    start = await client.post(f"/api/v1/sessions/start/{eid}", headers=ex_headers)
    sid = start.json()["answer_sheet_id"]

    for i, (_, student_answer) in enumerate(answers_map):
        if student_answer is not None:
            await client.post(
                f"/api/v1/sessions/{sid}/answer",
                json={"question_id": qids[i], "answer_content": student_answer},
                headers=ex_headers,
            )

    submit_resp = await client.post(
        f"/api/v1/sessions/{sid}/submit",
        params={"auto_score": "false"},
        headers=ex_headers,
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "submitted"
    return sid


async def get_score_by_sheet_payload(client, sheet_id, token):
    resp = await client.get(
        f"/api/v1/scores/sheet/{sheet_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_grade_all_correct():
    """All correct answers should get full score."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
        ])
        data = await get_score_by_sheet_payload(client, sid, ex_token)
    assert data["total_score"] == 30.0
    assert data["max_score"] == 30.0
    assert data["level"] == "优秀"


@pytest.mark.asyncio
async def test_grade_all_wrong():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "B"),
            ("B", "C"),
            ("C", "A"),
        ])
        data = await get_score_by_sheet_payload(client, sid, ex_token)
    assert data["total_score"] == 0.0
    assert data["level"] == "不合格"


@pytest.mark.asyncio
async def test_grade_partial():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),  # correct
            ("B", "C"),  # wrong
            ("C", None), # unanswered
        ])
        data = await get_score_by_sheet_payload(client, sid, ex_token)
    assert data["total_score"] == 10.0  # only first correct
    assert data["max_score"] == 30.0


@pytest.mark.asyncio
async def test_get_score_by_sheet():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "B"),
        ])
        resp = await client.get(f"/api/v1/scores/sheet/{sid}",
                               headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_score"] == 20.0
    assert len(data["details"]) == 2
    for d in data["details"]:
        assert d["is_correct"] is True
        assert d["feedback"] == "正确"
        assert d["analysis"]["scoring_source"] == "rule"


@pytest.mark.asyncio
async def test_cannot_double_grade():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [("A", "A")])
        headers = {"Authorization": f"Bearer {org_token}"}

        resp = await client.post(f"/api/v1/scores/grade/{sid}", headers=headers)
    assert resp.status_code == 400
    assert "已评分" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_report():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "C"),
        ])
        score_payload = await get_score_by_sheet_payload(client, sid, ex_token)
        score_id = score_payload["score_id"]

        resp = await client.post(f"/api/v1/scores/{score_id}/report",
                                headers={"Authorization": f"Bearer {ex_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ratio" in data
    assert "dimension_analysis" in data
    assert "recommendations" in data
    assert data["total_questions"] == 2
    assert data["correct_count"] == 1


@pytest.mark.asyncio
async def test_generate_report_and_diagnostic_do_not_override_each_other():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "C"),
        ])
        score_payload = await get_score_by_sheet_payload(client, sid, ex_token)
        score_id = score_payload["score_id"]

        score_report_resp = await client.post(
            f"/api/v1/scores/{score_id}/report",
            headers={"Authorization": f"Bearer {ex_token}"},
        )
        diagnostic_resp = await client.get(
            f"/api/v1/scores/{score_id}/diagnostic",
            headers={"Authorization": f"Bearer {ex_token}"},
        )

    assert score_report_resp.status_code == 200
    assert diagnostic_resp.status_code == 200
    assert "total_questions" in score_report_resp.json()
    assert "radar_data" in diagnostic_resp.json()


@pytest.mark.asyncio
async def test_score_processing_endpoints_complete_and_reuse_cached_diagnostic():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")
        headers = {"Authorization": f"Bearer {ex_token}"}

        sid = await setup_exam_submit_only(client, org_token, ex_token, [
            ("A", "A"),
            ("B", "C"),
        ])

        start_resp = await client.post(f"/api/v1/scores/process/{sid}", headers=headers)
        assert start_resp.status_code == 200
        assert start_resp.json()["stage"] == "submitted"

        status_payload = None
        for _ in range(30):
            status_resp = await client.get(f"/api/v1/scores/process/{sid}", headers=headers)
            assert status_resp.status_code == 200
            status_payload = status_resp.json()
            if status_payload["stage"] == "completed":
                break
            await asyncio.sleep(0.05)

        assert status_payload is not None
        assert status_payload["stage"] == "completed"
        assert status_payload["score_id"]
        assert status_payload["diagnostic_ready"] is True

        repeat_resp = await client.post(f"/api/v1/scores/process/{sid}", headers=headers)
        assert repeat_resp.status_code == 200
        repeat_payload = repeat_resp.json()
        assert repeat_payload["stage"] == "completed"
        assert repeat_payload["score_id"] == status_payload["score_id"]


@pytest.mark.asyncio
async def test_dimension_scores():
    """Verify dimension-level scoring breakdown."""
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        ex_token = await register_user(client, "examinee")

        sid = await setup_exam_and_submit(client, org_token, ex_token, [
            ("A", "A"),  # 维度1 - correct
            ("B", "C"),  # 维度2 - wrong
        ])
        data = await get_score_by_sheet_payload(client, sid, ex_token)
    assert "dimension_scores" in data
    dim_scores = data["dimension_scores"]
    assert "维度1" in dim_scores
    assert "维度2" in dim_scores
    assert dim_scores["维度1"]["earned"] == 10.0
    assert dim_scores["维度2"]["earned"] == 0.0
