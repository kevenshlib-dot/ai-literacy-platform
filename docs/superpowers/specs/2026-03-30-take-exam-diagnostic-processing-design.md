# 交卷后诊断处理中视图设计

## 背景

当前正式考试的流程是考生在 [TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue) 交卷后跳转到成绩管理页，再由用户手动点击诊断报告。首次点击时如果诊断报告尚未生成，前端会同步调用 `GET /scores/{score_id}/diagnostic`，这一步会触发评分分析与 LLM 结构化诊断生成，耗时较长时容易被浏览器端超时放大成“网络连接失败”。

用户期望的体验是：提交答卷后留在当前页面，明确看到“正在评分/正在生成诊断报告”的处理中状态，直到正式报告可展示为止。

## 目标

1. 正式考试交卷后不再直接跳转成绩页，而是在当前页面切换到处理中视图。
2. 处理中视图按阶段展示处理状态，让用户知道系统在推进。
3. 诊断报告准备完成后，当前页直接展示诊断报告内容。
4. 首次生成诊断报告不再依赖一次同步长请求，避免前端超时报“网络连接失败”。
5. 随机测试维持现有快速出结果流程，不纳入本次改造。

## 非目标

1. 不引入 Celery、RabbitMQ 消费任务或新的消息队列架构。
2. 不重做成绩管理页的诊断报告弹窗结构。
3. 不改变随机测试提交流程。

## 方案概述

### 前端

在 [TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue) 中新增正式考试提交后的流程态：

- `taking`
- `processing`
- `diagnostic_ready`
- `processing_failed`

提交正式考试后，页面从答题视图切换到处理中视图。处理中视图展示以下阶段：

1. `答卷已提交`
2. `正在评分`
3. `正在生成诊断报告`
4. `诊断报告已就绪`

前端流程：

1. 调用 `POST /sessions/{sheet_id}/submit`
2. 成功后切换到处理中视图
3. 调用 `POST /scores/process/{answer_sheet_id}` 启动处理
4. 轮询 `GET /scores/process/{answer_sheet_id}` 获取阶段状态
5. 状态为 `completed` 后，调用 `GET /scores/{score_id}/diagnostic`
6. 拉到报告数据后切换为诊断报告展示视图

失败时展示失败状态，并提供“重试生成”“返回成绩页”两个操作。

### 后端

新增轻量处理接口，但不引入新持久化表：

- `POST /scores/process/{answer_sheet_id}`
- `GET /scores/process/{answer_sheet_id}`

`POST` 接口职责：

1. 如果成绩和诊断报告已存在，直接返回完成态
2. 如果尚未处理，则启动后台异步处理任务
3. 避免重复启动同一答题卡的并发处理

`GET` 接口职责：

1. 返回当前处理阶段
2. 在任务运行时提供阶段进度
3. 在任务已完成但内存状态已丢失时，基于 `AnswerSheet.status`、`Score`、`diagnostic_report` 缓存回推最终状态

后台处理逻辑：

1. 必要时生成成绩
2. 生成基础成绩报告
3. 生成诊断报告
4. 成功后写回缓存态与 `Score.report`

### 诊断生成超时控制

为了避免其他入口再次触发超长同步等待，[diagnostic_service.py](/home/ps/project/ai-literacy-platform/app/services/diagnostic_service.py) 中的 LLM 结构化诊断生成增加显式超时，超时或异常时退回规则版诊断内容。这样即使从成绩管理页直接打开诊断报告，也不会无限等待或轻易触发前端超时。

## 数据与状态模型

状态接口统一返回：

- `answer_sheet_id`
- `stage`: `submitted | scoring | generating_diagnostic | completed | failed`
- `score_id`
- `diagnostic_ready`
- `message`

阶段语义：

- `submitted`: 答卷已提交，处理已排队或等待启动
- `scoring`: 正在生成成绩
- `generating_diagnostic`: 成绩已完成，正在生成诊断报告
- `completed`: 诊断报告已生成，可直接读取
- `failed`: 处理失败，可重试

## 组件边界

1. [TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue)
   负责正式考试提交后的流程切换、处理中视图、轮询与最终报告承载。
2. [Scores.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Scores.vue)
   保留成绩管理入口，不承担这次提交流程编排。
3. [app/api/v1/endpoints/scores.py](/home/ps/project/ai-literacy-platform/app/api/v1/endpoints/scores.py)
   提供处理启动接口、状态查询接口。
4. [app/services/diagnostic_service.py](/home/ps/project/ai-literacy-platform/app/services/diagnostic_service.py)
   负责诊断报告生成与超时回退。

## 错误处理

1. `submit` 失败：仍停留在答题视图，维持原错误提示。
2. 处理启动失败：进入失败视图，允许重试。
3. 后台处理失败：状态接口返回 `failed`，前端展示失败说明。
4. 诊断报告详情读取失败：保留处理中完成状态，并提供单独的“重试加载报告”。

## 测试要点

1. 启动处理接口在已有缓存时直接返回完成态。
2. 状态接口能正确反映处理中和完成态。
3. 诊断 LLM 超时时会回退到规则版报告，不导致接口长时间悬挂。
4. 正式考试提交后前端能进入处理中态并在完成后显示报告。
