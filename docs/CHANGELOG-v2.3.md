# AI素养评测平台 v2.3 版本更新总结

**发布日期**: 2026-04-12
**版本号**: v2.3.0
**上一稳定版本**: v2.2.1

---

## 一、版本概述

v2.3 围绕 **LLM 智能解析**、**交互式导入预览** 和 **系统状态检测** 三大核心能力进行了升级，同时修复了多个影响评分和考试体验的关键 Bug。

---

## 二、Bug 修复（v2.2.1 → v2.3）

| 编号 | 问题 | 原因 | 修复方式 | 涉及文件 |
|------|------|------|----------|----------|
| #1 | 批量删除题目失败 | 外键约束（paper_questions, exam_questions, answers, score_details）阻止删除 | 删除前先清理所有关联记录 | `question_service.py` |
| #2 | 试卷导入答案丢失，评分全零 | Word 导入时 `correct_answer_override` 未传递到 PaperQuestion 和 ExamQuestion | 在 `paper_io_service.py` 的 4 处补上 `correct_answer_override` 字段 | `paper_io_service.py` |
| #3 | Word 解析答案区域检测失败 | 答案区域以"第1题：✗ 错误"格式出现时无法被检测到 | 新增 `ANSWER_SECTION_PATTERNS` 匹配模式，答案解析不再依赖 `current_answer_section_type`，增加跨类型 fallback 搜索 | `paper_word_parser.py` |
| #4 | 判断题显示文本框而非 T/F 按钮 | 判断题 options 字段可能为空 | `answer_service.py` 中强制确保 `true_false` 类型的 options 包含 `{"T":"正确","F":"错误"}` | `answer_service.py` |
| #5 | 最后一题缺少交卷按钮 | "下一题"按钮在最后一题时无实际意义 | TakeExam.vue 中最后一题的"下一题"按钮改为"交卷"按钮（带确认弹窗） | `TakeExam.vue` |

---

## 三、新增功能

### 3.1 LLM 智能试卷解析 Agent

| 功能 | 说明 |
|------|------|
| 智能验证 | 正则解析后调用 LLM 验证/修正题型和答案 |
| 置信度评分 | 为每道题生成置信度分数和问题标注 |
| 分批调用 | 超过 30 题时自动分批调用 LLM |
| 降级策略 | LLM 不可用时无缝降级为纯正则解析结果 |

新增文件：`app/agents/paper_parse_agent.py`

### 3.2 交互式导入预览

| 功能 | 说明 |
|------|------|
| 卡片式预览 | 每题完整展示题干、选项、答案 |
| 全字段可编辑 | 题干、选项、答案均可直接修改 |
| 题型切换 | 下拉选择题型，答案控件自动切换（T/F 单选、选项单选、多选 checkbox、文本 textarea） |
| 三色状态标识 | 绿色（高置信度）/ 黄色（需注意）/ 红色（需修正） |
| AI 建议采纳 | 支持单题"采纳 AI 建议"和"全部采纳"批量操作 |

新增文件：`frontend/src/components/PaperImportPreview.vue`

### 3.3 POST /papers/import-reviewed 端点

| 功能 | 说明 |
|------|------|
| 接收修正数据 | 接收用户在预览界面修正后的题目数据 |
| 字段清洗 | 剥离 LLM 辅助字段（置信度、标注等）后调用现有 `import_paper()` |

### 3.4 试卷创建者显示

| 功能 | 说明 |
|------|------|
| 创建者列 | 试卷列表新增"创建者"列 |
| 批量查询 | 后端批量查询用户名，避免 N+1 查询 |

### 3.5 LLM 状态检测系统

| 层级 | 功能 | 说明 |
|------|------|------|
| 后端 | `check_llm_status()` | `llm_config.py` 新增 LLM 连通性检测函数 |
| 后端 | `GET /system/llm-status` | `system_config.py` 新增状态查询端点 |
| 前端 | Dashboard 警告横幅 | 未配置 LLM 时显示黄色提示横幅 + "前往配置"按钮 |
| 前端 | `useLLMStatus.ts` | 可复用 composable，在题目生成、交卷、试卷导入等操作前检查并提示 |

新增文件：`frontend/src/composables/useLLMStatus.ts`

### 3.6 新增 LLM 模块配置

| 模块 Key | 说明 |
|----------|------|
| `paper_generation` | 试卷生成相关 LLM 调用 |
| `paper_import` | 试卷导入解析相关 LLM 调用 |

以上模块已加入 `MODULE_KEYS` 并在系统配置 UI 中可配置。

---

## 四、新增文件清单

### 后端

| 文件 | 说明 |
|------|------|
| `app/agents/paper_parse_agent.py` | LLM 智能试卷解析 Agent |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/components/PaperImportPreview.vue` | 交互式导入预览组件 |
| `frontend/src/composables/useLLMStatus.ts` | LLM 状态检测 composable |

---

## 五、Agent 清单（9 个）

| Agent | 文件 | 用途 |
|-------|------|------|
| question_agent | `app/agents/question_agent.py` | 题目生成 |
| scoring_agent | `app/agents/scoring_agent.py` | 评分（单评/多评） |
| review_agent | `app/agents/review_agent.py` | 质量审核 |
| interactive_agent | `app/agents/interactive_agent.py` | 情景互动 |
| annotation_agent | `app/agents/annotation_agent.py` | 自动标注 |
| intent_agent | `app/agents/intent_agent.py` | 意图解析 |
| indicator_agents | `app/agents/indicator_agents.py` | 指标分析 |
| **paper_parse_agent** | `app/agents/paper_parse_agent.py` | **试卷解析（新增）** |

---

## 六、版本兼容性说明

- **v2.2.1** 可通过 `git checkout v2.2.1` 回退
- **v2.3.0** 无新增数据库迁移，与 v2.2.1 数据库结构完全兼容
- **推荐部署版本**: v2.3.0
