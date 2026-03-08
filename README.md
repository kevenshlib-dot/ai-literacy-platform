# AI素养评测平台

基于大语言模型的 AI 素养能力评测系统，支持智能出题、自动评分、五维诊断和情景互动等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy async + Pydantic |
| 前端 | Vue 3 + TypeScript + Vite + Ant Design Vue |
| LLM | vLLM serving Qwen3.5-35B-A3B (OpenAI 兼容 API) |
| 数据库 | PostgreSQL 16 + Elasticsearch 8 + Milvus 2.3 |
| 存储 | MinIO (对象存储) |
| 消息队列 | RabbitMQ + Redis |
| 部署 | Docker Compose + Nginx |

## 系统架构

```
用户浏览器 → Nginx (:80)
                ├─ /        → Vue 3 SPA 静态文件
                └─ /api/*   → FastAPI (:8000)
                                ├─ PostgreSQL (:5432)   主数据库
                                ├─ Elasticsearch (:9200) 全文检索
                                ├─ Milvus (:19530)      向量检索
                                ├─ MinIO (:9000)        文件存储
                                ├─ RabbitMQ (:5672)     异步任务
                                ├─ Redis (:6379)        缓存
                                └─ vLLM (:8100)         大模型推理
```

## 核心功能

### 题库管理
- **AI 智能出题**：基于素材内容或自由主题，LLM 生成单选/多选/判断/填空/简答题
- **预览审阅流程**：生成后预览 → 编辑/删减 → 确认保存，支持从已有题库补充题目
- **AI 质量检查**：五维度自动评分（清晰度、选项质量、正确性、匹配度、难度），10分制
- **批量审核**：支持批量通过/拒绝，Markdown 导入导出
- **Bloom 认知层次**：支持按记忆/理解/应用/分析/评价/创造分级出题

### 考试组卷
- 自然语言组卷（如"出20题中等难度的AI基础考试"）
- 自动组卷（按维度/难度/题型分布自动抽题）
- 手动组卷

### 评分系统
- 客观题自动评分
- 主观题 AI 评分（单评/多评共识）
- 五维诊断报告（AI基础知识/技术应用/伦理安全/批判思维/创新实践）
- 成绩排行、数据导出

### 情景互动
- SJT 情景判断测试
- 多轮对话式评估
- 动态难度调节

### 素材管理
- 支持 PDF/DOCX/TXT 上传
- 自动解析为知识单元
- 知识单元关联出题

## 项目结构

```
├── app/                        # 后端代码
│   ├── main.py                 # FastAPI 入口
│   ├── core/config.py          # 配置（环境变量）
│   ├── models/                 # SQLAlchemy 模型
│   ├── schemas/                # Pydantic 数据模型
│   ├── api/v1/endpoints/       # API 端点 (14 模块)
│   ├── services/               # 业务逻辑层
│   └── agents/                 # 8 个 AI Agent
│       ├── question_agent.py   # 题目生成
│       ├── scoring_agent.py    # 评分（单评/多评）
│       ├── review_agent.py     # 质量审核
│       ├── interactive_agent.py# 情景互动
│       ├── annotation_agent.py # 自动标注
│       ├── intent_agent.py     # 意图解析
│       └── indicator_agents.py # 指标分析
├── frontend/                   # 前端代码
│   ├── src/views/              # 页面组件
│   │   ├── Dashboard.vue       # 仪表盘
│   │   ├── Questions.vue       # 题目管理
│   │   ├── Materials.vue       # 素材管理
│   │   └── Scores.vue          # 成绩管理
│   └── Dockerfile              # 前端构建 (Nginx)
├── docker-compose.yml          # Docker 编排
├── docker-compose.webui.yml    # Open WebUI（LLM Chat 调试界面）
├── Dockerfile                  # 后端构建
├── nginx.conf                  # Nginx 反向代理配置
├── requirements.txt            # Python 依赖
├── alembic/                    # 数据库迁移
├── DEPLOY.md                   # 客户部署指南
└── STARTUP.md                  # 本地开发指南
```

## 快速开始

### 环境要求

- Docker 24+ & Docker Compose v2+
- Node.js 18+ & npm 9+
- Python 3.11+
- GPU 服务器（运行 vLLM，推荐 16GB+ 显存）

### 本地开发

```bash
# 1. 启动基础服务
docker compose up -d postgres elasticsearch minio milvus-standalone redis rabbitmq

# 2. 安装后端依赖并启动
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 启动前端
cd frontend && npm install && npm run dev
```

### 生产部署 (Docker Compose)

```bash
# 1. 配置环境变量
cp .env .env.production
vi .env.production  # 修改密钥、密码、LLM 配置

# 2. 构建前端
cd frontend && npm install && npm run build && cd ..

# 3. 启动所有服务
docker compose up -d --build
```

详细部署说明见 [DEPLOY.md](DEPLOY.md)。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEBUG` | `true` | 生产环境设为 `false` |
| `SECRET_KEY` | `change-this` | 应用密钥，生产必须修改 |
| `JWT_SECRET_KEY` | `change-this` | JWT 密钥，生产必须修改 |
| `POSTGRES_PASSWORD` | `ai_literacy_pass` | 数据库密码 |
| `LLM_API_KEY` | `token-not-needed` | LLM API Key（本地 vLLM 不需要） |
| `LLM_BASE_URL` | `http://localhost:8100/v1` | LLM 服务地址 |
| `LLM_MODEL` | `Qwen/Qwen3.5-35B-A3B` | 模型名称 |

完整配置见 `app/core/config.py`。

## LLM 配置

### 方案 A：本地 vLLM（推荐，当前使用）

```bash
# 在 GPU 服务器上启动 vLLM
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --port 8100 \
  --host 0.0.0.0 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9
```

### 方案 B：云 API

```ini
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

> LLM 不可用时，题目生成自动降级为模板生成，其他功能不受影响。

## Open WebUI（可选）

提供 LLM Chat 界面，方便直接与大模型对话调试，独立于主平台：

```bash
make webui-up     # 启动，访问 http://<服务器IP>:3100
make webui-down   # 停止
make webui-logs   # 查看日志
```

## API 文档

启动后端后访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |

> 首次部署后请立即修改默认密码。

## 相关文档

- [客户部署指南](DEPLOY.md) — 全新服务器部署步骤
- [服务器迁移重启指南](SERVER_RESTART.md) — 服务器搬迁后重新建立服务
- [本地开发指南](STARTUP.md) — 开发环境配置
- [系统管理员手册](AI素养评测平台_系统管理员手册.md) — 详细运维手册
