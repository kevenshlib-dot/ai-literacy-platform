# Question Bank Overflow Design

## Goal
修复题库管理页中两类内容溢出问题：

- 列表页长题干、长来源内容导致表格横向布局不稳定，固定操作列未真正悬浮在右侧。
- 题目详情抽屉首次打开时，长文本偶发横向超出描述表格；再次打开后恢复正常换行。

## Current Findings
- 题库管理主列表和审核列表都在 [frontend/src/views/Questions.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Questions.vue) 中，列宽已配置，但表格未设置横向 `scroll`。
- 操作列虽然声明了 `fixed: 'right'`，但在没有横向滚动上下文时，固定列行为不稳定。
- 详情抽屉使用 `a-descriptions bordered`。`ant-design-vue` 的 bordered descriptions 内部表格布局是 `table-layout: auto`，长内容在首轮布局时更容易撑开。
- 抽屉中的题干、解析、来源、审核意见等长文本没有统一的换行策略。

## Design
### 1. 稳定列表表格的横向布局
- 为“全部题目”和“批量审核”两张表补充显式 `:scroll="{ x: ... }"`。
- 保持现有 `fixed: 'right'` 操作列定义，使操作列在横向滚动时固定在右侧。
- 保留题干两行截断与来源单行截断，不改动当前信息密度。

### 2. 稳定详情抽屉首次打开布局
- 为题目详情抽屉启用 `forceRender`，减少首次打开时内容与容器同时挂载带来的布局抖动。
- 为详情 descriptions 增加局部 class，覆盖内部 bordered table 的布局为 `table-layout: fixed`，避免长内容把表格撑宽。

### 3. 统一详情长文本换行策略
- 题干、选项、解析、来源、审核意见、校准说明使用统一长文本样式：
  - `overflow-wrap: anywhere`
  - `word-break: break-word`
  - 需要保留换行的字段使用 `white-space: pre-wrap`
- 保持现有内容结构与操作按钮布局不变。

## Verification
- 前端构建通过：`cd frontend && npm run build`
- 手动验证：
  - 题库管理列表横向滚动时，操作列固定在右侧。
  - 首次打开长题目详情时不再出现横向超出。
  - 题干、解析、来源、审核意见等长文本在抽屉内稳定换行。
