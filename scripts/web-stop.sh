#!/usr/bin/env bash
# Novelforge Web · 停止脚本
set -euo pipefail

PID_FILE="/tmp/novelforge-web.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "（没有 PID 文件，服务可能没在跑）"
    # 兜底：按端口清
    PORT="${NOVELFORGE_WEB_PORT:-5055}"
    if lsof -ti ":$PORT" > /dev/null 2>&1; then
        echo "发现端口 $PORT 还被占用，尝试强制关闭…"
        lsof -ti ":$PORT" | xargs kill 2>/dev/null || true
        sleep 0.5
        lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true
    fi
    exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 0.5
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
    fi
    echo "✓ 已停止 pid=$PID"
else
    echo "（pid=$PID 已不存在）"
fi
rm -f "$PID_FILE"
