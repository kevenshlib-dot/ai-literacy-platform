# Typed Generator Parse Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 generator 在 parse 路径下按题型强制要求关键字段，从而减少选择题因缺少 `options` 触发的无效生成。

**Architecture:** 用题型化 Pydantic 模型替换当前宽松的 generator parse 模型。请求层 parse 成功后直接返回强校验结果；如字段不全，则让 generator 进入现有重试或 fallback，而不是回退到文本 JSON 解析。

**Tech Stack:** OpenAI Python SDK, Pydantic v2, pytest

---

## Chunk 1: generator 题型化 parse 模型

### Task 1: 增加题型化 Pydantic 模型

**Files:**
- Modify: `app/agents/question_agent.py`

- [ ] 增加选择题 options 模型
- [ ] 增加 single/multiple/true_false/fill_blank/short_answer 的 Pydantic 模型
- [ ] 增加按 `question_types` 组装的 RootModel

## Chunk 2: generator 走题型化 parse

### Task 2: 改造 generate_questions_via_llm 的 parse_response_format

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 根据 `question_types` 传入题型化 parse 模型
- [ ] 保持无 `parsed` 时的文本回退不变
- [ ] 保持现有重试/fallback 语义不变

## Chunk 3: 回归验证

### Task 3: 补测试并验证

**Files:**
- Modify: `tests/test_question_generation_compare.py`

- [ ] 验证选择题缺少 options 时 parse 路径不会被当成成功
- [ ] 验证 true_false / fill_blank 的 parsed 路径仍可用
- [ ] 验证 generator 既有 parse/重试测试不回归
