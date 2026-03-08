# 服务器迁移重启指南

本文档适用于将 DGX Spark 服务器搬到客户环境后，重新建立和启动所有服务。

---

## 前置条件

- **硬件**：NVIDIA DGX Spark GB10（或同等 GPU 服务器）
- **系统**：已安装 Docker、Docker Compose、Python 3.11+、Node.js 18+
- **项目路径**：`~/ai-literacy-platform/`
- **网络**：服务器需接入客户内网，确保客户端能访问服务器 80 端口

## 服务一览

| 服务 | 端口 | 启动方式 | 说明 |
|------|------|---------|------|
| vLLM | 8100 | 手动/systemd | 大模型推理（宿主机运行） |
| Docker 容器组 | 多端口 | docker compose | 数据库/中间件/后端/前端 |
| Nginx (容器内) | 80 | 随 docker compose | 对外唯一入口 |

## 启动步骤（共 3 步）

### 第 1 步：网络配置

1. 将服务器接入客户网络，获取 IP 地址：

```bash
ip addr show  # 或 hostname -I
# 记录分配到的 IP，例如 192.168.1.100
```

2. 确认客户端能 ping 通服务器：

```bash
# 在客户电脑上
ping 192.168.1.100
```

3. 如需修改防火墙，确保 80 端口开放：

```bash
sudo ufw allow 80/tcp    # Ubuntu
# 或
sudo firewall-cmd --add-port=80/tcp --permanent && sudo firewall-cmd --reload  # CentOS
```

---

### 第 2 步：启动 vLLM（大模型服务）

vLLM 运行在宿主机上（非 Docker），需先启动：

```bash
# 后台启动 vLLM
nohup python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --port 8100 \
  --host 0.0.0.0 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9 \
  > ~/vllm-server.log 2>&1 &
```

等待模型加载完成（约 1-2 分钟），验证：

```bash
curl http://localhost:8100/v1/models
# 应返回包含模型名称的 JSON
```

> **如果 vLLM 已配置为 systemd 服务**：
> ```bash
> sudo systemctl start vllm
> sudo systemctl status vllm
> ```

> **如果无法启动 vLLM**：AI 出题/评分功能会自动降级，不影响平台其他功能。

---

### 第 3 步：启动平台服务（Docker Compose）

```bash
cd ~/ai-literacy-platform

# 启动所有容器（后端、前端、数据库、中间件）
docker compose up -d
```

等待所有服务健康（约 1-2 分钟）：

```bash
docker compose ps
```

预期输出——所有容器显示 `Up (healthy)`：

```
ai-literacy-app           Up
ai-literacy-frontend      Up
ai-literacy-postgres      Up (healthy)
ai-literacy-elasticsearch Up (healthy)
ai-literacy-minio         Up (healthy)
ai-literacy-milvus        Up (healthy)
ai-literacy-rabbitmq      Up (healthy)
ai-literacy-redis         Up (healthy)
...
```

---

## 验证

在客户电脑的浏览器中访问 `http://<服务器IP>`：

| 检查项 | 操作 | 预期结果 |
|--------|------|---------|
| 页面加载 | 访问 `http://<IP>` | 显示登录页 |
| 登录 | admin / admin123 | 进入管理后台 |
| API 状态 | 访问 `http://<IP>/api/v1/health` | 返回 `"status": "healthy"` 和模型名 |
| LLM 功能 | 题库建设 → 生成题目 | 题目正常生成 |

---

## 停止服务

```bash
# 停止 Docker 容器（数据卷保留，不丢数据）
cd ~/ai-literacy-platform
docker compose down

# 停止 vLLM
pkill -f "vllm.entrypoints"
# 或
sudo systemctl stop vllm
```

---

## 完全重启（重启服务器后）

服务器断电或重启后，按以下顺序操作：

```bash
# 1. 启动 Docker 服务（通常开机自动启动）
sudo systemctl start docker

# 2. 启动 vLLM
nohup python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --port 8100 --host 0.0.0.0 \
  --max-model-len 32768 --gpu-memory-utilization 0.9 \
  > ~/vllm-server.log 2>&1 &

# 3. 等待 vLLM 加载完成
sleep 60 && curl http://localhost:8100/v1/models

# 4. 启动平台
cd ~/ai-literacy-platform && docker compose up -d

# 5. 等待并验证
sleep 90 && docker compose ps && curl http://localhost:8000/api/v1/health
```

---

## 常见问题

### 容器启动失败

```bash
# 查看具体错误
docker compose logs <服务名>
# 例如：docker compose logs app
```

| 症状 | 排查 |
|------|------|
| postgres 不健康 | 检查磁盘空间 `df -h`，数据卷是否完整 |
| app 容器退出 | `docker compose logs app`，通常是 `.env.production` 配置问题 |
| frontend 无法访问 | 检查 80 端口是否被占用 `ss -tlnp \| grep :80` |

### 网络问题

| 症状 | 排查 |
|------|------|
| 客户端无法访问 | 确认 IP、防火墙、网线/WiFi 连接 |
| API 调用 502 | 后端未启动，`docker compose ps` 检查 app 容器 |
| AI 功能超时 | vLLM 未启动或模型加载中，检查 `curl localhost:8100/v1/models` |

### vLLM 问题

```bash
# 查看 vLLM 日志
tail -50 ~/vllm-server.log

# 检查 GPU 状态
nvidia-smi

# 检查端口占用
ss -tlnp | grep 8100
```

| 症状 | 排查 |
|------|------|
| CUDA out of memory | 降低 `--gpu-memory-utilization` 到 0.85 |
| 模型找不到 | 确认模型文件在 `~/.cache/huggingface/` 中 |
| 端口被占用 | `kill $(lsof -t -i:8100)` 后重新启动 |

### 数据备份与恢复

```bash
# 备份数据库
docker exec ai-literacy-postgres pg_dump -U ai_literacy ai_literacy_db > backup_$(date +%Y%m%d).sql

# 恢复数据库
cat backup.sql | docker exec -i ai-literacy-postgres psql -U ai_literacy ai_literacy_db

# 备份上传文件
docker cp ai-literacy-minio:/data ./minio_backup
```

---

## 环境变量参考

关键配置在 `.env.production` 文件中，通常不需要修改：

```ini
DEBUG=false
SECRET_KEY=<已配置的密钥>
JWT_SECRET_KEY=<已配置的密钥>
LLM_API_KEY=token-not-needed
LLM_MODEL=Qwen/Qwen3.5-35B-A3B
# LLM_BASE_URL 由 docker-compose.yml 中 environment 覆盖为 http://localhost:8100/v1
```

如需更换 LLM 模型，修改以下两处：
1. vLLM 启动命令中的 `--model` 参数
2. `.env.production` 中的 `LLM_MODEL` 值

---

## 端口汇总

| 服务 | 端口 | 对外暴露 |
|------|------|---------|
| Nginx (前端) | 80 | 是（用户访问入口） |
| FastAPI (后端) | 8000 | 否（Nginx 反代） |
| vLLM | 8100 | 否（仅本机） |
| PostgreSQL | 5432 | 否 |
| Elasticsearch | 9200 | 否 |
| Milvus | 19530 | 否 |
| MinIO | 9000/9001 | 否 |
| RabbitMQ | 5672 | 否 |
| Redis | 6379 | 否 |
