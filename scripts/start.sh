#!/bin/bash
# 启动飞书权限通知系统

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "========================================="
echo "飞书权限通知系统 - 启动脚本"
echo "========================================="
echo ""

# 检查配置文件
if ! grep -q '"[^"]*"' config/config.yaml 2>/dev/null; then
    echo "⚠️  警告: config/config.yaml 中的飞书配置可能未填写"
    echo "请确保已填写 app_id、app_secret 和 user_id"
    echo ""
fi

# 启动 webhook 服务器
echo "🚀 启动 Webhook 服务器 (端口 8080)..."
python3 src/server/webhook_server.py &
WEBHOOK_PID=$!
echo "   Webhook 服务器 PID: $WEBHOOK_PID"
echo ""

# 等待服务器启动
sleep 2

# 健康检查
echo "🔍 健康检查..."
if curl -s http://localhost:8080/health > /dev/null; then
    echo "   ✅ Webhook 服务器运行正常"
else
    echo "   ❌ Webhook 服务器启动失败"
    kill $WEBHOOK_PID 2>/dev/null
    exit 1
fi
echo ""

echo "========================================="
echo "📋 下一步操作："
echo "========================================="
echo ""
echo "1. 启动内网穿透（如 ngrok）:"
echo "   ngrok http 8080"
echo ""
echo "2. 将生成的 HTTPS URL 配置到飞书开放平台的事件订阅中"
echo ""
echo "3. 在 Claude Code 中触发权限请求进行测试"
echo ""
echo "4. 停止服务器时按 Ctrl+C 或运行: kill $WEBHOOK_PID"
echo ""
echo "========================================="
echo ""

# 保持脚本运行，等待用户中断
trap "echo ''; echo '🛑 停止 Webhook 服务器...'; kill $WEBHOOK_PID 2>/dev/null; exit 0" INT TERM

wait $WEBHOOK_PID
