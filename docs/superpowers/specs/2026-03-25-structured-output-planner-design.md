# Planner Structured Output Hardening Design

## Goal
让 `planner` 和 `batch planner` 在本地 Qwen 路径下优先消费 SDK 已解析好的结构化对象，减少当前“已启用结构化输出但仍因文本 `json.loads` 失败”的问题。

## Problem
当前 `planner` / `batch planner` 虽然已经带了 `response_format=json_schema`，但返回结果仍按 `message.content -> extract_json_text -> json.loads` 处理。  
这会把“模型已经支持结构化输出”重新降级成“依赖文本 JSON 严格合法”，只要模型多输出一个字符或少一个逗号就会失败。

## Scope
本轮只改 `planner` 路径：

- `generate_question_plan_via_llm`
- `generate_question_plan_batch_via_llm`
- `_request_question_generation(_openai_compatible)`

不改：

- `generator`
- `review`
- schema strict 级别
- prompt 内容

## Design
### 1. 增加统一的结构化响应消费层
- 在请求层支持可选的 `parse_response_format`
- 当模型支持结构化输出且提供了 `parse_response_format` 时，优先调用 `client.beta.chat.completions.parse(...)`
- 返回统一结构：
  - `content`
  - `parsed`
  - `usage`
  - `structured_mode`

### 2. planner 优先消费 `parsed`
- `generate_question_plan_via_llm()` 和 `generate_question_plan_batch_via_llm()` 优先读取 `response_data["parsed"]`
- 只有 `parsed is None` 时，才回退到当前 `extract_json_text + json.loads`
- 继续保留现有本地 deterministic fallback

### 3. parse 模型先做宽松版
- 使用 Pydantic `RootModel[list[...]]` 定义 planner 输出模型
- 不在本轮引入动态 strict schema
- 仍然依赖现有 normalization 兜底 question_type、slot_index、dimension 等字段

### 4. 失败分类更清晰
- 请求层返回 `structured_mode`，区分：
  - `parse`
  - `response_format_text`
  - `plain_text`
- 后续分析可以看出是“直接 parse 成功”还是“退回文本 JSON”

## Risks
- 某些 OpenAI-compatible 端点可能支持 `response_format`，但不支持 `beta.parse`
- 因此 parse 路径必须保留现有回退：
  - parse 失败 -> 继续走 `chat.completions.create`
  - structured output 不支持 -> 去掉 `response_format` 重试

## Verification
- 单元测试验证 `_request_question_generation_openai_compatible()` 在 parse 成功时返回 `parsed`
- 单元测试验证 `generate_question_plan_via_llm()` 优先使用 `parsed`
- 单元测试验证 `generate_question_plan_batch_via_llm()` 优先使用 `parsed`
