#!/usr/bin/env bash
# PolyListing AI Linux 启动脚本
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

command -v python3 >/dev/null || { echo "缺少 python3"; exit 1; }
command -v node >/dev/null || { echo "缺少 node（前端需要）"; exit 1; }

# 1. 后端虚拟环境
if [ ! -d ".venv" ]; then
  echo "创建 Python 虚拟环境..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r backend/requirements.txt

# 2. 前端依赖与构建（可选：开发模式直接 npm run dev）
if [ ! -d "frontend/node_modules" ]; then
  echo "安装前端依赖（首次较慢）..."
  (cd frontend && npm install)
fi

echo "启动后端 :8000 与前端 :5173 ..."
(cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
wait
