# Unique Material Knowledge Points Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce one-question-per-knowledge-unit in material-based question-bank generation and fix false-positive material-reference matching.

**Architecture:** Keep the current selection and validation pipeline, but add an upfront unique-capacity gate and make unit-type planning strictly one question per selected unit. Reuse the same capacity logic across preview, final build, and prompt preview so all entry points behave consistently.

**Tech Stack:** FastAPI backend, SQLAlchemy async services, pytest

---

### Task 1: Lock the new unique-capacity behavior with tests

**Files:**
- Modify: `tests/test_question_distribution.py`
- Create or Modify: `tests/test_question_validation_rules.py`

- [ ] Add a regression test showing mixed-type material allocation assigns at most one question to each knowledge unit.
- [ ] Add a regression test showing the requested per-type counts are preserved when enough unique units exist.
- [ ] Add rule tests showing `节点` / `环节` / `调节` no longer trigger material-reference detection.
- [ ] Add rule tests showing `第3章` / `作者：` / `出版社：` still trigger material-reference detection.

### Task 2: Implement unique-capacity gating for material generation

**Files:**
- Modify: `app/services/question_service.py`

- [ ] Add a helper to compute `requested_total` and the effective selection limit for unique material generation.
- [ ] Add a helper that raises before generation when selected unique units are fewer than requested questions.
- [ ] Update material preview generation to use the effective expanded selection limit and fail fast on insufficient unique units.
- [ ] Update final material build to use the same unique-capacity logic.
- [ ] Cap suggested total question count by the available unique selected units.

### Task 3: Make unit-type planning strictly one question per unit

**Files:**
- Modify: `app/services/question_service.py`
- Verify: `tests/test_question_distribution.py`

- [ ] Refactor `_plan_unit_type_distribution()` so each knowledge unit can appear at most once in the final plan.
- [ ] Preserve weighted preference by assigning earlier slots to higher-value units.
- [ ] Preserve requested per-type counts when enough unique units exist.

### Task 4: Align prompt preview with the new gating

**Files:**
- Modify: `app/services/question_prompt_service.py`

- [ ] Update material prompt preview to reselect per-material units using the actual allocated count for that material.
- [ ] Fail prompt preview early when a material cannot provide enough unique units for its allocated questions.

### Task 5: Narrow forbidden material-reference matching

**Files:**
- Modify: `app/agents/question_agent.py`
- Verify: `tests/test_question_validation_rules.py`

- [ ] Remove single-character forbidden tokens `章` and `节`.
- [ ] Keep phrase-based and regex-based chapter / author / publisher detection intact.
- [ ] Re-run rule tests to verify false positives are eliminated without weakening real chapter-reference detection.

### Task 6: Verify targeted flows

**Files:**
- Verify only

- [ ] Run `python -m py_compile` on the touched backend files and tests.
- [ ] Run the targeted unit tests for allocation and validation rules.
- [ ] Re-run the real material preview for `f0c70f37-6e55-45f1-9286-38289bf3384c` and compare failure reasons with the previous run.
