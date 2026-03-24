# 题库预览链路降调用次数 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让素材题库预览首屏不再同步等待每题 AI review，并为后续整批 planner / 批量 generator 重构建立批次接口。

**Architecture:** 预览接口同步返回题目、规则风险和校准结果，同时生成一个 `preview_batch_id`。后台异步执行该批次的 AI review，并通过新的批次查询接口回填到前端。批次结果先存进程内临时存储，控制范围后续再升级。

**Tech Stack:** FastAPI, Pydantic, Vue 3, 进程内 TTL 存储, pytest

---

## Chunk 1: 预览批次与异步 AI Review 后端

### Task 1: 定义预览批次 schema

**Files:**
- Modify: `app/schemas/question.py`
- Test: `tests/test_questions.py`

- [x] 增加 `preview_batch_id`、`ai_review_pending`、`ai_review_completed` 等响应字段
- [x] 增加查询批次 AI review 结果的 response schema

### Task 2: 实现批次临时存储

**Files:**
- Create: `app/services/preview_review_store.py`
- Test: `tests/test_questions.py`

- [x] 实现基于进程内字典 + TTL 的批次存储
- [x] 支持写入初始预览结果、回填 AI review、读取批次汇总

### Task 3: 改造素材预览接口

**Files:**
- Modify: `app/services/question_service.py`
- Modify: `app/api/v1/endpoints/questions.py`
- Test: `tests/test_questions.py`

- [x] 将 `_review_preview_questions()` 从同步首屏链路移出
- [x] 预览生成后写入批次存储并返回 `preview_batch_id`
- [x] 增加后台异步启动 AI review 的入口
- [x] 增加 `GET /questions/preview/batch/{preview_batch_id}` 查询接口

### Task 4: 补后端测试

**Files:**
- Modify: `tests/test_questions.py`

- [x] 预览首屏返回时 `quality_review_count == 0` 且 `ai_review_pending == true`
- [x] 后台回填后批次查询能返回每题 `quality_review`
- [x] 规则质检与后验校准仍保留

## Chunk 2: 前端预览轮询与状态展示

### Task 5: 扩展前端预览状态

**Files:**
- Modify: `frontend/src/views/Questions.vue`

- [x] 保存 `preview_batch_id`
- [x] 打开预览抽屉后轮询 AI review 结果
- [x] 展示“AI review 处理中 / 已完成”

### Task 6: 补首屏与回填展示

**Files:**
- Modify: `frontend/src/views/Questions.vue`

- [x] 首屏先展示规则风险和校准统计
- [x] AI review 回填后更新题表的 `quality_review` 列和统计区

### Task 7: 前端验证

**Files:**
- Modify: `frontend/src/views/Questions.vue`

- [x] 运行 `npm run build`
- [ ] 手工验证预览先返回、质检后补

## Chunk 3: 为后续整批 planner / generator 预留接口

### Task 8: 重构生成入口参数

**Files:**
- Modify: `app/agents/question_agent.py`
- Modify: `app/services/question_service.py`
- Test: `tests/test_question_generation_compare.py`

- [x] 给生成入口预留可注入 `question_plan` 的参数
- [x] 不改变当前行为，仅确保后续可以跳过每题 planner
- [x] 素材预览链路改为每轮 attempt 只执行一次整批 planner，并将规划按槽位注入后续单题 generator
- [x] 素材预览链路按题型批量调用 generator，复用同一轮整批 planner 结果

### Task 9: 回归测试

**Files:**
- Modify: `tests/test_question_generation_compare.py`
- Modify: `tests/test_questions.py`

- [x] 验证现有 local_qwen 结构化输出路径不回归
- [x] 验证素材预览保存链路不受影响

## Chunk 4: 受限并发执行

### Task 10: 为预览生成增加受限并发

**Files:**
- Modify: `app/services/question_service.py`
- Modify: `app/api/v1/endpoints/questions.py`
- Test: `tests/test_questions.py`

- [x] 将素材预览按题型批量 generator 改为受限并发执行
- [x] 将 free preview 按题型批量 generator 改为受限并发执行
- [x] 保持现有接口语义不变，仅将 `preview_questions_free` 改为异步实现以承接并发调用

### Task 11: 并发回归测试

**Files:**
- Modify: `tests/test_questions.py`

- [x] 验证 free preview 的按题型批量生成可以并发执行
- [x] 验证素材预览整批 planner / 异步 AI review 链路不回归
