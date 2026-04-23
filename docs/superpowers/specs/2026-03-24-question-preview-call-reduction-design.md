# 题库预览链路降调用次数设计

## 背景
当前“从素材生成试题 -> 题目预览”链路已经完成了三轮性能优化：
- preview 首屏不再同步执行 AI review
- planner 提升为每轮 attempt 一次
- generator 提升为按题型批量并发执行

但真实 profiling 结果显示，预览总耗时仍然过长。以素材 `742ae365-8e46-4874-a088-ecf7fb852df1`、10 题配置为例：
- 总墙钟时间约 `250.96s`
- planner 两轮共 `173.69s`，约占总耗时 `69%`
- generator 两轮合计约 `76s` 墙钟时间
- 数据库查询、重复检测、题集校验、后验校准加起来不到 `1%`

当前主要瓶颈已经从“调用太多”变成“整轮重试代价过高”。一旦首轮存在局部掉题，系统会整轮重跑，从而再次支付最昂贵的 planner 成本。

## 目标
- 在单次 preview 请求中将 planner 调用次数固定为 `1`
- 将 retry 从“整轮重跑”改成“只补失败槽位”
- 保留现有规则质检、重复检测、后验校准
- 修正 preview 返回统计，使其反映真实整次请求成本

## 非目标
- 本轮不改变题目保存语义
- 本轮不新增复杂的题目状态机
- 本轮不重写并发模型或引入 `AsyncOpenAI`
- 本轮不继续修改题目质量规则本身

## 设计
### 1. 单次请求内 planner 只执行一次
在 `preview_question_bank_from_material()` 内，planner 不再放在 attempt 循环内部。单次请求开始后：
- 先准备素材知识单元
- 先按当前 `unit_type_plan` 构建全部生成槽位
- 调用一次 `generate_question_plan_batch_via_llm()`
- 将 planner 结果缓存到本次请求上下文

同一请求的后续重试只复用这份 planner 结果，不再重新规划。

### 2. retry 改为“只补失败槽位”
首轮 generator 执行后，将槽位分成两类：
- 已成功槽位：保留题目结果，不再重跑
- 失败槽位：按失败原因记录并在下一轮补题

后续 attempt 只为失败槽位重建 generator 批次。成功题目不会被丢弃，也不会因为 warning 被重写。

### 3. retry 条件收缩到“补齐题量”
只有以下情况才会进入下一轮补题：
- `generated_total < requested_total`
- 某些槽位因为结构/题型/内容硬校验被拒绝
- planner 完全失败且 deterministic fallback 也不足

以下情况只保留 warning，不触发 retry：
- `validation_reasons` 但题数已足
- 批内/历史近重复 warning
- 后验校准 warning
- fallback warning 但返回题数已足

这样 retry 的职责从“修饰整批质量”缩窄为“补齐缺题”。

### 4. 统计拆成 overall 与 attempt 两层
当前 preview 返回给前端的 `duration_seconds / total_tokens` 只统计最后一轮 attempt。新实现中：
- `overall_*` 聚合整次请求的真实耗时、token、planner/generator 调用次数
- `attempt_*` 仅保留最后一轮 attempt 的调试信息

对外默认暴露整次请求的真实统计，并补一个 `timings` 对象，至少包含：
- `prepare_units_seconds`
- `planner_seconds`
- `generation_seconds`
- `duplicate_check_seconds`
- `calibration_seconds`
- `attempt_count`

### 5. 保持现有并发模型不变
当前 generator 已经是按题型批量、通过 `asyncio.to_thread + gather + semaphore` 受限并发执行。本轮不再额外调整并发度，也不引入 `AsyncOpenAI`。优先通过“planner 一次 + 失败槽位补题”拿最大收益。

## 风险
- planner 结果跨 attempt 复用后，第二轮补题可能继承首轮的弱规划，导致补题质量不如全量重跑
- 只补失败槽位后，部分统计和日志需要重写，否则会继续低估真实成本
- 如果失败槽位集中在同一题型，局部补题 prompt 可能比全量批次更短，需要确保现有 prompt 在小批量下仍稳定

## 验收
- 单次 preview 请求中 `planner_calls == 1`
- 首轮部分槽位失败时，仅失败槽位进入下一轮 generator
- 前端看到的 `duration_seconds / total_tokens` 与整次请求真实成本一致
- 对素材 `742ae365-8e46-4874-a088-ecf7fb852df1`、10 题配置复测时：
  - 总耗时显著低于当前约 `250s`
  - `planner` 不再因 retry 重复执行
  - 现有规则质检、重复检测、后验校准不回归
