# 构建上下文为项目根目录（compose: context: .），以便同时复制 backend/ 与 demo/
FROM python:3.12-slim

WORKDIR /app

# 系统依赖：Pillow 需要部分图像库；healthcheck 用 python 标准库（无需 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libjpeg-turbo-progs zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY backend/migrations/ ./migrations/
COPY backend/alembic.ini ./
# 演示商品 CSV（随镜像分发，供“批量导入”功能使用；路径与 config.DEMO_DIR 对应）
COPY demo/ /demo/

RUN mkdir -p /app/data/images /app/data/exports /app/data/uploads \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app/data

ENV PYTHONUNBUFFERED=1
ENV PL_DATA_DIR=/app/data
ENV PL_DATABASE_URL=sqlite:////app/data/polylisting.db

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
