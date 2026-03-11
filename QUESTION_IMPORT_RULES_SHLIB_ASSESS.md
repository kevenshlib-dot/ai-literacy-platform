# 题库导入规则说明（适配 `paper_llm_dryrun_qwen35plus_enhanced.json`）

本文档说明如何将外部题目数据文件：

`/home/ps/project/shlib_assess/outputs/paper_llm_dryrun_qwen35plus_enhanced.json`

导入到当前项目 `ai-literacy-platform` 的题库中，并覆盖以下内容：

- 当前项目原生支持的导入方式
- 题目字段的真实约束
- 源 JSON 与本项目字段的映射规则
- 需要先转换的字段
- 不会被直接保留的源数据字段

## 1. 结论

这份 JSON **不能直接导入** 当前项目，必须先做一次字段转换。

原因有三类：

1. 当前项目原生导入接口只直接支持 Markdown 导入
   接口为 `POST /api/v1/questions/batch/import-md`
2. 如果走原始结构批量保存接口，则请求体必须符合 `BatchCreateFromRawRequest`
   接口为 `POST /api/v1/questions/batch/create-raw`
3. 这份源 JSON 的字段命名、题型枚举、难度枚举、选项格式，和项目题库结构不一致

因此推荐路径是：

```text
源 JSON
-> 转换为本项目 PreviewQuestionItem 列表
-> 调用 /api/v1/questions/batch/create-raw
-> 导入为 draft 状态题目
```

## 2. 当前项目支持的导入方式

### 2.1 Markdown 导入

项目已有原生接口：

```text
POST /api/v1/questions/batch/import-md
```

要求：

- 上传 `.md` 文件
- 文件编码必须为 UTF-8
- 文件内容必须符合项目导出的 Markdown 结构
- 导入后题目统一写入为 `draft`

项目内部解析逻辑只识别以下结构：

- `<!-- meta: {...} -->`
- `**题干：**`
- `**正确答案：**`
- `**解析：**`
- `**评分标准：**`
- 选项表格 `| A | xxx |`

### 2.2 原始题目批量保存

项目还有一个更适合程序化导入的接口：

```text
POST /api/v1/questions/batch/create-raw
```

这个接口接收的每道题结构必须符合：

```json
{
  "question_type": "single_choice",
  "stem": "题干",
  "options": {"A": "选项1", "B": "选项2"},
  "correct_answer": "A",
  "explanation": "解析",
  "difficulty": 3,
  "dimension": "AI伦理安全",
  "knowledge_tags": ["标签1", "标签2"],
  "bloom_level": "understand",
  "source_material_id": null,
  "source_knowledge_unit_id": null
}
```

这也是本次导入最推荐的方式。

## 3. 本项目题库字段约束

### 3.1 支持的题型

项目底层 `QuestionType` 只接受以下值：

- `single_choice`
- `multiple_choice`
- `true_false`
- `fill_blank`
- `short_answer`
- `essay`
- `sjt`

注意：

- 源文件中的 `judgment` 不是合法值
- 导入前必须转换为 `true_false`

### 3.2 难度字段

项目要求：

- `difficulty` 必须是 `1` 到 `5` 的整数

而源文件使用的是：

- `easy`
- `medium`
- `hard`

因此必须先映射。

推荐映射：

```text
easy   -> 2
medium -> 3
hard   -> 4
```

说明：

- 项目是 1-5 五级难度
- 源数据只有三级
- 用 `2/3/4` 比 `1/3/5` 更平滑，也更接近当前系统默认难度 `3`

### 3.3 options 字段

项目要求：

- `options` 应为 `dict`
- 选择题常见格式为：

```json
{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}
```

而源文件中：

- `options` 是 `list`
- 单选题是 `["A. ...", "B. ...", "C. ...", "D. ..."]`
- 判断题是 `["正确", "错误"]`
- 论述题是 `[]`

因此必须转换。

### 3.4 正确答案字段

项目要求：

- 单选题：`A/B/C/D`
- 判断题：通常使用 `A` 或 `B`
- 主观题：直接存答案文本

而源文件中：

- 单选题答案通常已经是 `A`
- 判断题答案是 `正确` / `错误`
- 论述题答案常带前缀，如 `参考答案：...`

因此也要转换。

### 3.5 状态字段

当前导入逻辑不会接收源文件状态，导入后统一为：

```text
draft
```

也就是说，导入后仍需人工提交审核。

## 4. 源 JSON 结构概览

该文件顶层是一个对象，核心题目数据位于：

```text
questions
```

每个题目对象当前包含这类字段：

- `question_id`
- `question_type`
- `difficulty`
- `metric_id`
- `metric_l1`
- `metric_l2`
- `metric_l3`
- `applicable_library_types`
- `applicable_roles`
- `applicable_levels`
- `question`
- `options`
- `answer`
- `explanation`
- `source_doc`
- `source_locator`
- `source_snippet`
- `generation_meta`

经检查，这份文件当前共有：

- 18 道题
- 题型分布：
  - `judgment`: 10
  - `single_choice`: 6
  - `essay`: 2

## 5. 源字段到项目字段的映射规则

推荐映射如下：

| 源字段 | 目标字段 | 处理规则 |
|---|---|---|
| `question_type` | `question_type` | `judgment -> true_false`，其余保持或按项目枚举映射 |
| `question` | `stem` | 直接映射 |
| `options` | `options` | 从 list 转成 dict |
| `answer` | `correct_answer` | 按题型转换 |
| `explanation` | `explanation` | 直接映射 |
| `difficulty` | `difficulty` | `easy/medium/hard -> 2/3/4` |
| `metric_l1/metric_l2/metric_l3` | `knowledge_tags` | 推荐合并成数组 |
| `metric_l1` | `dimension` | 建议按项目维度规则再映射，不建议直接原样写入 |
| `source_doc/source_locator/source_snippet` | `rubric` 或额外备注 | 项目题表无专门字段，需落到扩展字段或外部保留 |
| `question_id` | 不直接入库主键 | 可放入 `rubric.import_meta` 或单独保存在转换文件中 |

## 6. 推荐的维度映射规则

项目题库维度通常使用这 5 类：

- `AI基础知识`
- `AI技术应用`
- `AI伦理安全`
- `AI批判思维`
- `AI创新实践`

而源数据中的一级分类如：

- `AI伦理`
- `AI能力`
- `AI知识`

它们不能直接完全等价映射，需要转换。

推荐先按以下规则映射：

```text
AI伦理 -> AI伦理安全
AI知识 -> AI基础知识
AI能力 -> 结合 metric_l2 / metric_l3 细分：
  - 含“角色定位”“认知”“判断” -> AI批判思维
  - 含“程序开发”“系统运维”“工具使用”“工作流” -> AI创新实践
  - 含“应用”“场景”“业务使用” -> AI技术应用
  - 无法判断时 -> AI技术应用
```

如果转换脚本不想做复杂规则，也可以：

1. 不传 `dimension`
2. 由项目现有逻辑或后续人工校正处理

但如果直接通过 `create_question` 导入，而不是走 LLM 校验链路，那么最好在转换前就给出明确 `dimension`。

## 7. options 转换规则

### 7.1 单选题

源格式：

```json
[
  "A. 依据在实践中、理想的人建立可验证流程并保留证据链",
  "B. 优先追求速度，忽略证据边界",
  "C. 在未核验来源时直接对外发布结论",
  "D. 把关键判断完全交给模型"
]
```

目标格式：

```json
{
  "A": "依据在实践中、理想的人建立可验证流程并保留证据链",
  "B": "优先追求速度，忽略证据边界",
  "C": "在未核验来源时直接对外发布结论",
  "D": "把关键判断完全交给模型"
}
```

处理规则：

- 去掉前缀 `A. `、`B. `、`C. `、`D. `
- 保留键名为 `A/B/C/D`

### 7.2 判断题

源格式：

```json
["正确", "错误"]
```

目标格式：

```json
{
  "A": "正确",
  "B": "错误"
}
```

同时答案字段也要同步转换：

```text
正确 -> A
错误 -> B
```

### 7.3 论述题

源格式：

```json
[]
```

目标格式：

```json
null
```

## 8. correct_answer 转换规则

### 8.1 单选题

通常直接保留：

```text
A -> A
B -> B
C -> C
D -> D
```

### 8.2 判断题

源答案：

- `正确`
- `错误`

目标答案：

```text
正确 -> A
错误 -> B
```

### 8.3 论述题

若源答案带前缀：

```text
参考答案：需明确场景目标、实施步骤、证据留痕与风险控制，并给出可执行分工。
```

建议导入前去掉前缀，存为：

```text
需明确场景目标、实施步骤、证据留痕与风险控制，并给出可执行分工。
```

## 9. knowledge_tags 推荐构造方式

项目的 `knowledge_tags` 是一个 list，推荐用源文件里的指标分层来构造：

```json
[
  "M0083",
  "AI伦理",
  "伦理认知与价值观",
  "数据伦理学的核心概念认知"
]
```

也可以用更简化版本：

```json
[
  "AI伦理",
  "伦理认知与价值观",
  "数据伦理学的核心概念认知"
]
```

推荐保留 `metric_id`，这样后续还能反查来源指标体系。

## 10. 不会被题库主表直接保存的字段

当前项目题目主表没有专门字段承载以下源数据：

- `question_id`
- `applicable_library_types`
- `applicable_roles`
- `applicable_levels`
- `source_doc`
- `source_locator`
- `source_snippet`
- `generation_meta`

如果这些信息需要保留，推荐两种方案：

### 方案 A：塞进 `rubric`

示例：

```json
{
  "import_meta": {
    "source_question_id": "Q001",
    "metric_id": "M0083",
    "applicable_library_types": ["public"],
    "applicable_roles": ["service"],
    "applicable_levels": ["newbie"],
    "source_doc": "AI4SS指南完整版.pdf",
    "source_locator": "p059#sec-...",
    "source_snippet": "在实践中，理想的人-AI协作应该是这样的流程..."
  }
}
```

### 方案 B：仅在离线转换文件中保留

即：

- 导入题库只保留核心出题字段
- 额外元数据存到单独 JSON 归档文件

如果当前系统不需要在前端展示这些元信息，方案 B 更简单。

## 11. 推荐导入目标结构

如果走 `/api/v1/questions/batch/create-raw`，推荐最终转换成如下结构：

```json
{
  "questions": [
    {
      "question_type": "single_choice",
      "stem": "在公共图书馆-服务岗位-新手中处理在实践中、理想的人相关任务时（案例S001），以下哪项更符合“数据伦理学的核心概念认知”要求？",
      "options": {
        "A": "依据在实践中、理想的人建立可验证流程并保留证据链",
        "B": "优先追求速度，忽略证据边界",
        "C": "在未核验来源时直接对外发布结论",
        "D": "把关键判断完全交给模型"
      },
      "correct_answer": "A",
      "explanation": "证据中的“在实践中、理想的人”提示应采用可验证与可追溯的做法。",
      "difficulty": 2,
      "dimension": "AI伦理安全",
      "knowledge_tags": ["M0083", "AI伦理", "伦理认知与价值观", "数据伦理学的核心概念认知"],
      "bloom_level": null,
      "source_material_id": null,
      "source_knowledge_unit_id": null
    }
  ]
}
```

## 12. 推荐导入流程

推荐按以下步骤执行：

1. 读取源 JSON 顶层的 `questions`
2. 逐题做字段映射
3. 统一规范题型、难度、选项、答案
4. 生成符合 `BatchCreateFromRawRequest` 的 JSON
5. 调用：

```text
POST /api/v1/questions/batch/create-raw
```

6. 导入成功后，题目状态默认是 `draft`
7. 再按业务需要执行批量送审

## 13. 本次源文件的特殊注意事项

这份源文件当前至少有以下特殊点，转换时必须处理：

1. `judgment` 不是本项目合法题型，必须转为 `true_false`
2. `options` 全部是 `list`，而不是 `dict`
3. 判断题答案是中文，不是 `A/B`
4. 论述题答案带 `参考答案：` 前缀
5. 难度不是整数，必须映射
6. 源 JSON 中很多元数据无法直接进入题目主表

## 14. 推荐做法

如果目标是“尽快导入且兼容现有项目”，推荐采用以下最小落地方案：

1. 只导入核心字段：
   - `question_type`
   - `stem`
   - `options`
   - `correct_answer`
   - `explanation`
   - `difficulty`
   - `dimension`
   - `knowledge_tags`
2. `rubric` 可选，不强制
3. `source_material_id` / `source_knowledge_unit_id` 统一设为 `null`
4. 通过 `/questions/batch/create-raw` 导入

这样最符合当前系统实际能力，也最少碰到表结构限制。

## 15. 后续可扩展方向

如果后续需要长期支持这类外部 JSON 导入，建议新增一个专用导入器，例如：

```text
POST /api/v1/questions/batch/import-json
```

由后端直接处理：

- 题型映射
- 难度映射
- list options -> dict options
- judgment -> true_false
- 中文答案 -> A/B
- 元数据落到 `rubric.import_meta`

这样后续同类文件就不需要每次手工转换。
