"""应用配置：所有敏感配置仅从服务端环境变量/本地设置文件读取，绝不下发到前端。"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
# PL_DATA_DIR 允许测试/容器化部署重定向数据目录（必须在导入本模块前设置）
DATA_DIR = Path(os.environ.get("PL_DATA_DIR") or (BASE_DIR / "data"))
IMAGES_DIR = DATA_DIR / "images"
EXPORTS_DIR = DATA_DIR / "exports"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "polylisting.db"

# 演示数据目录（随代码分发）
DEMO_DIR = BASE_DIR.parent / "demo"

MARKET_LANGUAGES = {
    "US": {"language": "en-US", "label": "美国 · 美式英语", "rtl": False},
    "UK": {"language": "en-GB", "label": "英国 · 英式英语", "rtl": False},
    "DE": {"language": "de-DE", "label": "德国 · 德语", "rtl": False},
    "FR": {"language": "fr-FR", "label": "法国 · 法语", "rtl": False},
    "ES": {"language": "es-ES", "label": "西班牙 · 西班牙语", "rtl": False},
    "IT": {"language": "it-IT", "label": "意大利 · 意大利语", "rtl": False},
    "JP": {"language": "ja-JP", "label": "日本 · 日语", "rtl": False},
    "BR": {"language": "pt-BR", "label": "巴西 · 巴西葡萄牙语", "rtl": False},
    "ID": {"language": "id-ID", "label": "印度尼西亚 · 印尼语", "rtl": False},
    "TH": {"language": "th-TH", "label": "泰国 · 泰语", "rtl": False},
    "SA": {"language": "ar-SA", "label": "沙特阿拉伯 · 阿拉伯语", "rtl": True},
}

PLATFORMS = ["amazon", "temu", "独立站"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PL_", env_file=".env", extra="ignore")

    app_name: str = "PolyListing AI"
    host: str = "0.0.0.0"
    port: int = 8000

    # 数据库（默认 SQLite，生产可切换 PostgreSQL）
    database_url: str = f"sqlite:///{DB_PATH.as_posix()}"

    # 安全
    api_token: str = Field(default="", description="可选：前端访问后端所需令牌，留空则本机开发不校验")
    max_upload_mb: int = 10
    max_images_per_task: int = 8
    allowed_image_ext: tuple[str, ...] = ("jpg", "jpeg", "png", "webp")

    # AI 适配器（OpenAI 兼容接口；留空表示未配置，生成结果将标记为“模拟”）
    text_api_base: str = Field(default="", description="文本模型 API Base，如 https://api.openai.com/v1")
    text_api_key: str = Field(default="", description="文本模型 API Key（仅服务端保存）")
    text_model: str = Field(default="gpt-4o-mini", description="文本模型名称")
    image_api_base: str = Field(default="", description="图像模型 API Base")
    image_api_key: str = Field(default="", description="图像模型 API Key（仅服务端保存）")
    image_model: str = Field(default="gpt-image-1", description="图像模型名称")
    request_timeout_sec: int = 120
    max_retries: int = 2

    # 预算控制
    daily_budget_usd: float = 10.0
    per_task_budget_usd: float = 2.0
    max_skus_per_task: int = 50

    # CORS（前端开发服务器）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def text_configured(self) -> bool:
        return bool(self.text_api_base and self.text_api_key)

    @property
    def image_configured(self) -> bool:
        return bool(self.image_api_base and self.image_api_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (DATA_DIR, IMAGES_DIR, EXPORTS_DIR, UPLOADS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return s


def settings_file_path() -> Path:
    """本地运行时设置文件（保存用户在“模型设置”页填写的 API 配置，仅服务端可读）。"""
    return DATA_DIR / "runtime_settings.json"


def load_runtime_settings() -> dict:
    p = settings_file_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_runtime_settings(data: dict) -> None:
    p = settings_file_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)  # 仅当前用户可读写
    except Exception:
        pass


def effective_settings() -> Settings:
    """合并环境变量与运行时设置文件（运行时优先）。"""
    base = get_settings()
    rt = load_runtime_settings()
    if not rt:
        return base
    data = {}
    for k in ("text_api_base", "text_api_key", "text_model", "image_api_base",
              "image_api_key", "image_model", "daily_budget_usd", "per_task_budget_usd",
              "max_skus_per_task", "max_upload_mb"):
        if k in rt and rt[k] not in (None, ""):
            data[k] = rt[k]
    if not data:
        return base
    return base.model_copy(update=data)
