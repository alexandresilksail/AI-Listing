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

    # 运行环境：development（本地开发，可无令牌）/ production（生产，必须配置 API 令牌）
    env: str = Field(default="development", description="development 或 production")

    # 数据库（默认 SQLite，生产可切换 PostgreSQL）
    database_url: str = f"sqlite:///{DB_PATH.as_posix()}"

    # 安全：API 访问令牌。production 环境下必须设置，否则应用拒绝启动（fail-fast）。
    # 所有 /api/* 管理接口（除 /api/health、/api/meta）都要求
    # Authorization: Bearer <token> 或 X-API-Token: <token>。
    api_token: str = Field(default="", description="API 访问令牌；生产环境必须设置")
    # 下载模型返回图片 URL 的大小上限（MB）
    max_download_mb: int = 20
    # 仅开发调试用：允许 http 与非公网地址的图片下载（SSRF 风险，生产禁止）
    allow_insecure_download: bool = False
    max_upload_mb: int = 10
    max_images_per_task: int = 8
    allowed_image_ext: tuple[str, ...] = ("jpg", "jpeg", "png", "webp")
    # 上传图片像素上限（防解压炸弹）
    max_image_pixels: int = 50_000_000

    # AI 适配器（OpenAI 兼容接口；留空表示未配置，生成结果将标记为“模拟”）
    text_api_base: str = Field(default="", description="文本模型 API Base，如 https://api.openai.com/v1")
    text_api_key: str = Field(default="", description="文本模型 API Key（仅服务端保存）")
    text_model: str = Field(default="gpt-4o-mini", description="文本模型名称")
    image_api_base: str = Field(default="", description="图像模型 API Base")
    image_api_key: str = Field(default="", description="图像模型 API Key（仅服务端保存）")
    image_model: str = Field(default="gpt-image-1", description="图像模型名称")
    request_timeout_sec: int = 120
    max_retries: int = 2
    # 文本模型 JSON 输出模式：json_object（默认，部分供应商不支持时自动降级为 none）
    text_json_mode: str = Field(default="json_object", description="json_object 或 none")
    # 未知模型价格策略：allow=允许执行但费用标记为未知；block=拒绝执行
    unknown_cost_policy: str = Field(default="allow", description="allow 或 block")

    # 预算控制
    daily_budget_usd: float = 10.0
    per_task_budget_usd: float = 2.0
    max_skus_per_task: int = 50

    # 单个任务执行超时（秒）
    task_timeout_sec: int = 600

    # CORS（前端开发服务器）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() == "production"

    @property
    def text_configured(self) -> bool:
        return bool(self.text_api_base and self.text_api_key)

    @property
    def image_configured(self) -> bool:
        return bool(self.image_api_base and self.image_api_key)

    def validate_production(self) -> None:
        """生产环境启动前检查：未配置 API 令牌直接拒绝启动（fail-fast）。"""
        if self.is_production and not self.api_token:
            raise RuntimeError(
                "PL_ENV=production 但未配置 PL_API_TOKEN：生产模式默认拒绝所有未授权请求，"
                "已拒绝启动。请设置 PL_API_TOKEN，或明确使用 PL_ENV=development 运行。")


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
