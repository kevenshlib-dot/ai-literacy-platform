# Generator Structured Output Hardening Design

## Goal
让 `generate_questions_via_llm()` 在本地 Qwen 路径下优先消费 SDK 已解析好的结构化对象，降低当前 generator 因文本 `json.loads` 失败导致的重试与 fallback。

## Problem
当前 generator 与 planner 一样，虽然已经带了 `response_format=json_schema`，但返回结果仍默认走 `message.content -> extract_json_text -> json.loads`。  
真实链路里 generator 比 planner 调用次数更多、schema 更复杂，因此它现在是 JSON 漂移与耗时放大的主要来源。

## Scope
本轮只改 generator 路径：

- `generate_questions_via_llm`
- generator 对应的解析模型

不改：

- strict schema
- prompt
- 题型校验规则
- fallback / retry 语义

## Design
### 1. 复用请求层 parse 能力
- 直接复用上一轮请求层新增的 `parse_response_format`
- generator 请求时传入题目数组 Pydantic 模型
- 请求层优先尝试 `beta.chat.completions.parse(...)`

### 2. generator 优先消费 `parsed`
- `generate_questions_via_llm()` 优先读取 `response_data["parsed"]`
- 只有 `parsed is None` 时，才回退到 `content + extract_json_text + json.loads`
- 后续 `_extract_question_payload()`、`_validate_and_fix_question()`、strict type 重试逻辑全部保留

### 3. 解析模型保持宽松
- 使用“题目数组” RootModel 承接输出
- 单题字段使用宽松模型：
  - 允许 `options/rubric/knowledge_tags/dimension/explanation` 缺失
  - 允许额外字段
- 本轮不做题型专属 Pydantic 模型，也不做 strict schema 收紧

## Risks
- parse 模式下，即便对象能被 Pydantic 解析，题目仍可能在 `_validate_and_fix_question()` 被判无效
- 这属于第二层语义校验，不是结构化输出失败；本轮不试图解决

## Verification
- 单元测试验证 generator 在 `parsed` 存在时不依赖文本 JSON
- 单元测试验证 strict type 重试路径不回归
- 单元测试验证 planner 注入路径不回归
