# Material Approved Question Count Design

## Goal
在素材管理列表中增加“题目数量（已审核）”列，显示每个素材关联的已审核通过题目总数。

## Current Findings
- 素材管理列表使用 `/materials` 接口返回的 `MaterialResponse` 数据直接渲染，当前没有题目数量字段。
- 前端列表位于 [frontend/src/views/Materials.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Materials.vue)，只需要加列展示，不需要新增交互。
- 后端 `list_materials` 当前只查询素材自身字段，没有聚合题库数据。

## Design
### 1. 后端在素材列表接口中返回聚合数量
- 在 `material_service.list_materials` 中追加一个按 `Question.source_material_id` 聚合的子查询。
- 只统计 `Question.status == approved` 的题目。
- 通过左连接把聚合结果附着到每条素材记录上，没有命中的素材返回 `0`。

### 2. 扩展素材响应模型
- 在 `MaterialResponse` 中新增 `approved_question_count`，默认值为 `0`。
- 这样 `/materials` 列表接口可直接返回该字段，其他复用该模型的接口在未设置该属性时也保持兼容。

### 3. 前端最小展示改动
- 在素材管理列表增加“题目数量（已审核）”列。
- 直接显示后端返回值，不增加排序、筛选和详情展示。

## Verification
- 后端回归：
  - `/materials` 返回 `approved_question_count`。
  - 仅 `approved` 状态题目会计入数量。
- 前端验证：
  - `cd frontend && npm run build`
  - 素材管理列表正常显示新增列。
