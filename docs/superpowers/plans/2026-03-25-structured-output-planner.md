# Planner Structured Output Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 planner 路径优先消费 SDK 解析后的结构化对象，减少本地 Qwen 下的 JSON 文本漂移。

**Architecture:** 在 OpenAI-compatible 请求层增加可选 `parse_response_format`，优先使用 `beta.chat.completions.parse`，planner 在拿到 `parsed` 后直接走 normalization，失败时再回退到现有文本 JSON 路径。generator 暂不变。

**Tech Stack:** FastAPI backend, OpenAI Python SDK, Pydantic v2, pytest

---

## Chunk 1: 请求层支持 parse 返回

### Task 1: 扩展 OpenAI-compatible 请求层

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 为 `_request_question_generation()` 增加 `parse_response_format` 参数
- [ ] 为 `_request_question_generation_openai_compatible()` 增加 parse 路径
- [ ] 返回统一字段 `parsed` 和 `structured_mode`
- [ ] 保留现有 `response_format` unsupported 降级逻辑

### Task 2: 补请求层测试

**Files:**
- Modify: `tests/test_question_generation_compare.py`

- [ ] 验证 parse 成功时返回 `parsed`
- [ ] 验证 parse 不可用时仍回退到旧路径

## Chunk 2: planner 优先消费 parsed

### Task 3: 为 planner 定义解析模型

**Files:**
- Modify: `app/agents/question_agent.py`

- [ ] 增加单题 planner 的 Pydantic 响应模型
- [ ] 增加 batch planner 的 Pydantic 响应模型

### Task 4: 改造单题 planner

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 优先使用 `response_data["parsed"]`
- [ ] 无 `parsed` 时回退到 `content + json.loads`
- [ ] 保留 deterministic fallback

### Task 5: 改造 batch planner

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 优先使用 `response_data["parsed"]`
- [ ] 无 `parsed` 时回退到 `content + json.loads`
- [ ] 保留 deterministic fallback

## Chunk 3: 回归验证

### Task 6: 跑 planner 相关回归

**Files:**
- Modify: `tests/test_question_generation_compare.py`

- [ ] 跑 planner parse 成功路径测试
- [ ] 跑 batch planner 对齐测试
- [ ] 跑现有 structured output unsupported 回退测试
