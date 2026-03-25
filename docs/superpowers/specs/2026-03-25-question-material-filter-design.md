# Question Material Filter Design

## Goal
为题库管理页的“全部题目”列表增加素材筛选字段，用户可以从全部素材中选择一个素材，只查看关联该素材的题目；列表统计口径与筛选结果保持一致。

## Current Findings
- 题库管理筛选栏在 [frontend/src/views/Questions.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Questions.vue) 中，目前只支持关键词、状态、题型、难度、维度和“仅看自己”。
- 列表数据与统计数据都来自 `/questions` 和 `/questions/stats`，两者当前都不支持 `source_material_id` 过滤。
- 页面里现有的 `parsedMaterials` 只服务于“新建题库”弹窗，且只加载 `parsed/vectorized` 素材，不适合作为“全部素材”筛选数据源。

## Design
### 1. 后端补齐素材过滤参数
- 为 `/questions` 增加可选查询参数 `source_material_id`。
- 为 `/questions/stats` 增加同名参数，保证统计与列表使用同一过滤条件。
- 在 `question_service` 中把该参数映射为 `Question.source_material_id == <id>` 条件。

### 2. 前端新增素材筛选字段
- 在“全部题目”筛选栏增加单选素材下拉。
- 下拉数据独立加载，不复用 `parsedMaterials`。
- 首次展开下拉时循环请求 `/materials`，按分页拉取全部素材并缓存到页面状态。
- 选择素材后仅在点击“查询”时生效；点击“重置”时一并清空。

### 3. 交互与口径保持一致
- `fetchQuestions`、`fetchQuestionStats`、批量操作后的列表刷新都要带上 `source_material_id`。
- 素材筛选只作用于“全部题目”页，不影响“批量审核”页和题目详情抽屉。

## Verification
- 后端回归：
  - `/questions?source_material_id=<id>` 只返回该素材下的题目。
  - `/questions/stats?source_material_id=<id>` 只统计该素材下的题目。
- 前端验证：
  - `cd frontend && npm run build`
  - 打开题库管理页，素材下拉可选全部素材，查询后列表与统计同步收敛。
