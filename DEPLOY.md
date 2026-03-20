# AI素养评测平台 — 客户部署指南

---

## 一、服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Ubuntu 20.04 / CentOS 8 | Ubuntu 22.04 LTS |
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 硬盘 | 50 GB SSD | 100 GB SSD |
| 网络 | 可访问内网 | 有公网 IP 或域名 |

需预装：
- Docker 24+、Docker Compose v2+
- Node.js 18+、npm 9+
- Python 3.10+、pip
- Git

---

## 二、部署架构

```
用户浏览器
    │
    ▼
┌─────────┐
│  Nginx  │  ← 端口 80/443，静态文件 + 反向代理
│  :80    │
└────┬────┘
     │  /api/*  代理到后端
     │  /       返回前端静态文件
     ▼
┌─────────┐     ┌──────────┐     ┌─────────────┐
│ FastAPI  │────▶│PostgreSQL│     │  LLM 服务    │
│  :8000   │     │  :5432   │     │ (DeepSeek    │
└─────────┘     └──────────┘     │  或本地部署)  │
     │                           └─────────────┘
     ├──▶ MinIO     (:9000)  对象存储
     ├──▶ Milvus    (:19530) 向量数据库
     └──▶ Redis     (:6379)  缓存
```

---

## 三、部署步骤

### 第 1 步：上传项目到服务器

在你的开发机上打包（排除不需要的文件）：

```bash
cd /Users/shlibkeven/Desktop/PRD/素养能力平台/

tar czf ai-literacy-platform.tar.gz \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.claude' \
  ai-literacy-platform/
```

上传到服务器：

```bash
scp ai-literacy-platform.tar.gz root@<服务器IP>:/opt/
```

在服务器上解压：

```bash
cd /opt
tar xzf ai-literacy-platform.tar.gz
cd ai-literacy-platform
```

---

### 第 2 步：配置生产环境变量

复制并编辑 `.env` 文件：

```bash
cp .env .env.bak
vi .env
```

**必须修改以下项**（带 ⚠️ 的为安全关键项）：

```ini
# 关闭调试
DEBUG=false

# ⚠️ 改为随机强密码（可用 openssl rand -hex 32 生成）
SECRET_KEY=<生成的随机密钥>
JWT_SECRET_KEY=<生成的另一个随机密钥>

# ⚠️ 修改数据库密码
POSTGRES_PASSWORD=<强密码>

# ⚠️ 修改 MinIO 密码
MINIO_ACCESS_KEY=<自定义用户名>
MINIO_SECRET_KEY=<强密码>

# LLM 配置（二选一）
# 方案A：使用 DeepSeek 云服务（推荐，无需 GPU）
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 方案B：使用本地 LLM（需 GPU 服务器）
# LLM_API_KEY=lm-studio
# LLM_BASE_URL=http://localhost:1234/v1
# LLM_MODEL=qwen/qwen2.5-coder-14b

# JWT 有效期（生产建议延长）
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=120
```

> ⚠️ **同时修改 `docker-compose.yml`** 中 PostgreSQL 和 MinIO 的密码，保持一致。

---

### 第 3 步：启动 Docker 基础服务

```bash
cd /opt/ai-literacy-platform

docker compose up -d
```

等待所有服务健康（约 1-2 分钟）：

```bash
# 持续查看状态，直到所有服务显示 (healthy)
docker compose ps
```

预期输出：

```
ai-literacy-postgres   Up (healthy)   0.0.0.0:5432->5432
ai-literacy-minio      Up (healthy)   0.0.0.0:9000-9001->9000-9001
ai-literacy-milvus     Up (healthy)   0.0.0.0:19530->19530
ai-literacy-etcd       Up (healthy)
...
```

---

### 第 4 步：初始化后端

```bash
cd /opt/ai-literacy-platform

# 安装 Python 依赖
pip3 install -r requirements.txt

# 初始化数据库表结构
alembic upgrade head

# 测试启动（前台运行，确认无报错）
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 看到 "Application startup complete." 后 Ctrl+C 停止
```

---

### 第 5 步：构建前端

```bash
cd /opt/ai-literacy-platform/frontend

# 安装依赖
npm install

# 修改 API 地址（生产模式）
# 创建 .env.production 文件
cat > .env.production << 'EOF'
VITE_API_BASE_URL=/api/v1
EOF

# 构建生产包
npm run build
```

构建完成后，静态文件在 `frontend/dist/` 目录下。

---

### 第 6 步：配置 Nginx

安装 Nginx：

```bash
apt install nginx -y   # Ubuntu
# 或
yum install nginx -y   # CentOS
```

创建配置文件：

```bash
cat > /etc/nginx/sites-available/ai-literacy << 'NGINX'
server {
    listen 80;
    server_name _;  # 改为实际域名或 IP

    # 前端静态文件
    root /opt/ai-literacy-platform/frontend/dist;
    index index.html;

    # 前端路由（Vue Router history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;  # LLM 调用可能较慢
        proxy_connect_timeout 60s;

        # 文件上传大小限制
        client_max_body_size 50M;
    }

    # Swagger 文档（可选，生产环境可注释掉）
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location /redoc {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
NGINX

# 启用配置
ln -sf /etc/nginx/sites-available/ai-literacy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试配置
nginx -t

# 启动 Nginx
systemctl enable nginx
systemctl restart nginx
```

---

### 第 7 步：后端设置为系统服务

```bash
cat > /etc/systemd/system/ai-literacy.service << 'EOF'
[Unit]
Description=AI Literacy Platform Backend
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-literacy-platform
Environment="PATH=/usr/local/bin:/usr/bin"
ExecStart=/usr/local/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动并设为开机自启
systemctl daemon-reload
systemctl enable ai-literacy
systemctl start ai-literacy

# 查看状态
systemctl status ai-literacy
```

---

## 四、验证部署

打开浏览器访问 `http://<服务器IP>`：

| 验证项 | 方法 | 预期结果 |
|--------|------|---------|
| 首页加载 | 访问 `http://<IP>` | 看到登录页面 |
| 登录 | 用 admin / admin123 登录 | 进入管理后台 |
| API 文档 | 访问 `http://<IP>/docs` | 看到 Swagger UI |
| 数据库 | 登录后查看数据 | 能看到考试/题目列表 |
| LLM 功能 | 题库建设 → AI 生成题目 | 题目正常生成 |

---

## 五、LLM 服务部署方案

### 方案 A：DeepSeek 云 API（推荐）

- 无需 GPU，注册即用
- 在 `.env` 中配置 API Key 即可
- 费用低，按 token 计费
- 需要服务器能访问外网

### 方案 B：本地部署 LLM（离线/内网环境）

需要 GPU 服务器（至少 16GB 显存）：

```bash
# 安装 Ollama（推荐，最简单）
curl -fsSL https://ollama.com/install.sh | sh

# 下载模型
ollama pull qwen2.5:14b

# 启动服务（默认端口 11434）
ollama serve
```

`.env` 配置改为：

```ini
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:14b
```

> 如果客户没有 GPU 且不能联网，LLM 相关功能（AI 生成题目、主观题评分、训练题生成）会自动降级为数据库随机抽题。

---

## 六、安全加固清单

- [ ] 修改所有默认密码（数据库、MinIO、管理员账号）
- [ ] `.env` 中 `DEBUG=false`
- [ ] 生成强随机 `SECRET_KEY` 和 `JWT_SECRET_KEY`
- [ ] 生产环境关闭 Swagger（删除 Nginx 中 `/docs` 配置）
- [ ] 配置 HTTPS（`certbot --nginx` 自动申请 Let's Encrypt 证书）
- [ ] 配置防火墙，只开放 80/443 端口
- [ ] 限制 CORS（`app/main.py` 中 `allow_origins` 改为实际域名）
- [ ] 数据库定期备份

---

## 七、数据备份与恢复

### 备份

```bash
# 备份数据库
docker exec ai-literacy-postgres pg_dump -U ai_literacy ai_literacy_db > backup_$(date +%Y%m%d).sql

# 备份上传文件
docker cp ai-literacy-minio:/data ./minio_backup_$(date +%Y%m%d)
```

### 恢复

```bash
# 恢复数据库
cat backup_20260306.sql | docker exec -i ai-literacy-postgres psql -U ai_literacy ai_literacy_db
```

建议设置 crontab 每日自动备份：

```bash
crontab -e
# 添加以下行（每天凌晨 2 点备份）
0 2 * * * docker exec ai-literacy-postgres pg_dump -U ai_literacy ai_literacy_db > /opt/backups/db_$(date +\%Y\%m\%d).sql
```

也可以直接使用 `docker-compose.yml` 中新增的 `postgres-backup` 服务：

- 备份时间：每天凌晨 2 点
- 保留策略：按天保留 14 天，同时保留周/月级归档
- 备份目录：`./backups/postgres/`

启动后会自动生成备份，无需再单独配置宿主机 crontab。

---

## 八、常见问题

| 问题 | 排查 |
|------|------|
| 页面白屏 | 检查 `frontend/dist/` 是否存在，Nginx 配置是否正确 |
| 登录 401 | 检查后端是否启动：`systemctl status ai-literacy` |
| 数据库连不上 | `docker ps` 检查 postgres 容器；确认 `.env` 密码一致 |
| AI 功能不工作 | 检查 LLM 服务是否可达，查看后端日志 `journalctl -u ai-literacy -f` |
| 文件上传失败 | 检查 MinIO 容器状态，Nginx `client_max_body_size` 设置 |
| 前端路由 404 | 确认 Nginx `try_files $uri $uri/ /index.html` 配置 |

---

## 九、端口一览（仅供内部参考，对外只开放 80/443）

| 服务 | 端口 | 备注 |
|------|------|------|
| Nginx | 80 / 443 | 对外唯一入口 |
| FastAPI | 8000 | 仅 127.0.0.1 监听 |
| PostgreSQL | 5432 | Docker 内部 |
| MinIO | 9000 / 9001 | Docker 内部 |
| Milvus | 19530 | Docker 内部 |
| Redis | 6379 | Docker 内部 |
| LLM | 1234 / 11434 | 本地部署时 |

---

## 十、部署清单 Checklist

```
□ 服务器环境准备（Docker / Node / Python）
□ 项目文件上传解压
□ .env 生产配置（密码、密钥、LLM）
□ docker compose up -d（基础服务）
□ pip install + alembic upgrade head（后端初始化）
□ npm install + npm run build（前端构建）
□ Nginx 配置 + 启动
□ 后端 systemd 服务 + 启动
□ 登录验证 admin/admin123
□ 修改管理员默认密码
□ 安全加固（HTTPS / 防火墙 / 关闭调试）
□ 设置数据备份
```
