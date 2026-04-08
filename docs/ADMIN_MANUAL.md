# AI素养评测平台 — 管理员手册

**适用版本**: v2.0.0
**更新日期**: 2026-04-08

---

## 目录

1. [部署架构](#1-部署架构)
2. [环境要求](#2-环境要求)
3. [首次部署（v2.0）](#3-首次部署v20)
4. [从 v1.0 升级到 v2.0](#4-从-v10-升级到-v20)
5. [版本回退](#5-版本回退)
6. [数据库管理](#6-数据库管理)
7. [系统配置管理](#7-系统配置管理)
8. [文件存储管理](#8-文件存储管理)
9. [日常运维](#9-日常运维)
10. [故障排查](#10-故障排查)

---

## 1. 部署架构

```
用户浏览器
    │
    ▼
┌─────────┐
│  Nginx  │  ← 端口 80/443，静态文件 + 反向代理
└────┬────┘
     │
     ├── /api/*  ──→  FastAPI (uvicorn :8000)
     ├── /minio/* ──→  MinIO   (:9000)
     └── /*       ──→  Vue SPA (dist/)

后端依赖:
  ├── PostgreSQL 15   (:5432)
  ├── Redis 7         (:6379)
  ├── MinIO           (:9000/:9001)
  └── vLLM / OpenAI兼容接口（大模型服务）
```

---

## 2. 环境要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Ubuntu 20.04 / CentOS 8 | Ubuntu 22.04 LTS |
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 硬盘 | 50 GB SSD | 100 GB SSD |
| Python | 3.10+ | 3.11+ |
| Node.js | 18+ | 20+ |
| Docker | 24+ | 最新稳定版 |

---

## 3. 首次部署（v2.0）

### 3.1 获取代码

```bash
git clone https://github.com/kevenshlib-dot/ai-literacy-platform.git
cd ai-literacy-platform

# 切换到推荐版本
git checkout v2.0.0
```

### 3.2 后端部署

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，配置数据库、Redis、MinIO、LLM 等参数

# 数据库迁移
alembic upgrade head

# 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.3 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 构建生产包
npm run build

# 产出在 dist/ 目录，配置 Nginx 指向此目录
```

### 3.4 Docker 部署（推荐）

```bash
# 使用 docker-compose 一键启动
docker-compose up -d
```

### 3.5 Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # MinIO 代理（如需要）
    location /minio/ {
        proxy_pass http://127.0.0.1:9000/;
    }
}
```

---

## 4. 从 v1.0 升级到 v2.0

### 4.1 升级前准备

```bash
# 1. 备份数据库
pg_dump -U postgres ai_literacy > backup_v1.0_$(date +%Y%m%d).sql

# 2. 备份当前代码
git stash  # 如有本地修改

# 3. 记录当前版本
git log --oneline -1
```

### 4.2 执行升级

```bash
# 拉取最新代码
git fetch origin

# 切换到 v2.0
git checkout v2.0.0

# 更新后端依赖
pip install -r requirements.txt

# 执行数据库迁移（增量迁移，不影响已有数据）
alembic upgrade head

# 重建前端
cd frontend
npm install
npm run build

# 重启服务
# 如使用 systemd:
sudo systemctl restart ai-literacy-backend
sudo systemctl restart nginx

# 如使用 Docker:
docker-compose up -d --build
```

### 4.3 升级验证

1. 访问平台首页，确认能正常登录
2. 检查题库管理页面数据完整
3. 进入试卷管理页面，确认新功能可用
4. 创建一张测试试卷，验证完整流程

### 4.4 数据兼容性说明

| 项目 | 说明 |
|------|------|
| 用户数据 | 完全兼容，无需处理 |
| 题库数据 | 完全兼容，无需处理 |
| 考试数据 | 完全兼容，exam 表新增 paper_id 字段（nullable） |
| 新增表 | papers、paper_sections、paper_questions、system_configs |

---

## 5. 版本回退

如需回退到 v1.0：

```bash
# 1. 切换代码
git checkout v1.0.0

# 2. 回退数据库迁移（回退到 v1.0 的最后一个迁移版本）
alembic downgrade <v1.0_last_migration_id>

# 3. 恢复依赖和重启服务
pip install -r requirements.txt
cd frontend && npm install && npm run build
# 重启服务...
```

> **注意**: 回退后 v2.0 新增的数据（试卷、系统配置等）将不可访问，但不会丢失。重新升级到 v2.0 后数据恢复。

---

## 6. 数据库管理

### 6.1 迁移命令

```bash
# 查看当前迁移版本
alembic current

# 查看迁移历史
alembic history

# 升级到最新
alembic upgrade head

# 回退一步
alembic downgrade -1
```

### 6.2 v2.0 新增数据表

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `papers` | 试卷主表 | id, title, status, total_score, created_by |
| `paper_sections` | 试卷大题 | id, paper_id, title, order_num, score_rule |
| `paper_questions` | 试卷题目 | id, paper_id, section_id, question_id, score |
| `system_configs` | 系统配置 | id, key, value, description |

### 6.3 数据备份建议

```bash
# 每日自动备份（添加到 crontab）
0 2 * * * pg_dump -U postgres ai_literacy | gzip > /backup/ai_literacy_$(date +\%Y\%m\%d).sql.gz

# 保留最近 30 天备份
find /backup -name "ai_literacy_*.sql.gz" -mtime +30 -delete
```

---

## 7. 系统配置管理

### 7.1 环境变量配置（.env）

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/ai_literacy

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ai-literacy

# LLM（基础配置）
LLM_API_BASE=http://localhost:8001/v1
LLM_API_KEY=your-api-key
LLM_MODEL_NAME=your-model-name
```

### 7.2 管理界面配置（v2.0 新增）

1. 登录系统后，左侧导航栏点击 **系统配置**
2. 可配置大模型相关参数：
   - API 地址
   - API 密钥
   - 模型名称
   - 温度、最大 token 等参数
3. **优先级规则**: 管理界面配置 > .env 环境变量配置
4. 修改后立即生效，无需重启服务

---

## 8. 文件存储管理

### 8.1 MinIO 管理

```bash
# MinIO 控制台
# 访问 http://your-server:9001

# 检查存储状态
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/ai-literacy
```

### 8.2 Word 文件临时存储

- 试卷 Word 导入时文件临时存储在 `storage/` 目录
- 解析完成后原始文件可清理
- 建议定期清理超过 7 天的临时文件：

```bash
find storage/ -type f -mtime +7 -delete
```

---

## 9. 日常运维

### 9.1 服务健康检查

```bash
# 后端健康检查
curl http://localhost:8000/api/v1/health

# 数据库连接检查
psql -U postgres -d ai_literacy -c "SELECT 1"

# Redis 检查
redis-cli ping
```

### 9.2 日志查看

```bash
# 后端日志
tail -f /var/log/ai-literacy/backend.log

# 如使用 Docker
docker-compose logs -f backend
```

### 9.3 性能监控要点

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| API 响应时间 | > 5s | 检查数据库查询或 LLM 调用 |
| 数据库连接数 | > 80% | 考虑增加连接池 |
| 磁盘使用率 | > 85% | 清理日志和临时文件 |
| 内存使用率 | > 90% | 检查是否有内存泄漏 |

---

## 10. 故障排查

### 10.1 试卷导入失败

**现象**: Word 文件上传后解析结果为空

**排查步骤**:
1. 确认文件为 `.docx` 格式（不支持 `.doc`）
2. 检查后端日志中的解析错误信息
3. 确认 `python-docx` 库已安装: `pip show python-docx`
4. 尝试用 python-docx 直接打开文件确认文件完整性

### 10.2 LLM 服务不可用

**现象**: AI 出题、审核等功能报错

**排查步骤**:
1. 检查 LLM 服务是否启动: `curl http://LLM_API_BASE/v1/models`
2. 检查系统配置页面的 LLM 配置是否正确
3. 检查 .env 中的 LLM 相关配置
4. 查看后端日志中的具体错误信息

### 10.3 数据库迁移失败

**现象**: `alembic upgrade head` 报错

**排查步骤**:
1. 查看当前迁移版本: `alembic current`
2. 检查是否有未完成的迁移: `alembic history`
3. 如有冲突，尝试: `alembic stamp head` 后重新迁移
4. 最终手段：从备份恢复数据库

### 10.4 前端页面空白

**排查步骤**:
1. 检查 Nginx 配置中 `try_files` 是否正确
2. 确认 `dist/` 目录存在且有内容
3. 检查浏览器控制台错误
4. 确认 API 代理配置正确

---

## 附录 A: 版本标签说明

| 标签 | 说明 | 推荐度 |
|------|------|--------|
| `v1.0.0` | 初始稳定版，基础题库+考试功能 | 可用 |
| `v2.0.0` | 试卷管理+Word导入+题库同步+系统配置 | **推荐** |

切换版本：
```bash
git fetch --tags
git checkout v1.0.0  # 切换到 v1.0
git checkout v2.0.0  # 切换到 v2.0（推荐）
```

## 附录 B: 端口清单

| 服务 | 端口 | 说明 |
|------|------|------|
| Nginx | 80/443 | Web 入口 |
| FastAPI | 8000 | 后端 API |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 缓存 |
| MinIO API | 9000 | 对象存储 API |
| MinIO Console | 9001 | 对象存储控制台 |
| vLLM | 8001 | 大模型服务（可配置） |
