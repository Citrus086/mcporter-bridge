#!/bin/bash
# 以 HTTP 模式运行 mcporter-bridge，供 AlphaBot 接入
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
cd "$SCRIPT_DIR"

# 默认运行在 8765 端口，可以通过参数修改
# 用法: ./run-http.sh [端口号]
PORT=${1:-8765}

echo "🚀 启动 mcporter-bridge HTTP 服务器..."
echo "📍 地址: http://127.0.0.1:$PORT"
echo ""

"$SCRIPT_DIR/.venv/bin/python3" -m mcporter_bridge --transport http --port $PORT
