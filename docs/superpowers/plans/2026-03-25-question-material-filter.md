# Question Material Filter Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为题库管理“全部题目”列表增加按素材筛选能力，并让列表统计与筛选口径一致。

**Architecture:** 后端在问题列表与统计接口上统一支持 `source_material_id` 条件；前端在 `Questions.vue` 增加素材下拉，并独立加载全部素材作为筛选选项。现有审核页、详情抽屉和题库生成弹窗不做行为调整。

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, TypeScript, ant-design-vue 4, pytest, Vite

---

## Chunk 1: Backend Filter Support

### Task 1: Extend question list and stats APIs with `source_material_id`

**Files:**
- Modify: `app/api/v1/endpoints/questions.py`
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] Add `source_material_id` query param to `/questions`.
- [ ] Pass the new param through to `question_service.list_questions`.
- [ ] Add the same param to `/questions/stats`.
- [ ] Pass it through to `question_service.get_question_stats`.
- [ ] Update both service functions to append `Question.source_material_id == source_material_id` when provided.

## Chunk 2: Frontend Filter UI

### Task 2: Add material selector and request wiring

**Files:**
- Modify: `frontend/src/views/Questions.vue`

- [ ] Add `source_material_id` to the main question filter state.
- [ ] Add a material `<a-select>` to the “全部题目” filter bar.
- [ ] Add local state for loading and caching all material options.
- [ ] Implement a paginated loader that fetches all materials from `/materials`.
- [ ] Wire `source_material_id` into `fetchQuestions`, `fetchQuestionStats`, and post-batch refresh requests.
- [ ] Clear the field in `resetFilters`.

## Chunk 3: Regression Coverage And Verification

### Task 3: Add regression tests and run verification

**Files:**
- Modify: `tests/test_questions.py`
- Test: `tests/test_questions.py`
- Test: `frontend/package.json`

- [ ] Add a test proving `/questions` filters by `source_material_id`.
- [ ] Add a test proving `/questions/stats` respects the same filter.
- [ ] Run the focused pytest cases.
- [ ] Run `cd frontend && npm run build`.
