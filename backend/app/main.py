"""PolyListing AI 后端应用入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_api_token, warn_if_insecure
from .config import effective_settings
from .database import init_db
from .routers import (demo, exports, files, images, listings, products, reviews,
                      rules, seo, settings, tasks)
from .services.review_service import ensure_default_rules
from .services.task_queue import get_queue

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("polylisting")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = effective_settings()
    # 生产模式启动前检查：未配置 API 令牌直接拒绝启动（fail-fast）
    s.validate_production()
    warn_if_insecure()
    init_db()
    # 初始化内置平台规则（幂等）
    from .database import get_sessionmaker
    db = get_sessionmaker()()
    try:
        ensure_default_rules(db)
    finally:
        db.close()
    queue = get_queue()
    # 启动对账：恢复遗留 pending 任务，processing 标记失败（不静默丢失）
    queue.recover_on_startup()
    await queue.start()
    logger.info("PolyListing AI 后端已启动（env=%s，任务队列运行中）", s.env)
    yield
    await queue.stop()


app = FastAPI(title="PolyListing AI", version="1.1.0", lifespan=lifespan,
              dependencies=[Depends(require_api_token)])

s = effective_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (products.router, listings.router, seo.router, images.router,
          reviews.router, tasks.router, exports.router, settings.router,
          rules.router, files.router, demo.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    s = effective_settings()
    # 探活端点：仅返回运行状态与“是否已配置模型”布尔探针（无任何密钥/配置细节）
    return {"status": "ok", "app": s.app_name, "env": s.env,
            "text_configured": s.text_configured,
            "image_configured": s.image_configured}


@app.get("/api/meta")
def meta():
    from .config import MARKET_LANGUAGES, PLATFORMS
    from .services.market_data import IMAGE_TYPE_LABELS
    return {"markets": MARKET_LANGUAGES, "platforms": PLATFORMS,
            "image_types": IMAGE_TYPE_LABELS,
            "aspect_ratios": ["1:1", "3:4", "4:3", "9:16", "16:9"]}
