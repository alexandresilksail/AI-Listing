#!/usr/bin/env bash
# PolyListing AI Linux 启动脚本（开发/单机部署）
# 首次运行自动创建 venv、安装依赖；生产部署建议使用 docker compose。
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

command -v python3 >/dev/null || { echo "缺少 python3（需要 3.10+）"; exit 1; }
command -v node >/dev/null || { echo "缺少 node（前端需要 20+）"; exit 1; }

# 1. 后端虚拟环境（幂等）
if [ ! -d ".venv" ]; then
  echo "创建 Python 虚拟环境..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "安装/校验后端依赖..."
pip install -q --disable-pip-version-check -r backend/requirements.txt

# 2. 前端依赖（幂等）
if [ ! -d "frontend/node_modules" ]; then
  echo "安装前端依赖（首次较慢）..."
  (cd frontend && npm install --no-audit --no-fund)
fi

# 鉴权提示
if [ -z "$PL_API_TOKEN" ]; then
  echo "⚠️  未设置 PL_API_TOKEN：当前为 development 模式，管理接口无鉴权。"
  echo "    生产部署请设置 PL_ENV=production 与 PL_API_TOKEN（见 .env.example）。"
fi

# 3. 启动后端（异常退出时给出明确错误）
echo "启动后端 :8000 ..."
(cd backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!

# 等待后端就绪（最多 30s）
for _ in $(seq 1 15); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "后端已就绪。"
    break
  fi
  sleep 2
done

# 4. 启动前端
echo "启动前端 :5173 ..."
(cd frontend && exec npm run dev) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "正在停止服务..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "  前端   http://127.0.0.1:5173"
echo "  后端   http://127.0.0.1:8000/api/health"
echo "  Ctrl+C 停止全部服务"
wait
