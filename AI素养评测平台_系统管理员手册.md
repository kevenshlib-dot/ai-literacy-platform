# AI素养评测培训平台 — 系统管理员手册

> 版本：v0.1.0 | 更新日期：2026-03-08 | 适用角色：系统管理员

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统架构与服务组件](#2-系统架构与服务组件)
3. [vLLM 大模型服务部署](#3-vllm-大模型服务部署)
4. [大模型调用与切换](#4-大模型调用与切换)
5. [系统内置提示词一览](#5-系统内置提示词一览)
6. [可自定义提示词的入口](#6-可自定义提示词的入口)
7. [平台部署与启动](#7-平台部署与启动)
8. [系统管理操作指南](#8-系统管理操作指南)
9. [服务端口与访问地址](#9-服务端口与访问地址)
10. [日常运维与故障排查](#10-日常运维与故障排查)
11. [附录](#附录)

---

## 1. 系统概述

AI素养评测培训平台是一套面向企业和教育机构的AI素养评测与培训系统。平台围绕**五大AI素养维度**进行评测：

| 维度 | 说明 |
|------|------|
| AI基础知识 | 机器学习原理、深度学习、算法基础、数据处理 |
| AI技术应用 | NLP、计算机视觉、推荐系统、大语言模型、AIGC |
| AI伦理安全 | 隐私保护、算法偏见、数据安全、负责任AI |
| AI批判思维 | 信息辨别、AI局限性认知、证据评估、逻辑推理 |
| AI创新实践 | 提示工程、AI工具使用、工作流自动化、方案设计 |

### 1.1 核心功能模块

- **智能题库管理**：AI自动出题、多维度质量审核、题目校准与去重
- **智能组卷与考试**：自然语言组卷、自动组卷、在线考试、实时自动保存
- **智能评分**：客观题自动评分、主观题AI评分、多模型评委团评分（防偏见）
- **情境化评测**：多轮对话式情境判断测试（SJT）
- **学习闭环**：五维诊断报告、自适应学习路径、薄弱点训练
- **运营管理**：用户管理、组织管理、成绩导出、月度报告

### 1.2 用户角色

| 角色 | 权限 |
|------|------|
| `admin`（管理员） | 全部功能，含用户管理、系统配置 |
| `organizer`（组织者） | 素材上传、出题、组卷、考试管理 |
| `reviewer`（审核员） | 题目审核、答卷批阅 |
| `examinee`（考生） | 参加考试、查看成绩、学习训练 |

---

## 2. 系统架构与服务组件

### 2.1 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    用户浏览器                         │
│                  http://服务器IP                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Nginx + Vue 3 前端 (:80)                │
└──────────────────────┬──────────────────────────────┘
                       │ /api/v1/*
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 后端 (:8000)                     │
│  ┌─────────────────────────────────────────────┐    │
│  │            8 个 AI 智能体 (Agent)              │    │
│  │  出题 │ 评分 │ 互动 │ 标注 │ 审核 │ 意图 │ 指标  │    │
│  └──────────────────┬──────────────────────────┘    │
└──────────────────────┬──────────────────────────────┘
                       │ OpenAI 兼容 API
┌──────────────────────▼──────────────────────────────┐
│         vLLM 大模型服务 (:8100)                       │
│   Qwen/Qwen3.5-35B-A3B (GPTQ-Int4, MoE)            │
└─────────────────────────────────────────────────────┘
```

### 2.2 基础设施服务

| 服务 | 镜像版本 | 用途 | 端口 |
|------|---------|------|------|
| PostgreSQL | 16-alpine | 关系型数据库 | 5432 |
| Elasticsearch | 8.12.0 | 全文搜索 | 9200 |
| Milvus | 2.3.7 | 向量数据库（语义检索/去重） | 19530 |
| MinIO | RELEASE.2024-01 | 对象存储（素材文件） | 9000/9001 |
| RabbitMQ | 3.13 | 消息队列（异步任务） | 5672/15672 |
| Redis | 7-alpine | 缓存 | 6379 |
| vLLM | 0.17.0 | 大模型推理服务 | 8100 |

---

## 3. vLLM 大模型服务部署

### 3.1 环境要求

- **操作系统**：Ubuntu 22.04+ / CentOS 8+ / 其他支持 CUDA 的 Linux
- **GPU**：NVIDIA GPU，显存 >= 24GB（推荐 128GB+ 统一内存，如 DGX Spark GB10）
- **CUDA**：12.0+
- **Python**：3.10+

> **当前部署硬件**：NVIDIA DGX Spark GB10（128GB 统一内存，CUDA 12.1 Blackwell 架构）

### 3.2 安装 vLLM

```bash
# 创建独立的 Python 虚拟环境
python3 -m venv ~/vllm-env

# 安装 vLLM
~/vllm-env/bin/pip install vllm
```

### 3.3 当前推荐模型

平台当前使用 **Qwen3.5-35B-A3B** 模型（GPTQ-Int4 量化版）：

| 属性 | 说明 |
|------|------|
| 模型全名 | `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` |
| 对外服务名 | `Qwen/Qwen3.5-35B-A3B` |
| 架构 | MoE（Mixture of Experts）— 总参数 35B，每次推理仅激活 3B |
| 量化 | GPTQ 4-bit（Marlin 后端） |
| 显存占用 | 约 21 GiB（128GB 显存仅占 16%） |
| KV Cache | 约 81 GiB 可用，支持约 106 万 tokens 缓存 |
| 最大上下文 | 262,144 tokens（256K） |
| 最大并发 | 约 16x（基于 256K 上下文） |

> **为什么选择 GPTQ-Int4 而非 FP8？** 当前 vLLM 0.17.0 的 CUTLASS FP8 内核（`cutlass_scaled_mm`）不兼容 NVIDIA Blackwell 架构（GB10, CUDA sm_121）。GPTQ-Int4 版本使用 Marlin 后端，完美兼容 Blackwell GPU，且显存占用更低。

### 3.4 下载并启动模型

#### 方式一：直接启动（自动下载模型）

```bash
# 设置 HuggingFace 镜像（国内服务器必须）
export HF_ENDPOINT=https://hf-mirror.com

# 启动 vLLM 服务（GPTQ-Int4 量化版）
nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8100 \
  --trust-remote-code \
  > ~/vllm-server.log 2>&1 &
```

首次启动会自动从 HuggingFace 镜像下载模型权重（约 23GB），后续启动直接使用缓存。

#### 方式二：先下载模型，再启动

```bash
# 安装 huggingface-cli
~/vllm-env/bin/pip install huggingface_hub

# 使用镜像下载模型到指定目录
export HF_ENDPOINT=https://hf-mirror.com
~/vllm-env/bin/huggingface-cli download \
  --resume-download Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --local-dir ~/models/Qwen3.5-35B-A3B-GPTQ-Int4

# 从本地路径启动
nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model ~/models/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8100 \
  --trust-remote-code \
  > ~/vllm-server.log 2>&1 &
```

### 3.5 验证 vLLM 服务

```bash
# 查看可用模型
curl http://localhost:8100/v1/models

# 测试对话能力
curl http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-35B-A3B",
    "messages": [{"role": "user", "content": "你好，请介绍一下人工智能"}],
    "max_tokens": 200
  }'
```

### 3.6 vLLM 常用启动参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `--model` | 模型名称或本地路径 | `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` |
| `--served-model-name` | 对外暴露的模型名称 | `Qwen/Qwen3.5-35B-A3B`（与 `.env` 中 `LLM_MODEL` 一致） |
| `--host` | 监听地址 | `0.0.0.0`（允许外部访问） |
| `--port` | 服务端口 | `8100` |
| `--trust-remote-code` | 信任远程代码 | Qwen3.5 模型必须 |
| `--tensor-parallel-size` | GPU 张量并行数 | 多卡时设为 GPU 数量 |
| `--max-model-len` | 最大序列长度 | 默认 262144（256K），可降低以节省显存 |
| `--gpu-memory-utilization` | GPU 显存利用率 | `0.9`（默认） |
| `--dtype` | 数据精度 | `auto`（GPTQ 模型自动使用 bfloat16） |
| `--enforce-eager` | 禁用 torch.compile | GPU 兼容性问题时使用 |

> **注意**：`--served-model-name` 非常重要。它决定了 API 对外暴露的模型名称，必须与 `.env` 中的 `LLM_MODEL` 值一致，否则平台无法正确调用模型。

### 3.7 设置 vLLM 开机自启（systemd）

创建服务文件 `/etc/systemd/system/vllm.service`：

```ini
[Unit]
Description=vLLM OpenAI-compatible API Server
After=network.target

[Service]
Type=simple
User=dell
Environment="HF_ENDPOINT=https://hf-mirror.com"
ExecStart=/home/dell/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8100 \
  --trust-remote-code
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm
sudo systemctl start vllm

# 查看状态
sudo systemctl status vllm

# 查看日志
journalctl -u vllm -f
```

---

## 4. 大模型调用与切换

### 4.1 配置文件说明

平台通过 3 个环境变量控制大模型连接，定义在 `.env` 或 `.env.production` 中：

| 变量 | 说明 | 当前值 |
|------|------|--------|
| `LLM_API_KEY` | API 密钥 | `token-not-needed`（本地 vLLM 不需要） |
| `LLM_BASE_URL` | API 地址 | `http://localhost:8100/v1` |
| `LLM_MODEL` | 模型标识 | `Qwen/Qwen3.5-35B-A3B` |

配置文件位置：

| 文件 | 用途 |
|------|------|
| `.env` | 开发环境配置 |
| `.env.production` | 生产环境配置（Docker 部署使用） |
| `app/core/config.py` | 默认值定义（.env 未设置时的降级值） |

### 4.2 切换大模型的方法

#### 场景一：切换 vLLM 加载的模型

1. 停止当前 vLLM 服务：
   ```bash
   pkill -f "vllm.entrypoints.openai.api_server"
   ```

2. 用新模型启动 vLLM：
   ```bash
   export HF_ENDPOINT=https://hf-mirror.com
   nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
     --model <新模型HF名称> \
     --served-model-name <对外服务名> \
     --host 0.0.0.0 --port 8100 \
     --trust-remote-code \
     > ~/vllm-server.log 2>&1 &
   ```

3. 更新 `.env` 中的 `LLM_MODEL`（必须与 `--served-model-name` 一致）：
   ```
   LLM_MODEL=<对外服务名>
   ```

4. 重启后端服务：
   ```bash
   docker compose restart app
   ```

#### 场景二：切换到云端 API（如 DeepSeek、OpenAI）

修改 `.env` 或 `.env.production`：

```bash
# DeepSeek API
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# OpenAI API
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# 其他 OpenAI 兼容 API（如硅基流动、智谱 AI）
LLM_API_KEY=你的API密钥
LLM_BASE_URL=https://api.provider.com/v1
LLM_MODEL=provider-model-name
```

重启后端生效：`docker compose restart app`

#### 场景三：切换回本地 vLLM

```bash
LLM_API_KEY=token-not-needed
LLM_BASE_URL=http://localhost:8100/v1
LLM_MODEL=Qwen/Qwen3.5-35B-A3B
```

> **注意**：Docker 容器内访问宿主机上的 vLLM 时，`.env.production` 中应使用 `http://host.docker.internal:8100/v1`，而非 `localhost`。

### 4.3 推荐模型列表

#### 本地部署模型（vLLM）

| 模型 | 架构 | 显存需求 | 中文能力 | 推荐场景 |
|------|------|---------|---------|---------|
| **Qwen/Qwen3.5-35B-A3B-GPTQ-Int4** | MoE 35B/3B活跃 | 21GB | 优秀 | ⭐ **当前使用**，Blackwell GPU 兼容 |
| Qwen/Qwen3.5-35B-A3B | MoE 35B/3B活跃 | 70GB | 优秀 | BF16 全精度版（显存充足时） |
| Qwen/Qwen2.5-7B-Instruct | Dense 7B | 16GB | 优秀 | 轻量部署，入门选择 |
| Qwen/Qwen2.5-14B-Instruct | Dense 14B | 32GB | 优秀 | 中等质量需求 |
| Qwen/Qwen2.5-72B-Instruct-AWQ | Dense 72B | 48GB | 优秀 | 高质量（AWQ 量化） |
| deepseek-ai/DeepSeek-V2-Lite-Chat | MoE 16B | 32GB | 优秀 | 推理能力强 |

> **MoE（Mixture of Experts）架构说明**：Qwen3.5-35B-A3B 总参数 35B，但每次推理仅激活 3B 参数，实现了"大模型质量 + 小模型速度"的最佳平衡。在 DGX Spark GB10 上推理速度约 50 tok/s。

#### NVIDIA Blackwell GPU (GB10/GB200) 兼容性说明

| 量化格式 | vLLM 兼容性 | 使用内核 | 说明 |
|---------|------------|---------|------|
| GPTQ-Int4 | ✅ 兼容 | Marlin | **推荐**，当前部署使用 |
| BF16（无量化） | ✅ 兼容 | FlashAttention v2 | 显存占用大（约 70GB） |
| FP8 | ❌ 不兼容 | CUTLASS (cutlass_scaled_mm) | vLLM 0.17.0 不支持 sm_121 |
| AWQ | ✅ 兼容 | Marlin | 可作为备选方案 |

> **重要提示**：在 NVIDIA Blackwell 架构（如 DGX Spark GB10、GB200）上，请**避免使用 FP8 量化模型**，当前 vLLM 的 CUTLASS 内核尚未支持 sm_121 计算能力。待 vLLM 后续版本更新后可重新评估 FP8 兼容性。

#### 云端 API 模型

| 模型 | 提供商 | 说明 |
|------|--------|------|
| deepseek-chat | DeepSeek | 性价比高，中文优秀 |
| gpt-4o | OpenAI | 综合能力最强 |
| glm-4 | 智谱 AI | 国产大模型 |

### 4.4 智能降级机制

当大模型服务不可用时，系统自动降级为规则/模板模式：

| 功能 | LLM 可用时 | 降级模式 |
|------|-----------|---------|
| 出题 | AI 智能生成高质量多样化题目 | 基于模板生成（质量有限） |
| 评分 | AI 语义理解评分 | 关键词匹配 + 规则评分 |
| 互动问答 | 多轮情境对话 | 预设回复模板 |
| 审核 | AI 五维度质量评估 | 基础格式检查 |
| 标注 | AI 自动内容标注 | 关键词匹配分类 |
| 意图解析 | 自然语言理解组卷 | 返回错误提示 |

降级触发条件：
- `LLM_API_KEY` 为默认值 `your-api-key` 时直接降级
- API 调用超时（60 秒）或返回错误时降级
- 降级不影响平台其他功能正常使用

---

## 5. 系统内置提示词一览

平台共内置 **11 个系统提示词（System Prompt）**，分布在 8 个 AI 智能体中。以下列出每个提示词的用途、位置和核心内容。

### 5.1 出题智能体（question_agent.py）

**文件位置**：`app/agents/question_agent.py`，第 215-294 行

**角色定义**：资深AI素养评测出题专家，10年以上教育测评经验

**核心指令**：
- 布鲁姆认知目标分类法（Bloom's Taxonomy）精准应用
- 干扰项心理学（Distractor Psychology）设计高质量干扰项
- 情境丰富性：优先使用具体场景包裹知识点
- 10种题目风格混合使用：直接知识型、情景应用型、案例分析型、对比辨析型、问题解决型、因果推理型、伦理困境型、评价判断型、趋势预测型、实践操作型
- 5 级难度校准（入门/简单/中等/困难/专家）
- 正确答案位置分散要求

**输出格式**：JSON 数组，每道题包含 `question_type`、`stem`、`options`、`correct_answer`、`explanation`、`knowledge_tags`、`dimension`

### 5.2 评分智能体（scoring_agent.py）

**文件位置**：`app/agents/scoring_agent.py`

#### 5.2.1 单模型评分提示词（第 16-34 行）

**角色定义**：专业AI素养评测评分专家

**评分规则**：
- 根据参考答案覆盖程度给分
- 关键概念必须准确
- 表述清晰、逻辑连贯可加分
- 存在明显错误应扣分

**输出格式**：`{"earned_ratio": 0.0-1.0, "feedback": "评分反馈"}`

#### 5.2.2 多模型评委团提示词（第 157-185 行）

**角色定义**：多角度独立评分专家

**防偏见机制**：
- 不因回答长度给额外分数
- 不因礼貌/讨好语言加分
- 只关注内容准确性、完整性和逻辑性
- 位置交换策略（先读参考答案/先读学生作答/同时对比）

**评分维度**：
- `accuracy`（准确性）：概念是否正确
- `completeness`（完整性）：是否覆盖要点
- `logic`（逻辑性）：论述是否有条理
- `expression`（表达性）：语言是否清晰

**输出格式**：四维度分数 + overall_ratio + feedback

### 5.3 互动问答智能体（interactive_agent.py）

**文件位置**：`app/agents/interactive_agent.py`

#### 5.3.1 情境对话提示词（第 17-57 行）

**角色定义**：AI素养情境评测专家，主持情境判断测试（SJT）

**动态参数**（由系统注入）：
- `{role_description}`：角色描述（如"AI产品经理"）
- `{scenario}`：场景背景
- `{dimension}`：评估维度
- `{difficulty}`：难度等级 1-5

**评估三维度**：
- `prompt_engineering`：提示工程能力
- `critical_thinking`：批判性思维
- `ethical_decision`：伦理决策

**输出格式**：回复内容 + 三维度评分 + 难度调整建议 + 是否结束

#### 5.3.2 会话总结提示词（第 60-82 行）

根据多轮对话记录生成最终评估摘要，包含总分、维度评分、关键决策点、优势、不足、建议。

### 5.4 标注智能体（annotation_agent.py）

**文件位置**：`app/agents/annotation_agent.py`，第 16-33 行

**功能**：分析教学材料内容，自动标注维度、难度、知识点、摘要、标签

**输出格式**：`{"dimension": "...", "difficulty": 1-5, "knowledge_points": [...], "summary": "...", "tags": [...]}`

### 5.5 审核智能体（review_agent.py）

**文件位置**：`app/agents/review_agent.py`，第 20-46 行

**五维度审核标准**：

| 维度 | 评分范围 | 审核内容 |
|------|---------|---------|
| stem_clarity（题干清晰度） | 1-5分 | 表述是否清晰、无歧义 |
| option_quality（选项质量） | 1-5分 | 干扰项是否合理 |
| answer_correctness（答案正确性） | 1-5分 | 正确答案是否确实正确 |
| knowledge_alignment（知识对齐） | 1-5分 | 与标注维度是否一致 |
| difficulty_calibration（难度校准） | 1-5分 | 难度标注是否匹配 |

**审核决策**：
- `approve`（通过）：综合评分 >= 3.5
- `revise`（修订）：综合评分 2.5-3.5
- `reject`（拒绝）：综合评分 < 2.5

### 5.6 意图解析智能体（intent_agent.py）

**文件位置**：`app/agents/intent_agent.py`，第 42-70 行

**功能**：将自然语言描述解析为组卷参数

**示例输入**：*"出一套20道的AI入门测试，包含15道单选和5道判断，限时30分钟"*

**输出格式**：`{"title": "...", "total_questions": 20, "difficulty": 1, "time_limit_minutes": 30, "type_distribution": {"single_choice": 15, "true_false": 5}, ...}`

### 5.7 指标体系智能体（indicator_agents.py）

**文件位置**：`app/agents/indicator_agents.py`

包含 3 个子智能体：

| 智能体 | 行号 | 功能 | temperature |
|--------|------|------|-------------|
| 研究员 | 37-59 | 分析AI发展趋势 | 0.7 |
| 顾问 | 89-107 | 提出评测指标更新建议 | 0.5 |
| 红队审核员 | 136-158 | 审查指标提案的可行性 | 0.3 |

---

## 6. 可自定义提示词的入口

系统提供了多个入口允许管理员和使用者输入自定义提示词，以影响AI的输出。

### 6.1 题目生成 — 自定义出题要求

**API 入口**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/questions/generate` | POST | 基于知识单元生成 |
| `/api/v1/questions/generate/material/{id}` | POST | 基于素材批量生成 |
| `/api/v1/questions/generate/free` | POST | 自由生成（必须提供 custom_prompt） |
| `/api/v1/questions/generate/bank/{id}` | POST | 构建题库 |

**自定义提示词参数**：`custom_prompt`（字符串）

**作用方式**：系统将 `custom_prompt` 作为 `【额外要求】` 追加到出题指令末尾

**示例请求**：

```json
{
  "content": "关于大语言模型的知识内容...",
  "question_types": ["single_choice", "multiple_choice"],
  "count": 5,
  "difficulty": 3,
  "bloom_level": "apply",
  "custom_prompt": "请侧重考查提示工程（Prompt Engineering）方面的知识，题目场景以办公自动化为主，避免涉及编程代码"
}
```

**可控参数一览**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `question_types` | 列表 | `single_choice`, `multiple_choice`, `true_false`, `fill_blank`, `short_answer` |
| `count` | 整数 | 生成题目数量 |
| `difficulty` | 1-5 | 难度等级 |
| `bloom_level` | 字符串 | 布鲁姆认知层次：`remember`/`understand`/`apply`/`analyze`/`evaluate`/`create` |
| `custom_prompt` | 字符串 | **自定义提示词**（追加到系统提示词后） |

### 6.2 主观题评分 — 自定义评分标准（Rubric）

**API 入口**：`POST /api/v1/scores/grade/{sheet_id}`

**自定义参数**：评分时可传入 `rubric` 字典作为自定义评分标准

**作用方式**：系统将 rubric 插入评分提示词中作为 `评分标准（Rubric）`

**示例**：

```json
{
  "rubric": {
    "概念准确性": "准确使用AI相关术语，定义无误（40%）",
    "论述完整性": "覆盖所有要求的知识点（30%）",
    "实例运用": "能举出恰当的实际案例（20%）",
    "表达规范": "语言清晰、逻辑连贯（10%）"
  }
}
```

### 6.3 多模型评委团评分

**API 入口**：`POST /api/v1/scores/panel-score`

**可控参数**：

| 参数 | 说明 |
|------|------|
| `num_evaluators` | 评委数量（2-5，默认 3） |
| `rubric` | 自定义评分标准字典 |

**工作原理**：系统使用同一个 LLM 模型模拟多个独立评委，通过**位置交换策略**（改变参考答案和学生作答的阅读顺序）消除位置偏见，最终取中位数得分。

### 6.4 互动问答 — 场景与角色定义

**API 入口**：`POST /api/v1/interactive`

**自定义参数**：

| 参数 | 说明 | 示例 |
|------|------|------|
| `scenario` | 场景描述 | "你是一家初创公司的CTO，正在考虑是否在产品中引入AI功能" |
| `role_description` | AI扮演的角色 | "资深AI产品顾问" |
| `dimension` | 评估维度 | "AI技术应用" |
| `difficulty` | 初始难度 | 3 |

这些参数会被注入到情境对话的系统提示词模板中。

### 6.5 自然语言组卷

**API 入口**：`POST /api/v1/exams/intent/assemble`

**自定义参数**：`description`（自然语言描述）

**示例**：

```json
{
  "description": "为新入职的产品经理设计一套AI素养评测，20道题，以应用和伦理为重点，难度中等偏上，时间30分钟"
}
```

系统通过意图解析智能体将自然语言转化为结构化组卷参数并自动组卷。

---

## 7. 平台部署与启动

### 7.1 前置条件

- Docker 和 Docker Compose 已安装
- vLLM 服务已启动（参见第 3 章）
- GPU 驱动已正确安装

### 7.2 一键部署

```bash
cd ~/ai-literacy-platform

# 检查/编辑生产配置（必须修改标注为 [必改] 的项目）
vim .env.production

# 运行部署脚本
chmod +x deploy.sh
./deploy.sh
```

部署脚本自动完成：
1. 检查 Docker 环境
2. 检查 vLLM 大模型服务是否就绪
3. 验证配置文件，自动生成安全密钥
4. 构建 Docker 镜像
5. 启动所有服务
6. 等待就绪并输出访问地址

### 7.3 手动部署

```bash
# 构建镜像
docker compose build

# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f app

# 运行数据库迁移
docker compose exec app alembic upgrade head
```

### 7.4 生产环境配置要点

`.env.production` 中**必须修改**的配置项：

| 配置项 | 说明 |
|--------|------|
| `SECRET_KEY` | 应用密钥（使用 `openssl rand -hex 32` 生成） |
| `JWT_SECRET_KEY` | JWT 密钥（使用 `openssl rand -hex 32` 生成） |
| `POSTGRES_PASSWORD` | 数据库密码（建议强密码） |
| `LLM_BASE_URL` | Docker 内使用 `http://host.docker.internal:8100/v1` |

---

## 8. 系统管理操作指南

### 8.1 用户管理

| 操作 | API | 说明 |
|------|-----|------|
| 创建用户 | `POST /api/v1/users` | 指定 username, email, password, role |
| 批量导入 | `POST /api/v1/users/batch-import` | 上传 Excel/CSV 文件 |
| 重置密码 | `POST /api/v1/users/{id}/reset-password` | 管理员重置用户密码 |
| 停用用户 | `DELETE /api/v1/users/{id}` | 软删除（可恢复） |
| 恢复用户 | `POST /api/v1/users/{id}/restore` | 恢复已删除用户 |
| 查看列表 | `GET /api/v1/users` | 支持 role/keyword/status 筛选 |

### 8.2 题库管理

| 操作 | API |
|------|-----|
| AI 批量出题 | `POST /api/v1/questions/generate/material/{id}` |
| AI 自由出题 | `POST /api/v1/questions/generate/free` |
| AI 质量检查 | `POST /api/v1/questions/{id}/ai-check` |
| 批量审核 | `POST /api/v1/questions/batch/review` |
| 自动标记低质量题 | `POST /api/v1/questions/calibration/auto-flag` |
| 查找重复题 | `GET /api/v1/questions/calibration/similar` |
| 全局质量报告 | `GET /api/v1/questions/analysis/report` |
| 导出题库 | `POST /api/v1/questions/batch/export-md` |
| 导入题库 | `POST /api/v1/questions/batch/import-md` |

### 8.3 考试管理

| 操作 | API |
|------|-----|
| 创建考试 | `POST /api/v1/exams` |
| 自然语言组卷 | `POST /api/v1/exams/intent/assemble` |
| 智能自动组卷 | `POST /api/v1/exams/{id}/assemble/auto` |
| 发布考试 | `POST /api/v1/exams/{id}/publish` |
| 关闭考试 | `POST /api/v1/exams/{id}/close` |
| 考试数据分析 | `GET /api/v1/exams/{id}/analysis` |

### 8.4 成绩管理

| 操作 | API |
|------|-----|
| 查看所有成绩 | `GET /api/v1/scores/all` |
| 导出成绩 Excel | `POST /api/v1/scores/export` |
| 批阅主观题 | `POST /api/v1/scores/grade/{sheet_id}` |
| 评委团评分 | `POST /api/v1/scores/panel-score` |
| 五维诊断报告 | `GET /api/v1/scores/{id}/diagnostic` |
| 排行榜 | `GET /api/v1/scores/leaderboard` |

---

## 9. 服务端口与访问地址

### 9.1 端口一览

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | Nginx + 前端 | 平台访问入口 |
| 8000 | FastAPI 后端 | API 接口 + Swagger 文档 |
| 8100 | vLLM | 大模型推理服务 |
| 5432 | PostgreSQL | 数据库 |
| 9200 | Elasticsearch | 全文搜索 |
| 19530 | Milvus | 向量数据库 |
| 9000 | MinIO API | 对象存储 |
| 9001 | MinIO Console | 对象存储管理界面 |
| 5672 | RabbitMQ | 消息队列 |
| 15672 | RabbitMQ Management | 消息队列管理界面 |
| 6379 | Redis | 缓存 |

### 9.2 常用访问地址

| 用途 | 地址 |
|------|------|
| 平台首页 | `http://<服务器IP>` |
| API 文档 (Swagger) | `http://<服务器IP>:8000/docs` |
| vLLM 模型列表 | `http://<服务器IP>:8100/v1/models` |
| MinIO 管理 | `http://<服务器IP>:9001`（minioadmin/minioadmin） |
| RabbitMQ 管理 | `http://<服务器IP>:15672`（guest/guest） |

---

## 10. 日常运维与故障排查

### 10.1 常用运维命令

```bash
# 查看所有服务状态
docker compose ps

# 查看后端日志
docker compose logs -f app

# 重启后端（配置变更后）
docker compose restart app

# 重启所有服务
docker compose restart

# 停止所有服务
docker compose down

# 停止并清除数据卷（⚠️ 数据全部丢失）
docker compose down -v
```

### 10.2 vLLM 运维

```bash
# 查看 vLLM 日志
tail -f ~/vllm-server.log

# 检查 vLLM 进程
ps aux | grep vllm

# 查看 GPU 使用情况
nvidia-smi

# 停止 vLLM
pkill -f "vllm.entrypoints.openai.api_server"

# 重启 vLLM（当前模型：Qwen3.5-35B-A3B GPTQ-Int4）
export HF_ENDPOINT=https://hf-mirror.com
nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 --port 8100 \
  --trust-remote-code \
  > ~/vllm-server.log 2>&1 &

# 查看 vLLM 当前加载的模型
curl -s http://localhost:8100/v1/models | python3 -m json.tool
```

### 10.3 常见问题排查

#### Q1：AI 出题/评分返回模板化结果（质量不佳）

**原因**：大模型服务不可用，系统自动降级为模板模式

**排查步骤**：
1. 检查 vLLM 是否运行：`curl http://localhost:8100/v1/models`
2. 检查后端日志：`docker compose logs app | grep LLM`
3. 确认 `.env.production` 中 `LLM_BASE_URL` 配置正确
4. Docker 内检查：`docker compose exec app curl http://host.docker.internal:8100/v1/models`

#### Q2：vLLM 启动后 GPU 内存不足 (OOM)

**解决方案**：
```bash
# 方案1：降低显存利用率
--gpu-memory-utilization 0.7

# 方案2：减小最大序列长度（大幅节省 KV Cache 显存）
--max-model-len 4096

# 方案3：使用 GPTQ-Int4 量化模型（当前已使用，仅 21GB）
--model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4

# 方案4：使用更小的模型
--model Qwen/Qwen2.5-7B-Instruct
```

> **注意**：在 Blackwell GPU (GB10) 上不要使用 FP8 量化模型，会因 CUTLASS 内核不兼容而启动失败。请使用 GPTQ-Int4 或 AWQ 量化版。

#### Q3：Docker 容器无法连接 vLLM

**原因**：`docker-compose.yml` 中需配置 `extra_hosts`

确认以下配置存在：
```yaml
app:
  extra_hosts:
    - "host.docker.internal:host-gateway"
  environment:
    - LLM_BASE_URL=http://host.docker.internal:8100/v1
```

#### Q4：模型下载超时或失败

```bash
# 设置 HuggingFace 镜像（国内必须）
export HF_ENDPOINT=https://hf-mirror.com

# 使用 huggingface-cli 先下载模型（支持断点续传）
~/vllm-env/bin/huggingface-cli download --resume-download Qwen/Qwen3.5-35B-A3B-GPTQ-Int4

# 检查下载进度
du -sh ~/.cache/huggingface/hub/models--Qwen--Qwen3.5-35B-A3B-GPTQ-Int4/
find ~/.cache/huggingface/hub/models--Qwen--Qwen3.5-35B-A3B-GPTQ-Int4/ -name "*.incomplete" | wc -l

# 清理不完整的下载（需要重新下载时）
find ~/.cache/huggingface/hub/ -name "*.incomplete" -delete
```

#### Q5：如何确认大模型的实际调用效果

```bash
# 手动测试 vLLM 的出题能力
curl http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-35B-A3B",
    "messages": [
      {"role": "system", "content": "你是AI素养评测出题专家"},
      {"role": "user", "content": "请生成1道关于机器学习的单选题，输出JSON格式"}
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

> **注意**：Qwen3.5 模型默认启用"思考链"模式，会在回答前输出推理过程。平台的各 Agent 已经能正确处理此行为。

#### Q6：vLLM 启动时报 CUTLASS / cutlass_scaled_mm 错误

**原因**：FP8 量化模型在 Blackwell GPU (sm_121) 上不兼容

**解决方案**：
```bash
# 改用 GPTQ-Int4 量化版本（使用 Marlin 后端，兼容 Blackwell）
--model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4

# 或使用 BF16 全精度版本（需要更多显存）
--model Qwen/Qwen3.5-35B-A3B --dtype bfloat16 --enforce-eager
```

---

## 附录

### A. 各智能体 LLM 调用参数汇总

| 智能体 | 文件 | temperature | max_tokens | 用途 |
|--------|------|-------------|-----------|------|
| 出题 | question_agent.py | 0.7 | 4096 | 生成多样化题目 |
| 评分（单模型） | scoring_agent.py | 0.2 | 512 | 精确评分 |
| 评分（评委团） | scoring_agent.py | 0.3 | 512 | 多角度评分 |
| 互动对话 | interactive_agent.py | 0.7 | 800 | 情境对话 |
| 互动总结 | interactive_agent.py | 0.3 | 800 | 生成摘要 |
| 标注 | annotation_agent.py | 0.3 | 500 | 内容分析 |
| 审核 | review_agent.py | 0.3 | 1024 | 质量检查 |
| 意图解析 | intent_agent.py | 0.3 | 500 | 自然语言理解 |
| 研究员 | indicator_agents.py | 0.7 | 1000 | 趋势分析 |
| 顾问 | indicator_agents.py | 0.5 | 1000 | 指标建议 |
| 红队审核 | indicator_agents.py | 0.3 | 1000 | 提案审查 |

### B. 题型与布鲁姆层次对照

| 题型 | 适用布鲁姆层次 | 说明 |
|------|--------------|------|
| 单选题（single_choice） | 全部层次 | 最通用题型 |
| 多选题（multiple_choice） | 理解、分析、评价 | 考查综合判断 |
| 判断题（true_false） | 记忆、理解 | 概念辨析 |
| 填空题（fill_blank） | 记忆、理解 | 术语掌握 |
| 简答题（short_answer） | 理解、应用、分析 | 深度考查 |

### C. 五维度关键词映射

系统使用关键词匹配自动分类题目所属维度：

| 维度 | 部分关键词 |
|------|-----------|
| AI基础知识 | 机器学习、深度学习、神经网络、算法、Transformer、梯度下降、反向传播 |
| AI技术应用 | NLP、计算机视觉、语音识别、ChatGPT、大语言模型、AIGC、推荐系统 |
| AI伦理安全 | 隐私、偏见、公平、deepfake、数据保护、算法歧视、可解释性 |
| AI批判思维 | 批判、局限、评估、验证、信息素养、逻辑、谬误 |
| AI创新实践 | 提示工程、prompt、AI工具、微调、API、部署、自动化 |

### D. 数据库模型清单

| 模型 | 表名 | 说明 |
|------|------|------|
| User | users | 用户信息，含角色、软删除 |
| Material | materials | 教学素材文件 |
| KnowledgeUnit | knowledge_units | 素材提取的知识单元 |
| Question | questions | 题目，含状态流转 |
| Exam | exams | 考试/试卷 |
| ExamQuestion | exam_questions | 考试-题目关联 |
| AnswerSheet | answer_sheets | 答卷 |
| Answer | answers | 逐题作答记录 |
| Score | scores | 成绩，含维度分数 |
| InteractiveSession | interactive_sessions | 互动问答会话 |
| SandboxSession | sandbox_sessions | 沙盒练习 |
| LearningPath | learning_paths | 学习路径 |
| Report | reports | 运营报告 |

### E. 配置文件环境变量完整清单

```bash
# ── 应用配置 ──
APP_NAME=AI素养评测平台
APP_VERSION=0.1.0
DEBUG=false                    # 生产环境设为 false
SECRET_KEY=<随机字符串>         # [必改]
API_V1_PREFIX=/api/v1

# ── 数据库 ──
POSTGRES_HOST=postgres         # Docker 内为服务名
POSTGRES_PORT=5432
POSTGRES_USER=ai_literacy
POSTGRES_PASSWORD=<强密码>     # [建议改]
POSTGRES_DB=ai_literacy_db

# ── 搜索引擎 ──
ELASTICSEARCH_HOST=elasticsearch
ELASTICSEARCH_PORT=9200

# ── 向量数据库 ──
MILVUS_HOST=milvus-standalone
MILVUS_PORT=19530

# ── 对象存储 ──
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin    # [建议改]
MINIO_SECRET_KEY=minioadmin    # [建议改]
MINIO_BUCKET=ai-literacy

# ── 消息队列 ──
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest        # [建议改]

# ── 缓存 ──
REDIS_HOST=redis
REDIS_PORT=6379

# ── 大模型配置 ──
LLM_API_KEY=token-not-needed   # 本地 vLLM 不需要密钥
LLM_BASE_URL=http://host.docker.internal:8100/v1  # Docker 内访问宿主机
LLM_MODEL=Qwen/Qwen3.5-35B-A3B   # vLLM 中 --served-model-name 的值

# ── 认证 ──
JWT_SECRET_KEY=<随机字符串>     # [必改]
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```
