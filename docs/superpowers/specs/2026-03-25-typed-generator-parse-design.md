# Typed Generator Parse Design

## Goal
让 generator 在 `parse` 路径下按题型校验必填字段，避免当前“结构化对象可解析，但选择题缺少 `options` 仍被当作成功结构”的问题。

## Problem
上一轮已经让 generator 优先消费 `message.parsed`。
但当前 parse 模型过于宽松，`single_choice` / `multiple_choice` 缺少 `options` 时仍能通过 Pydantic 解析，随后才在业务校验里触发 `缺少有效选项`，导致：

- 结构化成功，但业务上整批无效
- generator fallback 仍高
- 真正的问题从“非法 JSON”变成了“题型字段不完整”

## Scope
本轮只改 generator 的 parse 模型：

- 为不同题型定义更严格的 Pydantic 模型
- `generate_questions_via_llm()` 在 parse 路径下直接依赖这些模型进行第一层字段约束

不改：

- `response_format` dict schema
- prompt
- planner
- retry / fallback 语义

## Design
### 1. 为 generator 建立题型化模型
- `single_choice`: 必须有 `options`，且包含 `A/B/C/D`
- `multiple_choice`: 必须有 `options`，且包含 `A/B/C/D`
- `true_false`: 必须有 `options={"A":"正确","B":"错误"}`
- `fill_blank`: `options=None`
- `short_answer`: `options=None`

### 2. 多题型使用联合模型
- 预览链路虽然大多数时候按单题型批量调用 generator，但 `generate_questions_via_llm()` 仍是通用入口
- 因此 parse 模型要支持：
  - 单一题型时：对应 RootModel
  - 多题型时：联合 RootModel

### 3. parse 失败直接走现有重试/降级
- 如果 `parse` 路径因为字段缺失而失败，不再退回文本解析“补救”
- 直接让这一轮生成进入现有的重试 / fallback 逻辑

## Verification
- 单测覆盖单选/多选缺少 `options` 时，parse 路径判失败
- 单测覆盖 `true_false` / `fill_blank` 仍可正常 parse
- 真实复测看 `Only 0/N questions passed validation: 缺少有效选项` 是否下降
