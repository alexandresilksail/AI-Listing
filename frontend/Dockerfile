# PolyListing AI 前端多阶段构建
# 构建上下文为项目根目录（compose: context: .），以便复制 deploy/nginx.conf
# 构建阶段：Node 编译 TypeScript/Vite → 产出 dist
# 运行阶段：Nginx 托管静态文件并反向代理 /api 到后端
FROM node:22-alpine AS build

WORKDIR /app

# 先复制依赖清单（利用 Docker 层缓存）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# 再复制源码并构建
COPY frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts \
     frontend/tailwind.config.js frontend/postcss.config.js frontend/index.html ./
COPY frontend/src/ ./src/
# 安全红线：本镜像不接受任何密钥类 build-arg。
# 前端访问令牌（PL_API_TOKEN）绝不进入构建层——否则会被打包进
# dist/*.js 与 Source Map，等同公开泄露。前端改为运行时输入：
# 用户首次访问时由页面提示输入，存入浏览器 localStorage。
RUN npm run build

# ---------------------------------------------------------------- 运行阶段
FROM nginx:1.27-alpine

# 默认反向代理目标（compose 中通过环境变量渲染模板）
ENV BACKEND_HOST=backend \
    BACKEND_PORT=8000

COPY deploy/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
