FROM python:3.12-slim

WORKDIR /app

# 系统依赖：Pillow 需要部分图像库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libjpeg-turbo-progs zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./

RUN mkdir -p /app/data/images /app/data/exports /app/data/uploads

ENV PYTHONUNBUFFERED=1
ENV PL_DATA_DIR=/app/data
ENV PL_DATABASE_URL=sqlite:////app/data/polylisting.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
