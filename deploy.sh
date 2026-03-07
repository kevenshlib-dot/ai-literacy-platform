#!/bin/bash
# ============================================
# AI素养评测平台 - 一键部署脚本
# 在目标 Linux 服务器上执行
# ============================================
set -e

echo "=========================================="
echo "  AI素养评测平台 - 部署脚本"
echo "=========================================="

# 1. 检查 Docker 环境
echo ""
echo "[1/6] 检查 Docker 环境..."

if ! command -v docker &> /dev/null; then
    echo "Docker 未安装，正在安装..."
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
    echo "Docker 安装完成，请重新登录后再次运行此脚本"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo "Docker Compose 未安装，正在安装..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null || \
    sudo yum install -y docker-compose-plugin 2>/dev/null || \
    echo "请手动安装 docker-compose-plugin"
fi

echo "Docker 版本: $(docker --version)"
echo "Docker Compose 版本: $(docker compose version 2>/dev/null)"

# 2. 检查 LM Studio
echo ""
echo "[2/6] 检查 LM Studio..."

if curl -sf http://localhost:1234/v1/models > /dev/null 2>&1; then
    echo "LM Studio 已在运行，可用模型:"
    curl -s http://localhost:1234/v1/models | python3 -c "
import sys,json
try:
    data=json.load(sys.stdin)
    for m in data.get('data',[]):
        print(f'  - {m[\"id\"]}')
except: print('  (无法解析模型列表)')
" 2>/dev/null || echo "  (检测到服务但无法列出模型)"
else
    echo ""
    echo "=========================================="
    echo "  LM Studio 未检测到！请先完成以下步骤："
    echo "=========================================="
    echo ""
    echo "  1. 下载 LM Studio Linux 版:"
    echo "     https://lmstudio.ai/download/linux"
    echo ""
    echo "  2. 安装:"
    echo "     chmod +x LM-Studio-*.AppImage"
    echo "     # 有桌面环境: 直接双击运行"
    echo "     # 无桌面 (推荐): 使用 lms CLI"
    echo ""
    echo "  3. 使用 CLI 启动 (无需桌面环境):"
    echo "     # 安装 CLI"
    echo "     npx lmstudio install-cli"
    echo "     # 下载模型"
    echo "     lms get openai/gpt-oss-20b"
    echo "     # 加载模型并启动服务"
    echo "     lms load openai/gpt-oss-20b"
    echo "     lms server start"
    echo ""
    echo "  4. 确认 LM Studio 在 http://localhost:1234 运行后"
    echo "     重新执行本脚本: ./deploy.sh"
    echo "=========================================="
    echo ""
    read -p "LM Studio 是否已就绪？继续部署？(y/N): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        echo "已取消。请先启动 LM Studio 后再运行此脚本。"
        exit 0
    fi
fi

# 3. 检查配置文件
echo ""
echo "[3/6] 检查配置文件..."

if [ ! -f ".env.production" ]; then
    echo "错误: 未找到 .env.production 文件"
    echo "请先编辑 .env.production 配置文件"
    exit 1
fi

# 自动生成安全密钥
if grep -q "change-this-to-a-random-secret-key-in-production" .env.production; then
    echo "正在自动生成 SECRET_KEY..."
    NEW_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/SECRET_KEY=change-this-to-a-random-secret-key-in-production/SECRET_KEY=$NEW_SECRET/" .env.production
    echo "SECRET_KEY 已更新"
fi

if grep -q "change-this-to-a-random-jwt-secret" .env.production; then
    echo "正在自动生成 JWT_SECRET_KEY..."
    NEW_JWT=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/JWT_SECRET_KEY=change-this-to-a-random-jwt-secret/JWT_SECRET_KEY=$NEW_JWT/" .env.production
    echo "JWT_SECRET_KEY 已更新"
fi

echo "配置文件检查完成"

# 4. 构建镜像
echo ""
echo "[4/6] 构建 Docker 镜像（首次较慢，约 5-10 分钟）..."
docker compose build

# 5. 启动服务
echo ""
echo "[5/6] 启动所有服务..."
docker compose up -d

# 6. 等待服务就绪
echo ""
echo "[6/6] 等待服务启动..."

MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  已等待 ${WAITED}s..."
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo ""
    echo "警告: 后端服务启动超时，请检查日志:"
    echo "  docker compose logs app"
    echo "  docker compose logs postgres"
else
    echo ""
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "服务器IP")
    echo "=========================================="
    echo "  部署成功！"
    echo "=========================================="
    echo ""
    echo "  平台访问:  http://${LOCAL_IP}"
    echo "  API 文档:  http://${LOCAL_IP}/docs"
    echo ""
    echo "  LM Studio: http://localhost:1234 (本机)"
    echo "  MinIO:     http://${LOCAL_IP}:9001  (minioadmin/minioadmin)"
    echo "  RabbitMQ:  http://${LOCAL_IP}:15672 (guest/guest)"
    echo ""
    echo "  常用命令:"
    echo "    docker compose ps          # 查看服务状态"
    echo "    docker compose logs -f app # 查看后端日志"
    echo "    docker compose restart     # 重启服务"
    echo "    docker compose down        # 停止服务"
    echo "=========================================="
fi
