# Question Bank Overflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复题库管理列表的固定操作列与题目详情抽屉首次打开时的内容溢出问题。

**Architecture:** 仅修改 `frontend/src/views/Questions.vue`。列表通过显式横向滚动建立固定列上下文，详情抽屉通过预渲染、固定 descriptions 表格布局和统一长文本样式来稳定首次渲染结果。

**Tech Stack:** Vue 3, TypeScript, ant-design-vue 4, Vite

---

## Chunk 1: Questions View Overflow Fix

### Task 1: Stabilize question list tables

**Files:**
- Modify: `frontend/src/views/Questions.vue`
- Test: `frontend/package.json`

- [ ] Add horizontal `scroll.x` config to the main question table.
- [ ] Add horizontal `scroll.x` config to the review table so the right-side actions stay fixed during horizontal scrolling.
- [ ] Keep the existing stem/source truncation behavior unchanged.

### Task 2: Stabilize question detail drawer layout

**Files:**
- Modify: `frontend/src/views/Questions.vue`

- [ ] Enable `forceRender` on the question detail drawer.
- [ ] Add a scoped class for the detail descriptions block and override bordered descriptions table layout to `fixed`.
- [ ] Wrap long-text fields with reusable classes for safe wrapping and preserved line breaks where needed.

### Task 3: Verify frontend build

**Files:**
- Test: `frontend/package.json`

- [ ] Run `cd frontend && npm run build`.
- [ ] Confirm the build completes successfully.
