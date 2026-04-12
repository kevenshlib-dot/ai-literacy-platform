# AI素养评测平台 v2.0 版本更新总结

**发布日期**: 2026-04-08
**版本号**: v2.0.0
**上一稳定版本**: v1.0.0（可通过 `git checkout v1.0.0` 回退）

---

## 一、版本概述

v2.0 是一次重大功能升级，围绕 **试卷管理** 和 **题库互通** 两大核心能力进行了全面建设，同时对系统配置、考试管理等模块进行了改进优化。

---

## 二、新增功能

### 2.1 试卷管理模块（全新）

| 功能 | 说明 |
|------|------|
| 试卷 CRUD | 创建、编辑、删除试卷，支持标题/描述/时限/标签 |
| 大题分区 | 试卷支持多个大题（Section），每个大题可设置题型、分值规则 |
| 题目组装 | 从题库手动选题或自动组卷（按题型/难度/维度/标签） |
| 题目排序 | 拖拽或接口调整大题和题目顺序 |
| 试卷发布 | 草稿 → 已发布，发布时自动创建关联考试 |
| 试卷归档 | 已发布 → 已归档，归档时自动关闭关联考试 |
| 归档管理 | 独立的试卷归档页面，支持恢复（→草稿）和永久删除 |
| 试卷列表 | 已归档试卷自动从试卷管理页面隐藏，仅在归档页可见 |

### 2.2 Word 试卷导入

| 功能 | 说明 |
|------|------|
| 智能解析 | 支持 `.docx` 格式导入，自动识别大题分区、题型、分值 |
| 多种格式兼容 | 支持 `第X部分`、`一、`、`（一）`、独立题型标题等常见中文试卷格式 |
| 分值智能提取 | 识别 `每题X分`、`每小题X分`、`X分/题`、`共X分`、`满分X分` 等描述 |
| 标题识别 | 自动从文档前部提取试卷标题（优先匹配含考试关键词的行） |
| 题型自动推断 | 根据选项数量自动区分选择题 / 判断题 |
| 分值校验 | 自动校验总分合理性，支持按大题总分反算每题分值 |

### 2.3 试卷题目同步至题库

| 功能 | 说明 |
|------|------|
| 同步预览 | 导入题库前进行比对，显示每题状态（已入库/草稿/已修改/缺失） |
| 选择性导入 | 支持勾选指定题目进行同步 |
| 智能去重 | 已在题库中的题目（approved）自动跳过 |
| 草稿提升 | 题库中的草稿题目可直接提升为已审核状态 |
| 覆写入库 | 试卷中有覆写（stem_override/options_override）的题目创建新的题库条目 |

### 2.4 系统配置管理（全新）

| 功能 | 说明 |
|------|------|
| LLM 配置 | 支持通过管理界面配置大模型参数（优先级：UI 配置 > .env 环境变量） |
| 配置持久化 | 系统配置存储于数据库，支持动态修改无需重启 |

### 2.5 试卷导出

| 功能 | 说明 |
|------|------|
| Word 导出 | 试卷可导出为 `.docx` 格式，保留大题结构和分值信息 |
| JSON 导出 | 支持标准化 JSON 格式导出，便于系统间数据交换 |

---

## 三、功能优化

### 3.1 考试管理模块

- 移除状态列和状态筛选（考试状态由关联试卷自动管理）
- 试卷发布时自动创建考试，试卷归档时自动关闭考试

### 3.2 Agent 提示词优化

- 优化出题 Agent（question_agent）提示词
- 优化审核 Agent（review_agent）提示词
- 优化评分 Agent（scoring_agent）提示词
- 优化标注 Agent（annotation_agent）提示词
- 优化意图识别 Agent（intent_agent）提示词
- 优化交互 Agent（interactive_agent）提示词
- 优化指标 Agent（indicator_agents）提示词

### 3.3 文件存储服务

- MinIO 服务增强，支持更多文件操作
- 材料解析服务（parse_worker）优化

### 3.4 前端优化

- 登录/注册页面优化
- Vite 配置优化
- 主布局导航栏新增试卷管理和试卷归档入口

---

## 四、数据库变更

| 迁移文件 | 说明 |
|----------|------|
| `b65dddd8fdaa_add_system_configs_table.py` | 新增系统配置表 |
| `f6ab067da361_add_user_soft_delete_fields.py` | 用户软删除字段（修改） |

新增模型：
- `Paper` — 试卷主表
- `PaperSection` — 试卷大题
- `PaperQuestion` — 试卷题目（关联题库）
- `SystemConfig` — 系统配置

---

## 五、新增文件清单

### 后端

| 文件 | 说明 |
|------|------|
| `app/models/paper.py` | 试卷数据模型 |
| `app/models/system_config.py` | 系统配置数据模型 |
| `app/schemas/paper.py` | 试卷 API Schema |
| `app/api/v1/endpoints/papers.py` | 试卷 API 端点 |
| `app/api/v1/endpoints/system_config.py` | 系统配置 API 端点 |
| `app/services/paper_service.py` | 试卷业务逻辑 |
| `app/services/paper_io_service.py` | 试卷导入导出服务 |
| `app/services/paper_word_parser.py` | Word 试卷解析器 |
| `app/services/paper_word_exporter.py` | Word 试卷导出器 |
| `app/core/llm_config.py` | LLM 配置优先级管理 |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/views/Papers.vue` | 试卷管理页面 |
| `frontend/src/views/PaperEditor.vue` | 试卷编辑器 |
| `frontend/src/views/PaperArchive.vue` | 试卷归档页面 |
| `frontend/src/views/SystemConfig.vue` | 系统配置页面 |

---

## 六、版本兼容性说明

- **v1.0.0** 仍可独立部署，通过 `git checkout v1.0.0` 切换
- **v2.0.0** 需要执行数据库迁移（`alembic upgrade head`）
- 从 v1.0 升级到 v2.0 时，已有数据完全兼容，新增表不影响旧功能
- **推荐部署版本**: v2.0.0
