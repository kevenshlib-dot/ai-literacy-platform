# AI素养评测平台 — 本地开发启动指南

## 项目路径

```
cd ~/remote-projects/ai-literacy-platform-git
```

---

## 启动顺序（共 4 步）

### 第 1 步：启动 Docker 容器（数据库 + 中间件）

```bash
docker compose up -d postgres elasticsearch minio milvus-standalone redis rabbitmq
```

包含以下服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 主数据库 |
| Elasticsearch | 9200 | 全文检索 |
| MinIO | 9000 / 9001 | 对象存储（文件上传） |
| Milvus | 19530 | 向量数据库 |
| RabbitMQ | 5672 / 15672 | 消息队列 |
| Redis | 6379 | 缓存 |

等待约 30 秒，确认容器健康：

```bash
docker compose ps
```

所有容器应显示 `Up ... (healthy)`。

---

### 第 2 步：启动 vLLM（AI 大模型）

在 GPU 服务器上启动 vLLM：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --port 8100 --host 0.0.0.0 \
  --max-model-len 32768 --gpu-memory-utilization 0.9
```

> 验证：`curl http://localhost:8100/v1/models`，能返回 JSON 即正常。
> 如果 vLLM 未启动，AI 出题/评分会自动降级为模板生成，不影响其他功能。

---

### 第 3 步：启动后端（FastAPI）

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 看到 `Application startup complete.` 表示启动成功。
> 后端地址：`http://localhost:8000`
> API 文档：`http://localhost:8000/docs`

---

### 第 4 步：启动前端（Vite + Vue）

**新开一个终端窗口：**

```bash
cd frontend && npm run dev
```

> 看到 `VITE ready` 表示启动成功。
> 前端地址：`http://localhost:3000`

---

## 快速验证

| 检查项 | 方法 |
|--------|------|
| 数据库 | `docker compose ps` 查看 postgres 状态 |
| 后端 API | 浏览器打开 `http://localhost:8000/docs` |
| 前端页面 | 浏览器打开 `http://localhost:3000` |
| LLM 服务 | `curl http://localhost:8100/v1/models` |

---

## 停止所有服务

```bash
# 停止前端：在前端终端按 Ctrl+C
# 停止后端：在后端终端按 Ctrl+C
# 停止 vLLM：Ctrl+C 或 pkill -f "vllm.entrypoints"

# 停止 Docker 容器
docker compose down
```

> 注意：`docker compose down` 只停止容器，数据卷保留不丢失。

---

## 端口汇总

| 服务 | 端口 |
|------|------|
| 前端 (Vue) | 3000 |
| 后端 (FastAPI) | 8000 |
| vLLM (LLM) | 8100 |
| PostgreSQL | 5432 |
| Elasticsearch | 9200 |
| MinIO 控制台 | 9001 |
| Milvus | 19530 |
| RabbitMQ 管理 | 15672 |
| Redis | 6379 |

---

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
