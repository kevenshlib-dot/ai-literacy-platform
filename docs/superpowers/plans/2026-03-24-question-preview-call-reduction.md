# 题库预览链路降调用次数 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将素材题库 preview 的重试模型从“整轮重跑”改成“planner 一次 + 只补失败槽位”，并让预览统计反映整次请求真实成本。

**Architecture:** 单次 preview 请求先执行一次 batch planner，再按题型批量并发 generator。若首轮存在掉题，仅失败槽位进入后续补题轮次；成功槽位直接复用。统计层同时维护整次请求的 overall 指标和最后一轮 attempt 的局部指标，默认对外返回 overall 结果。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, OpenAI-compatible LLM client, asyncio, pytest

---

## Chunk 1: 文档与统计语义修正

### Task 1: 更新设计与实现文档

**Files:**
- Modify: `docs/superpowers/specs/2026-03-24-question-preview-call-reduction-design.md`
- Modify: `docs/superpowers/plans/2026-03-24-question-preview-call-reduction.md`

- [x] 将旧的 preview batch / 异步 AI review 方案更新为当前性能优化方案
- [x] 明确新目标是 `planner 一次 + 失败槽位补题 + overall 统计`

### Task 2: 修正 preview 统计语义

**Files:**
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] 在 `preview_question_bank_from_material()` 中增加 `overall_usage`、`overall_start_time`、`timings` 聚合
- [ ] 让 `stats.duration_seconds / total_tokens` 反映整次 preview 请求，而不是最后一轮 attempt
- [ ] 保留 `generation_attempts`，并增加分步骤 timing 统计

## Chunk 2: planner 单次复用与失败槽位补题

### Task 3: 将 planner 移出 attempt 循环

**Files:**
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] 在 attempt 循环前构建 `generation_slots`
- [ ] 仅调用一次 `generate_question_plan_batch_via_llm()`
- [ ] 将 planner 输出按 `slot_index` 缓存到槽位结构中

### Task 4: 实现失败槽位补题

**Files:**
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] 将槽位分成“已成功”与“待补题”两类
- [ ] 后续 attempt 仅为待补题槽位构建 generator 批次
- [ ] 成功槽位在后续 attempt 中直接复用，不再重跑
- [ ] `errors` 中记录按槽位的失败原因，便于后续归因

### Task 5: 收缩 retry 触发条件

**Files:**
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] 仅在 `generated_total < requested_total` 或硬校验拒绝时进入下一轮补题
- [ ] 仅有 `validation_reasons`、近重复 warning、后验校准 warning 时不再整轮重试
- [ ] fallback warning 但题数已足时直接返回首轮结果

## Chunk 3: 回归测试与真实性能复测

### Task 6: 补服务层回归测试

**Files:**
- Modify: `tests/test_questions.py`

- [ ] 断言 preview 在 `generation_attempts > 1` 时 planner 仍只调用一次
- [ ] 断言第二轮仅补失败槽位，不重跑成功槽位
- [ ] 断言 warning-only 风险不再触发第二轮
- [ ] 断言 `stats.duration_seconds / total_tokens` 为整次请求累积值

### Task 7: 运行定向验证

**Files:**
- Modify: `tests/test_questions.py`

- [ ] 运行 `python -m py_compile app/services/question_service.py tests/test_questions.py`
- [ ] 运行 `conda run -n ai-literacy python -m pytest tests/test_questions.py -q -k 'preview_question_bank'`

### Task 8: 对素材 `742ae365-8e46-4874-a088-ecf7fb852df1` 做事务回滚性能复测

**Files:**
- Modify: `app/services/question_service.py`
- Test: 手工 profiling 记录

- [ ] 用事务回滚再次 profiling
- [ ] 记录 `planner_calls`、总墙钟、各步骤 timing、真实总 token
- [ ] 与当前基线 `250.96s / planner_calls=2` 做前后对比
