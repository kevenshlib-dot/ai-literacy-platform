# Content-Layer Risk Reduction Design

## Goal
降低素材生成题目在真实链路中剩余的内容层风险，重点解决：

- 素材元信息或 prompt 标记泄漏到题干/解析
- 同批题知识点重复
- 生成批次中沿用同一角色/同一题干模板

## Current Findings
- 结构化输出链路已经明显稳定，选择题 `options` 缺失问题基本解决。
- 当前主要失败项转为：
  - `题目包含素材元信息或禁用表述`
  - `知识点重复`
  - `题干开头/职业角色重复`
- 这些问题目前主要在整批校验时发现，单题阶段拦截太晚。

## Design
### 1. 单题前置拦截内容泄漏
- 在 `_validate_and_fix_question()` 中新增内容层前置校验：
  - 素材元信息禁用表述
  - prompt/规划标记泄漏
  - 乱码残留
- 命中后直接丢弃该题，让现有重试逻辑接管。

### 2. Planner 批次去重回退
- 对 batch planner 的归一化结果增加轻量去重：
  - 若多个槽位返回相同 `knowledge_point/evidence` 签名
  - 优先回退到对应槽位的 deterministic fallback plan
- 这样不改变 planner 架构，但能降低同一概念被批量复写的概率。

### 3. Prompt 约束更贴近内容层问题
- batch planner prompt 增加：
  - 不同槽位的知识点必须语义明显不同
  - 人物/职业情境不得重复
  - 最终题目中不得出现“素材/材料/参考素材/槽位”等来源提示
- question plan section 同步补充相同约束。

### 4. Generator 槽位标记去提示词化
- 批量 generator 素材拼接从中文说明性标记改成中性 `<slot index="...">`。
- 避免模型直接把“题目槽位/参考素材”类提示词写回题干。

## Verification
- 单测验证单题前置拦截生效。
- 单测验证 batch planner 遇到重复知识点时回退到 fallback plan。
- 单测验证 generator 槽位内容不再包含 “题目槽位/参考素材”。
- 真实素材复测观察剩余风险是否从内容泄漏/重复继续下降。
