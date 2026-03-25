# Material Approved Question Count Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在素材管理列表中展示每个素材关联的已审核通过题目数量。

**Architecture:** 后端在 `/materials` 列表查询中增加已审核题目聚合并回填到 `MaterialResponse`；前端在 `Materials.vue` 添加一列直接展示该值。测试覆盖只统计 `approved` 状态的口径。

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, TypeScript, ant-design-vue 4, pytest, Vite

---

## Chunk 1: Backend Aggregation

### Task 1: Add `approved_question_count` to material list responses

**Files:**
- Modify: `app/services/material_service.py`
- Modify: `app/schemas/material.py`
- Test: `tests/test_materials.py`

- [ ] Add `approved_question_count` to `MaterialResponse` with a default of `0`.
- [ ] Build an approved-question aggregate subquery keyed by `Question.source_material_id`.
- [ ] Join that aggregate into the materials list query.
- [ ] Attach the count value to each returned material record.

## Chunk 2: Frontend Table Display

### Task 2: Add a materials table column for approved question count

**Files:**
- Modify: `frontend/src/views/Materials.vue`

- [ ] Extend the local `Material` type with `approved_question_count`.
- [ ] Add the “题目数量（已审核）” column after status and before category.
- [ ] Render the returned count directly.

## Chunk 3: Regression Coverage And Verification

### Task 3: Verify approved-only counting behavior

**Files:**
- Modify: `tests/test_materials.py`
- Test: `tests/test_materials.py`
- Test: `frontend/package.json`

- [ ] Add a materials list test that creates approved and non-approved questions for the same material.
- [ ] Verify only the approved question is counted.
- [ ] Run the focused pytest case.
- [ ] Run `cd frontend && npm run build`.
