# Post-Submit Diagnostic Processing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep examinees on the take-exam page after formal submission, show scoring/diagnostic progress, and render the diagnostic report once it is ready without forcing a first-load timeout-prone diagnostic request from the scores page.

**Architecture:** The backend adds a lightweight in-process answer-sheet processing coordinator with kickoff and status endpoints. The frontend changes the formal submit flow in `TakeExam.vue` to a staged processing view that starts processing, polls status, and loads the cached diagnostic report when processing finishes. Diagnostic LLM generation is bounded by an explicit timeout and falls back to deterministic sections on timeout.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, Vue 3 Composition API, Ant Design Vue, Axios, pytest

---

## Chunk 1: Backend Processing Coordinator

### Task 1: Add processing state helpers and status payload in scores endpoint

**Files:**
- Modify: `app/api/v1/endpoints/scores.py`
- Modify: `app/services/score_service.py`
- Test: `tests/test_scoring.py`

- [ ] Step 1: Write a failing backend test for process status transitions
- [ ] Step 2: Run `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_scoring.py -q`
- [ ] Step 3: Add a lightweight per-answer-sheet processing state store and helpers in `scores.py`
- [ ] Step 4: Add `POST /scores/process/{answer_sheet_id}` to start work or return completed state
- [ ] Step 5: Add `GET /scores/process/{answer_sheet_id}` to report `submitted | scoring | generating_diagnostic | completed | failed`
- [ ] Step 6: Add score lookup by sheet reuse where needed instead of duplicating queries
- [ ] Step 7: Run the scoring test file again

### Task 2: Run processing in a background async task with isolated DB session

**Files:**
- Modify: `app/api/v1/endpoints/scores.py`
- Modify: `app/core/database.py` or import existing session factory if needed
- Test: `tests/test_scoring.py`

- [ ] Step 1: Write or extend a failing test that starts processing twice and expects idempotent behavior
- [ ] Step 2: Implement background task creation with a fresh async DB session
- [ ] Step 3: Update stage before scoring, before diagnostic generation, and on completion/failure
- [ ] Step 4: Persist generated score and diagnostic report through existing services
- [ ] Step 5: Run the targeted scoring tests again

## Chunk 2: Diagnostic Timeout Fallback

### Task 3: Bound structured diagnostic generation time

**Files:**
- Modify: `app/services/diagnostic_service.py`
- Test: `tests/test_diagnostic.py`

- [ ] Step 1: Write a failing test that simulates a slow diagnostic LLM and expects a successful fallback report
- [ ] Step 2: Run `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py -q`
- [ ] Step 3: Wrap `generate_structured_diagnostic_sections(...)` in `asyncio.to_thread(...)` plus `asyncio.wait_for(...)`
- [ ] Step 4: Keep existing fallback sections for timeout and other exceptions
- [ ] Step 5: Run the diagnostic test file again

## Chunk 3: Take Exam Processing View

### Task 4: Add post-submit processing and report display states in TakeExam

**Files:**
- Modify: `frontend/src/views/TakeExam.vue`
- Possibly modify: `frontend/src/utils/request.ts` only if a per-request timeout override is needed

- [ ] Step 1: Add local UI state for `taking | processing | diagnostic_ready | processing_failed`
- [ ] Step 2: Render a formal-exam processing view with phase indicators and retry/exit actions
- [ ] Step 3: Change formal `submitExam()` flow to submit, start processing, and poll status
- [ ] Step 4: Load `GET /scores/{score_id}/diagnostic` only after process status is `completed`
- [ ] Step 5: Stop polling on unmount and route changes
- [ ] Step 6: Keep random-test behavior unchanged

### Task 5: Reuse diagnostic presentation without breaking Scores view

**Files:**
- Modify: `frontend/src/views/TakeExam.vue`
- Optionally modify: `frontend/src/views/Scores.vue`

- [ ] Step 1: Decide the smallest viable reuse boundary for diagnostic rendering
- [ ] Step 2: Prefer reusing the existing report markup if extraction is low-risk; otherwise render a focused in-page diagnostic result view for `TakeExam`
- [ ] Step 3: Verify report rendering works with the same response shape used by `Scores.vue`
- [ ] Step 4: Run frontend build

## Chunk 4: Verification

### Task 6: Full regression verification

**Files:**
- Test: `tests/test_scoring.py`
- Test: `tests/test_diagnostic.py`
- Verify: `frontend/src/views/TakeExam.vue`
- Verify: `frontend/src/views/Scores.vue`

- [ ] Step 1: Run `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_scoring.py tests/test_diagnostic.py -q`
- [ ] Step 2: Run `cd frontend && npm run build`
- [ ] Step 3: Review diffs to ensure random test flow and scores page behavior were not regressed
- [ ] Step 4: Prepare a concise summary of backend, frontend, and verification results
