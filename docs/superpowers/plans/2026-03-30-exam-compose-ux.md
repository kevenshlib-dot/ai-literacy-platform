# Exam Compose UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the exam composition experience so candidate pagination stays stable after add/replace actions, candidates can be multi-selected for batch add, and whole question-type groups can be reordered.

**Architecture:** Keep the existing `ExamCompose.vue` page structure and backend API contract intact. Introduce local UI state for candidate multi-select and group ordering, then derive the persisted `order_num` from `groupOrder + group items` so the backend still receives a flat ordered list.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, existing FastAPI composition API

---

## Chunk 1: Candidate Selection State

### Task 1: Add state and rendering for candidate multi-select

**Files:**
- Modify: `frontend/src/views/ExamCompose.vue`

- [ ] **Step 1: Add local state for selected candidates and group order**

Introduce `selectedCandidateIds` and `groupOrder`, plus small helper functions for checking, toggling, and clearing selected candidates.

- [ ] **Step 2: Update the candidate panel UI**

Add:
- a batch action bar above the candidate list
- a checkbox per candidate card
- selection count feedback

Keep single-item replace/add controls intact.

- [ ] **Step 3: Implement batch add handler**

Add a handler that:
- validates non-empty selection
- skips already-added questions
- appends valid candidates into the proper group
- clears processed selections

## Chunk 2: Pagination-Stable Candidate Refresh

### Task 2: Split user-triggered refresh from mutation-triggered refresh

**Files:**
- Modify: `frontend/src/views/ExamCompose.vue`

- [ ] **Step 1: Keep `refreshCandidates()` as the reset-to-page-1 path**

Use it only when the user changes filters or explicitly clicks search/reset.

- [ ] **Step 2: Make add/replace/remove operations preserve current page**

After add, batch add, replace, or remove:
- call the current-page fetch path
- do not overwrite filter state
- if current page becomes empty and `current > 1`, decrement page and fetch again

- [ ] **Step 3: Preserve candidate active state sensibly**

When the current active candidate disappears, fall back to the first available candidate on the current page.

## Chunk 3: Type Group Reordering

### Task 3: Add whole-group move controls and derive final payload from group order

**Files:**
- Modify: `frontend/src/views/ExamCompose.vue`

- [ ] **Step 1: Drive grouped rendering from `groupOrder`**

Refactor grouping helpers so display order comes from `groupOrder` instead of the hard-coded constant alone.

- [ ] **Step 2: Add group move actions**

Add `moveGroupUp(questionType)` and `moveGroupDown(questionType)` and render enabled/disabled controls in each group header.

- [ ] **Step 3: Keep item drag-and-drop scoped to its current group**

Ensure the existing group-internal drag sorting still works after introducing `groupOrder`.

- [ ] **Step 4: Rebuild `compositionPayload()` from group order**

Flatten groups in `groupOrder`, then assign `order_num` sequentially for save.

## Chunk 4: Verification

### Task 4: Run targeted verification

**Files:**
- Modify: `frontend/src/views/ExamCompose.vue`

- [ ] **Step 1: Type-check the modified page through a frontend build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript or template errors.

- [ ] **Step 2: Review the diff for scope**

Run: `git diff -- frontend/src/views/ExamCompose.vue docs/superpowers/specs/2026-03-30-exam-compose-ux-design.md docs/superpowers/plans/2026-03-30-exam-compose-ux.md`
Expected: only the intended UX and planning changes are present.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ExamCompose.vue docs/superpowers/specs/2026-03-30-exam-compose-ux-design.md docs/superpowers/plans/2026-03-30-exam-compose-ux.md
git commit -m "feat: improve exam composition workflow"
```
