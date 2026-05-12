#!/usr/bin/env bash
# Novelforge Web · 生产姿势启动脚本
#
# 用法：
#   scripts/web-start.sh          # 启动（后台 + 日志 + PID）
#   scripts/web-stop.sh           # 停止
#   scripts/web-start.sh --fg     # 前台运行（Ctrl-C 停）
#
# 特点：
#   - 用 waitress（生产级 WSGI），没有 "development server" 警告
#   - 显式 unset READONLY_MODE + STATE_DIR，避免老环境变量残留
#   - 日志落在 /tmp/novelforge-web.log
#   - PID 落在 /tmp/novelforge-web.pid
#   - 自动在浏览器打开 /genres
set -euo pipefail

PORT="${NOVELFORGE_WEB_PORT:-5055}"
HOST="${NOVELFORGE_WEB_HOST:-127.0.0.1}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/novelforge-web.pid"
LOG_FILE="/tmp/novelforge-web.log"

# 清理可能残留的环境变量（它们是 GitHub Pages 静态 demo 才需要）
unset READONLY_MODE
unset STATE_DIR

# 如果已有实例在跑，先提醒
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "⚠ novelforge-web 已在运行（pid=$(cat "$PID_FILE")）"
    echo "   先跑 scripts/web-stop.sh 停掉再启动，或访问 http://${HOST}:${PORT}/"
    exit 1
fi

# 端口占用检查（非本 PID 的占用）
if lsof -ti ":$PORT" > /dev/null 2>&1; then
    echo "⚠ 端口 $PORT 已被占用（非本脚本启动的进程）。"
    echo "   NOVELFORGE_WEB_PORT=6000 scripts/web-start.sh  # 换端口"
    exit 1
fi

cd "$PROJECT_ROOT"

if [ "${1:-}" = "--fg" ]; then
    echo "▶ 前台启动 novelforge-web  http://${HOST}:${PORT}/"
    echo "  Ctrl-C 停止"
    exec python3 -m waitress --host="$HOST" --port="$PORT" web.app:app
fi

# 后台启动
nohup python3 -m waitress --host="$HOST" --port="$PORT" web.app:app \
    > "$LOG_FILE" 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > "$PID_FILE"

# 等待服务起来
for i in 1 2 3 4 5; do
    if curl -sf "http://${HOST}:${PORT}/" > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo "✗ 启动失败。检查日志：tail -f $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

echo "✓ novelforge-web 已启动"
echo "  地址: http://${HOST}:${PORT}/"
echo "  题材: http://${HOST}:${PORT}/genres"
echo "  素材: http://${HOST}:${PORT}/novels"
echo "  pid:  $WEB_PID"
echo "  log:  $LOG_FILE"
echo ""
echo "停止：scripts/web-stop.sh"

# 自动开浏览器（macOS）
if command -v open > /dev/null 2>&1; then
    open "http://${HOST}:${PORT}/genres"
fi
