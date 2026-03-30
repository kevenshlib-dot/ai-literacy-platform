# 独立诊断报告页设计

## 背景

当前诊断报告虽然已经抽出了共享内容组件，但入口仍分散在两个页面壳子中：

1. 成绩管理页 [Scores.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Scores.vue) 内嵌报告区域
2. 交卷后的 [TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue) 中间态里内嵌报告区域

这会导致页面生命周期、返回路径、图表初始化时机和后续维护仍然分叉。用户已经明确希望“无论从哪里进入，都跳到同一个诊断分析报告页面”，以保证一致性。

## 目标

1. 新增独立诊断报告页，成为唯一报告展示入口。
2. 成绩页点击“诊断报告”跳转到独立页面。
3. 正式考试提交后，处理中完成即自动跳转到独立页面。
4. 报告内容继续复用 [DiagnosticReportView.vue](/home/ps/project/ai-literacy-platform/frontend/src/components/DiagnosticReportView.vue)，避免再出现两处报告内容漂移。

## 非目标

1. 不改变后端诊断数据结构。
2. 不改变评分/诊断处理状态接口。
3. 不改变随机测试流程。

## 方案概述

### 路由

新增前端路由：

- `/scores/:scoreId/diagnostic`

对应页面：

- [ScoreDiagnostic.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/ScoreDiagnostic.vue)

这个页面是完整诊断报告的唯一壳子，负责：

1. 根据 `scoreId` 获取诊断报告
2. 统一显示返回入口
3. 统一承载“下载报告 / 下载证书”
4. 复用 [DiagnosticReportView.vue](/home/ps/project/ai-literacy-platform/frontend/src/components/DiagnosticReportView.vue) 展示内容

### 成绩页

[Scores.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Scores.vue) 不再在页内展开完整诊断报告，改为：

1. 列表中点击“诊断报告”直接 `router.push`
2. 管理员和个人视图都复用这一跳转逻辑
3. 原先页内报告相关状态和渲染逻辑删除

这样成绩页重新回到“列表 / 复盘 / 训练 / 管理操作”的边界。

### 交卷页

[TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue) 继续负责：

1. 考试中
2. 提交后处理中
3. 处理失败重试

但不再负责最终报告渲染。处理完成后直接：

- `router.replace({ name: 'ScoreDiagnostic', params: { scoreId } })`

这样交卷页只承担流程编排，不承担报告展示。

## 页面行为

### 独立报告页

页面加载流程：

1. 读取 `route.params.scoreId`
2. 请求 `GET /scores/{scoreId}/diagnostic`
3. 成功后渲染完整报告
4. 失败时显示错误态，并提供返回成绩页

辅助信息：

1. 用户名优先取路由 query 中的 `displayName`
2. 没有 query 时，默认回退当前登录用户姓名/用户名

### 入口一致性

1. 成绩页进入：跳到独立报告页
2. 交卷完成进入：自动跳到独立报告页
3. 后续如果增加分享、打印、导出，只需要改这一页

## 组件边界

1. [DiagnosticReportView.vue](/home/ps/project/ai-literacy-platform/frontend/src/components/DiagnosticReportView.vue)
   只负责报告主体内容和图表。
2. [ScoreDiagnostic.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/ScoreDiagnostic.vue)
   负责页面壳子、取数、下载、返回。
3. [Scores.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/Scores.vue)
   只负责跳转，不再直接展示完整报告。
4. [TakeExam.vue](/home/ps/project/ai-literacy-platform/frontend/src/views/TakeExam.vue)
   只负责处理状态和自动跳转。

## 验证要点

1. 从成绩页进入和交卷后自动进入，最终都落到同一个路由页面。
2. 独立报告页能正确显示雷达图和柱状图。
3. 成绩页不再保留页内完整报告状态。
4. 前端构建通过。
