# Seed Data (种子数据)

包含预置的试卷、题目和系统配置，部署后可直接导入使用。

## 内容

- `seed_data.sql` — 完整的种子数据（角色、用户、题目、试卷、考试、系统配置）
- 默认管理员：`admin` / `admin123`

## 使用方法

### 全新部署后导入

```bash
# 1. 确保数据库已创建并完成迁移
alembic upgrade head

# 2. 导入种子数据
docker exec -i ai-literacy-postgres psql -U ai_literacy -d ai_literacy_db < seed/seed_data.sql
```

### Docker Compose 部署

```bash
# 启动服务后
docker compose up -d
sleep 10  # 等待数据库就绪

# 运行迁移
docker exec ai-literacy-app alembic upgrade head

# 导入种子数据
docker exec -i ai-literacy-postgres psql -U ai_literacy -d ai_literacy_db < seed/seed_data.sql
```

## 注意事项

- 种子数据包含 bcrypt 加密的密码，可直接使用
- 如果数据库已有同 ID 的记录，导入会报重复键错误（可忽略或先清空）
- 系统配置（LLM 提供者等）需要根据实际环境重新设置
