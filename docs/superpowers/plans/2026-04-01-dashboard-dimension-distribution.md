# Dashboard Dimension Distribution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正工作台维度卡片与题目总数的统计口径，改为全量题库题目占比。

**Architecture:** 仅调整前端工作台页面的数据请求和显示文案，复用现有 `/questions/stats` 接口提供的总数和维度分布，不新增后端逻辑。

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, existing Axios request wrapper

---

### Task 1: 修正工作台统计数据来源

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`
- Verify: `frontend/src/views/Dashboard.vue`

- [ ] Step 1: 将维度卡片标题改为“AI素养维度题目占比”
- [ ] Step 2: 在 `loadDashboard()` 中新增 `/questions/stats` 请求
- [ ] Step 3: 用 `/questions/stats.total` 更新 `stats.questions`
- [ ] Step 4: 用 `/questions/stats.by_dimension` 计算五个维度的百分比
- [ ] Step 5: 删除 `/questions?limit=100` 的样本统计逻辑

### Task 2: 验证

**Files:**
- Verify: `frontend/src/views/Dashboard.vue`

- [ ] Step 1: 运行 `cd frontend && npm run build`
- [ ] Step 2: 检查工作区差异，确认只包含本次目标改动
