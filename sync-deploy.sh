#!/bin/bash
# ============================================================
# AI素养评测平台 - 同步部署脚本
# 用法: ./sync-deploy.sh [sync|deploy|full]
#   sync   - 仅同步代码到服务器（不重建容器）
#   deploy - 同步代码 + 重建并重启容器
#   full   - 同步代码 + 强制重建镜像 + 重启容器
# ============================================================

set -e

SERVER="dell@192.168.31.18"
REMOTE_DIR="~/ai-literacy-platform"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
ACTION="${1:-sync}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}  AI素养评测平台 - 同步部署工具${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

# ---- Step 1: 构建前端 ----
echo -e "${YELLOW}[1/4] 构建前端...${NC}"
cd "$LOCAL_DIR/frontend"
if [ "$ACTION" = "full" ] || [ ! -d "dist" ]; then
    npm run build
    echo -e "${GREEN}  ✓ 前端构建完成${NC}"
else
    echo -e "${GREEN}  ✓ 使用已有的 dist/ (如需重新构建请用 full 模式)${NC}"
fi

# ---- Step 2: 同步代码到服务器 ----
echo -e "${YELLOW}[2/4] 同步代码到服务器 ${SERVER}...${NC}"
cd "$LOCAL_DIR"
rsync -avz --delete \
    --exclude '.git' \
    --exclude '.claude' \
    --exclude '.env' \
    --exclude 'frontend/node_modules' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    . "${SERVER}:${REMOTE_DIR}/"

echo -e "${GREEN}  ✓ 代码同步完成${NC}"

if [ "$ACTION" = "sync" ]; then
    echo ""
    echo -e "${GREEN}同步完成！如需重建容器，请运行:${NC}"
    echo -e "  ./sync-deploy.sh deploy"
    exit 0
fi

# ---- Step 3: 重建 Docker 镜像 ----
echo -e "${YELLOW}[3/4] 重建 Docker 镜像...${NC}"
if [ "$ACTION" = "full" ]; then
    ssh "$SERVER" "cd ${REMOTE_DIR} && docker compose build --no-cache"
else
    ssh "$SERVER" "cd ${REMOTE_DIR} && docker compose build"
fi
echo -e "${GREEN}  ✓ 镜像构建完成${NC}"

# ---- Step 4: 重启服务 ----
echo -e "${YELLOW}[4/4] 重启服务...${NC}"
ssh "$SERVER" "cd ${REMOTE_DIR} && docker compose up -d"

# 等待健康检查
echo -e "${YELLOW}  等待服务启动...${NC}"
sleep 15
HEALTH=$(ssh "$SERVER" "curl -sf http://localhost:8000/api/v1/health 2>/dev/null || echo 'FAIL'")

if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}  ✓ 服务启动成功！${NC}"
else
    echo -e "${YELLOW}  ⚠ 后端可能还在初始化，请稍后检查${NC}"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}  平台地址: http://192.168.31.18${NC}"
echo -e "${GREEN}  API文档:  http://192.168.31.18/docs${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
