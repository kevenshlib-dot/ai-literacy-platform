# Cross-Type Allocation Guardrails Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce duplicate-question failures by preventing multiple question types from over-concentrating on the same knowledge unit during material-based generation.

**Architecture:** Keep the current material selection flow intact, but replace the per-type independent allocation behavior with a constrained global allocator. The allocator will still prefer high-value knowledge units, but it will enforce a per-unit total question cap, apply cumulative penalty after each assignment, and restrict how many different question types a single unit can absorb.

**Tech Stack:** FastAPI backend, SQLAlchemy async services, pytest

---

## Status Snapshot

- [x] 已将纯分配回归测试拆到 `tests/test_question_distribution.py`
- [x] 已把 `_plan_unit_type_distribution()` 改成“总配额 + 轮转题型”的全局分配
- [x] 已补上“保持请求题量不变”的回归断言
- [ ] 真实素材 `f0c70f37-6e55-45f1-9286-38289bf3384c` 的新版对比预览仍待复跑
  - 当前阻塞：执行环境连接 PostgreSQL 超时，尚未拿到新的真实 `validation_reasons`

### Task 1: Lock the expected allocation behavior with regression tests

**Files:**
- Modify: `tests/test_question_distribution.py`
- Verify: `tests/test_question_distribution.py`

- [ ] Add a unit-level regression test for `_plan_unit_type_distribution()` showing that mixed type distributions no longer stack 4-5 questions onto one high-score knowledge unit.
- [ ] Add a regression test showing that when three strong knowledge units are available, the allocator spreads question types across them instead of reusing the same unit for every type.
- [ ] Run the targeted pytest selection/allocation tests and confirm the new tests fail before implementation.

### Task 2: Implement constrained global allocation

**Files:**
- Modify: `app/services/question_service.py`
- Verify: `tests/test_question_distribution.py`

- [ ] Introduce small helper(s) to compute per-unit cap and allocation priority without changing selection behavior.
- [ ] Refactor `_plan_unit_type_distribution()` so it allocates across all requested questions globally instead of independently per type.
- [ ] Enforce a per-unit total cap so a single knowledge unit cannot absorb most of the requested set.
- [ ] Add cumulative reuse penalty after each allocation so previously assigned units become less attractive for the next question slot.
- [ ] Enforce a question-type spread limit so the same unit cannot collect too many distinct types in one preview/build pass.
- [ ] Keep the output structure unchanged for callers.

### Task 3: Verify preview-level effects

**Files:**
- Modify: `tests/test_question_distribution.py`
- Verify: `tests/test_question_distribution.py`

- [ ] Add or update a preview-focused regression test so repeated knowledge-signature collisions are reduced in a small mixed-type material generation scenario.
- [ ] Run targeted pytest commands for allocation + preview generation.

### Task 4: Re-run the real material diagnostic

**Files:**
- Verify only

- [ ] Re-run the real `coverage` preview diagnostic for material `f0c70f37-6e55-45f1-9286-38289bf3384c` with the small mixed-type sample (`2` single choice, `1` multiple choice, `1` true/false, `1` short answer).
- [ ] Compare the before/after failure reasons, especially repeated knowledge-signature issues and per-unit concentration.
