# PostgreSQL 备份脚本设计

## 目标

提供一个可直接在仓库内执行的 PostgreSQL 单次备份脚本，基于 `docker-compose.yml` 中的 `postgres` 服务导出数据库，并把备份文件保存到仓库内目录。

## 范围

- 新增脚本 `scripts/backup_postgres.sh`
- 默认读取仓库根目录的 `docker-compose.yml`
- 通过 `docker compose exec` 在 `postgres` 容器内执行 `pg_dump`
- 默认输出到 `backups/postgres/`
- 生成带时间戳的 `.sql.gz` 文件
- 支持可选参数 `-f`/`--compose-file` 指定 Compose 文件

## 非目标

- 不增加自动清理旧备份逻辑
- 不增加自动定时任务
- 不增加数据库恢复脚本
- 不覆盖 MinIO、Redis、Milvus 等其他有状态服务

## 设计

脚本优先复用 Compose 中已声明的 `postgres` 服务和容器环境变量，而不是依赖宿主机安装 PostgreSQL 客户端。执行时先校验 `docker`、`gzip` 和 Compose 文件，再确认 `postgres` 服务存在且处于运行状态。备份命令通过 `docker compose exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"'` 执行，并将标准输出直接压缩写入 `backups/postgres/<db_name>_<timestamp>.sql.gz`。

## 成功与失败语义

- 成功：输出备份文件绝对路径
- 失败：输出明确错误信息并返回非零退出码

## 校验要点

- Compose 文件不存在时退出
- `postgres` 服务不存在时退出
- `postgres` 服务未运行时退出
- 备份过程中若 `pg_dump` 或压缩失败，不保留半成品文件
