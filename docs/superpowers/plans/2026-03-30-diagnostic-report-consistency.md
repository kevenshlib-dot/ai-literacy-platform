# Diagnostic Report Consistency Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate contradictory diagnostic report output by aligning lost-score detection and by marking uncovered dimensions as not evaluable instead of assigning synthetic low scores.

**Architecture:** Keep the existing report payload shape stable where possible, but change backend derivation rules so all sections are generated from the same earned-vs-max evidence. Diagnostic dimension entries with zero covered questions will carry an explicit "not evaluated" state and will be excluded from weakness prioritization and recommendations.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, pytest

---

## Chunk 1: Lost-Score Detection

### Task 1: Add regression tests for partial-credit loss handling

**Files:**
- Modify: `tests/test_diagnostic.py`
- Test: `tests/test_diagnostic.py`

- [ ] **Step 1: Write the failing tests**

Add an integration test that creates a `short_answer` question with a rubric, submits a partially correct answer that earns non-full credit, and asserts the diagnostic `wrong_answer_summary.items` contains that question.

- [ ] **Step 2: Run the targeted diagnostic test to verify it fails**

Run: `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py -q`
Expected: FAIL because partially scored subjective questions are currently treated as correct and omitted from wrong-answer analysis.

- [ ] **Step 3: Implement minimal lost-score selection fix**

Update `app/services/score_service.py` so wrong-answer detail generation selects any `ScoreDetail` whose `earned_score < max_score`, not only `is_correct == False`.

- [ ] **Step 4: Run targeted tests to verify the fix**

Run: `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py -q`
Expected: PASS for the new partial-credit regression and existing diagnostic assertions.

## Chunk 2: Uncovered Dimension Handling

### Task 2: Add regression tests for uncovered dimensions

**Files:**
- Modify: `tests/test_diagnostic.py`
- Test: `tests/test_diagnostic.py`

- [ ] **Step 1: Write the failing tests**

Add an integration test that creates an exam covering only a subset of the five dimensions and asserts an uncovered dimension:
- reports `question_count == 0`
- is marked as not evaluated
- does not appear in `improvement_priorities`
- does not fabricate a low-score reason

- [ ] **Step 2: Run the targeted diagnostic test to verify it fails**

Run: `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py -q`
Expected: FAIL because uncovered dimensions currently inherit the overall ratio and can be ranked as weaknesses.

- [ ] **Step 3: Implement minimal uncovered-dimension fix**

Update `app/services/diagnostic_service.py` to:
- stop backfilling uncovered dimensions with the overall score
- emit explicit `evaluated` / `not_evaluated` state for dimension metrics and radar entries
- exclude uncovered dimensions from weakest-dimension selection, strengths/weaknesses, suggestions, and misleading summaries

- [ ] **Step 4: Run targeted tests to verify the fix**

Run: `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py -q`
Expected: PASS for the new uncovered-dimension regression and existing diagnostic assertions.

## Chunk 3: Report Rendering Compatibility

### Task 3: Keep report payload readable by the frontend

**Files:**
- Modify: `app/services/diagnostic_service.py`
- Modify: `frontend/src/views/Scores.vue`
- Test: `tests/test_diagnostic.py`

- [ ] **Step 1: Review payload consumers**

Confirm how `frontend/src/views/Scores.vue` renders dimension analysis and whether it needs a fallback label for uncovered dimensions.

- [ ] **Step 2: Implement compatibility adjustments**

If needed, update the frontend to show "本次无题目覆盖，暂不评估" for dimensions where `evaluated == false`, while preserving existing rendering for evaluated dimensions.

- [ ] **Step 3: Run verification**

Run: `conda run --no-capture-output -n ai-literacy python -m pytest tests/test_diagnostic.py tests/test_scoring.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/services/diagnostic_service.py app/services/score_service.py frontend/src/views/Scores.vue tests/test_diagnostic.py
git commit -m "fix: align diagnostic lost-score and uncovered-dimension analysis"
```
