# PostgreSQL Backup Script Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个基于 `docker compose` 的 PostgreSQL 单次备份脚本，并补充最小可验证的测试与使用说明。

**Architecture:** 通过仓库内 shell 脚本调用 `docker compose exec` 进入 `postgres` 服务容器执行 `pg_dump`，利用容器环境变量获取数据库连接信息，导出结果直接 gzip 压缩后写入仓库内 `backups/postgres/`。测试侧以静态断言和 shell 语法检查为主，避免依赖本地 Docker 运行环境。

**Tech Stack:** Bash, Docker Compose v2, pytest

---

## Chunk 1: Script, Docs, And Validation

### Task 1: Add PostgreSQL backup script

**Files:**
- Create: `scripts/backup_postgres.sh`
- Modify: `README.md`
- Test: `tests/test_docker_compose_backup.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_backup_script_uses_docker_compose_exec():
    script_text = Path("scripts/backup_postgres.sh").read_text(encoding="utf-8")

    assert 'docker compose -f "$COMPOSE_FILE"' in script_text
    assert 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' in script_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docker_compose_backup.py -v`
Expected: FAIL because `scripts/backup_postgres.sh` does not exist yet and the assertions cannot pass.

- [ ] **Step 3: Write minimal implementation**

```bash
#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD=(docker compose -f "$COMPOSE_FILE")
"${COMPOSE_CMD[@]}" exec -T "$SERVICE_NAME" sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

Then expand it to include:
- repository-relative default paths
- `-f` / `--compose-file`
- dependency checks
- service existence / running checks
- timestamped gzip output under `backups/postgres/`
- temporary file cleanup on failure

- [ ] **Step 4: Update usage documentation**

Add a short README section showing:
- how to run the script
- default output directory
- how to override the Compose file

- [ ] **Step 5: Run verification**

Run:
- `bash -n scripts/backup_postgres.sh`
- `pytest tests/test_docker_compose_backup.py -v`

Expected:
- shell syntax check passes
- pytest passes

- [ ] **Step 6: Commit**

```bash
git add scripts/backup_postgres.sh README.md tests/test_docker_compose_backup.py docs/superpowers/specs/2026-03-16-postgres-backup-script-design.md docs/superpowers/plans/2026-03-16-postgres-backup-script.md
git commit -m "feat: add postgres backup script"
```
