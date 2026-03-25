# Generator Structured Output Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 generator 优先消费 SDK 解析后的结构化对象，减少本地 Qwen 下的 JSON 文本漂移与无效重试。

**Architecture:** 复用现有请求层 parse 能力，为 generator 增加宽松的题目数组解析模型；`generate_questions_via_llm()` 优先消费 `parsed`，失败时回退到现有文本 JSON 路径与题型校验逻辑。

**Tech Stack:** OpenAI Python SDK, Pydantic v2, pytest

---

## Chunk 1: 生成结果解析模型

### Task 1: 增加 generator 宽松解析模型

**Files:**
- Modify: `app/agents/question_agent.py`

- [ ] 增加单题宽松 Pydantic 模型
- [ ] 增加题目数组 RootModel
- [ ] 保持 extra 字段可通过

## Chunk 2: generator 优先消费 parsed

### Task 2: 改造 generate_questions_via_llm

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 请求层调用时传入 `parse_response_format`
- [ ] 优先使用 `response_data["parsed"]`
- [ ] 无 `parsed` 时回退到 `content + json.loads`
- [ ] 保持现有重试、fallback、校验逻辑不变

## Chunk 3: 回归验证

### Task 3: 补 generator 定向测试

**Files:**
- Modify: `tests/test_question_generation_compare.py`

- [ ] 验证 generator 优先消费 parsed
- [ ] 验证 strict type 重试路径不回归
- [ ] 验证 planner 注入与 usage 统计不回归
