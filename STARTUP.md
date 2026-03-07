# AI素养评测平台 — 重启服务指南

## 项目路径

```
cd /Users/shlibkeven/Desktop/PRD/素养能力平台/ai-literacy-platform
```

---

## 启动顺序（共 4 步）

### 第 1 步：启动 Docker 容器（数据库 + 中间件）

```bash
docker compose up -d
```

包含以下服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 主数据库 |
| MinIO | 9000 / 9001 | 对象存储（文件上传） |
| Milvus | 19530 | 向量数据库 |
| etcd | 2379 | Milvus 依赖 |
| Milvus-MinIO | 9010 / 9011 | Milvus 内部存储 |

等待约 30 秒，确认容器健康：

```bash
docker ps
```

所有容器应显示 `Up ... (healthy)`。

---

### 第 2 步：启动 LM Studio（AI 大模型）

1. 打开应用：**LM Studio.app**
2. 加载模型：`qwen/qwen2.5-coder-14b`
3. 启动本地服务器，确保监听端口 **1234**

> 验证：浏览器访问 `http://localhost:1234/v1/models`，能返回 JSON 即正常。
> 如果 LM Studio 未启动，训练题目生成会自动降级为从题库随机抽题，不影响其他功能。

---

### 第 3 步：启动后端（FastAPI）

```bash
cd /Users/shlibkeven/Desktop/PRD/素养能力平台/ai-literacy-platform

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 看到 `Application startup complete.` 表示启动成功。
> 后端地址：`http://localhost:8000`
> API 文档：`http://localhost:8000/docs`

---

### 第 4 步：启动前端（Vite + Vue）

**新开一个终端窗口：**

```bash
cd /Users/shlibkeven/Desktop/PRD/素养能力平台/ai-literacy-platform/frontend

npm run dev
```

> 看到 `VITE ready` 表示启动成功。
> 前端地址：`http://localhost:3000`

---

## 快速验证

| 检查项 | 方法 |
|--------|------|
| 数据库 | `docker ps` 查看 postgres 状态 |
| 后端 API | 浏览器打开 `http://localhost:8000/docs` |
| 前端页面 | 浏览器打开 `http://localhost:3000` |
| LLM 服务 | 浏览器打开 `http://localhost:1234/v1/models` |

---

## 停止所有服务

```bash
# 停止前端：在前端终端按 Ctrl+C
# 停止后端：在后端终端按 Ctrl+C

# 停止 Docker 容器
cd /Users/shlibkeven/Desktop/PRD/素养能力平台/ai-literacy-platform
docker compose down
```

> 注意：`docker compose down` 只停止容器，数据卷保留不丢失。

---

## 端口汇总

| 服务 | 端口 |
|------|------|
| 前端 (Vue) | 3000 |
| 后端 (FastAPI) | 8000 |
| LM Studio (LLM) | 1234 |
| PostgreSQL | 5432 |
| MinIO 控制台 | 9001 |
| Milvus | 19530 |

---

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
