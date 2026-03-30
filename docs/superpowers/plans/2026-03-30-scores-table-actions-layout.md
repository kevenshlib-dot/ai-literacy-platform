# Scores Table Actions Layout Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the actions column in the scores management tables from overflowing by widening the table layout appropriately and making the action button area wrap safely.

**Architecture:** Keep the existing table structure and actions unchanged. Adjust only the manager/personal score tables in `Scores.vue` by increasing action-column widths, enabling horizontal scroll, and applying a compact wrapping layout to the action button groups.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Vite

---

## Chunk 1: Table Layout Adjustments

### Task 1: Widen the affected tables and actions columns

**Files:**
- Modify: `frontend/src/views/Scores.vue`

- [ ] **Step 1: Identify the two affected table definitions**

Update only:
- the manager score list table
- the personal score list table

- [ ] **Step 2: Add horizontal scroll config**

Set `scroll.x` on both affected tables so total column width is handled inside the table instead of squeezing the actions cell.

- [ ] **Step 3: Increase actions column widths**

Tune `managerColumns` and `columns` so the actions column has enough baseline room for the current action set.

## Chunk 2: Action Cell Wrapping

### Task 2: Make the action area resilient in narrow widths

**Files:**
- Modify: `frontend/src/views/Scores.vue`

- [ ] **Step 1: Update the action cell containers**

Use a wrapping `a-space` or equivalent compact flex layout for manager and personal action cells.

- [ ] **Step 2: Add scoped styles if needed**

If default Ant Design spacing is not sufficient, add a small scoped helper class to control wrapping and gap without changing the visual hierarchy.

## Chunk 3: Verification

### Task 3: Verify build and diff scope

**Files:**
- Modify: `frontend/src/views/Scores.vue`

- [ ] **Step 1: Run frontend build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no Vue template or TypeScript errors.

- [ ] **Step 2: Review diff scope**

Run: `git diff -- frontend/src/views/Scores.vue docs/superpowers/specs/2026-03-30-scores-table-actions-layout-design.md docs/superpowers/plans/2026-03-30-scores-table-actions-layout.md`
Expected: only the intended table-layout and planning changes are present.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/Scores.vue docs/superpowers/specs/2026-03-30-scores-table-actions-layout-design.md docs/superpowers/plans/2026-03-30-scores-table-actions-layout.md
git commit -m "fix: prevent score table action overflow"
```
