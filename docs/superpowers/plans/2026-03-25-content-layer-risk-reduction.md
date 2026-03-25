# Content-Layer Risk Reduction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan.

**Goal:** 将真实素材预览中的主要风险从“生成后整批发现”前移到“单题/规划阶段发现”，减少素材元信息泄漏和批内知识点重复。

## Chunk 1: 单题前置内容校验

### Task 1: 扩展 `_validate_and_fix_question`

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_validation_rules.py`

- [ ] 新增 prompt 标记泄漏检测 helper
- [ ] 在单题校验中前置拦截素材元信息、prompt 泄漏、乱码
- [ ] 补回归测试

## Chunk 2: planner 轻量去重回退

### Task 2: 给 batch planner 结果增加重复知识点回退

**Files:**
- Modify: `app/agents/question_agent.py`
- Test: `tests/test_question_generation_compare.py`

- [ ] 给 question plan 增加签名归一化
- [ ] 重复时优先回退到 deterministic fallback plan
- [ ] 补回归测试

## Chunk 3: prompt 与素材拼接去提示词化

### Task 3: 调整 prompt 约束和 generator 槽位标记

**Files:**
- Modify: `app/agents/question_agent.py`
- Modify: `app/services/question_service.py`
- Test: `tests/test_questions.py`

- [ ] 补充 batch planner / question plan 的内容层约束
- [ ] 将批量 generator 的槽位标记替换为中性格式
- [ ] 补回归测试

## Chunk 4: 定向验证

### Task 4: 运行定向测试

**Files:**
- Test: `tests/test_question_validation_rules.py`
- Test: `tests/test_question_generation_compare.py`
- Test: `tests/test_questions.py`

- [ ] 运行 py_compile
- [ ] 运行内容层相关 pytest 子集
- [ ] 记录结果并判断是否需要真实素材复测
