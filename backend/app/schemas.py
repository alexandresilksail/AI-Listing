"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------- 商品
class ProductParamIn(BaseModel):
    group: str = "basic"
    key: str
    value: str = ""
    unit: str = ""
    verified: bool = False
    source: str = "manual"


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = ""
    brand: str = ""
    model: str = ""
    category: str = ""
    source_text: str = ""
    params: list[ProductParamIn] = []

    @field_validator("sku")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU 不能为空")
        return v


class ProductUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    source_text: str | None = None
    status: str | None = None


class ParamOut(ProductParamIn):
    id: int
    model_config = {"from_attributes": True}


class ProductImageOut(BaseModel):
    id: int
    kind: str
    filename: str
    mime: str
    size: int
    width: int
    height: int
    url: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    brand: str
    model: str
    category: str
    source_text: str
    status: str
    is_demo: bool
    params: list[ParamOut] = []
    images: list[ProductImageOut] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProductBrief(BaseModel):
    id: int
    sku: str
    name: str
    brand: str
    category: str
    image_count: int = 0
    is_demo: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}


class ImportResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    errors: list[str] = []
    product_ids: list[int] = []


# ---------------------------------------------------------------- Listing
class ListingTaskCreate(BaseModel):
    product_id: int
    platform: str = "amazon"
    markets: list[str] = Field(default_factory=lambda: ["US"])
    idempotency_key: str = ""

    @field_validator("markets")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("至少选择一个目标市场")
        return v


class ListingFieldOut(BaseModel):
    field: str
    content: Any


class ListingVersionOut(BaseModel):
    id: int
    product_id: int
    platform: str
    market: str
    language: str
    version: int
    is_current: bool
    is_simulated: bool
    source: str
    localization_note: str
    risk_note: str
    fields: list[ListingFieldOut] = []
    created_at: datetime
    model_config = {"from_attributes": True}


class ListingTaskOut(BaseModel):
    id: int
    product_id: int
    product_sku: str = ""
    platform: str
    market: str
    language: str
    status: str
    is_simulated: bool
    model_name: str
    error: str
    cost_usd: float | None = None  # None = 费用未知（模型不在价格表）
    duration_ms: int
    epoch: int = 0  # 任务版本号（提交/重试递增，防旧执行覆盖）
    created_at: datetime
    updated_at: datetime
    version: ListingVersionOut | None = None
    model_config = {"from_attributes": True}


class ListingFieldPatch(BaseModel):
    field: str
    content: Any


class ListingEdit(BaseModel):
    fields: list[ListingFieldPatch] = []
    note: str = ""


# ---------------------------------------------------------------- SEO
class SeoKeywordIn(BaseModel):
    keyword: str
    kw_type: str = "core"
    must_include: bool = False
    banned: bool = False


class SeoGenerateIn(BaseModel):
    product_id: int
    market: str = "US"


class KeywordOut(BaseModel):
    id: int
    keyword: str
    kw_type: str
    source: str
    must_include: bool
    banned: bool
    note: str
    market: str
    language: str
    model_config = {"from_attributes": True}


class TitleCandidateOut(BaseModel):
    id: int
    title: str
    scores: dict
    is_selected: bool
    market: str
    language: str
    platform: str
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- 图片
class ImageTaskCreate(BaseModel):
    product_id: int
    image_type: str = "main"
    platform: str = "amazon"
    market: str = "US"
    aspect_ratio: str = "1:1"
    count: int = Field(default=1, ge=1, le=4)
    style: str = ""
    background: str = ""
    prompt: str = ""
    ref_image_ids: list[int] = []
    idempotency_key: str = ""


class GeneratedImageOut(BaseModel):
    id: int
    task_id: int
    product_id: int
    image_type: str
    market: str
    language: str
    filename: str
    url: str
    width: int
    height: int
    is_simulated: bool
    version: int
    review_status: str
    prompt: str = ""
    created_at: datetime
    model_config = {"from_attributes": True}


class ImageTaskOut(BaseModel):
    id: int
    product_id: int
    product_sku: str = ""
    image_type: str
    platform: str
    market: str
    language: str
    aspect_ratio: str
    count: int
    prompt: str = ""
    status: str
    is_simulated: bool
    model_name: str
    error: str
    cost_usd: float | None = None  # None = 费用未知（模型不在价格表）
    duration_ms: int
    epoch: int = 0  # 任务版本号（提交/重试递增，防旧执行覆盖）
    created_at: datetime
    updated_at: datetime
    images: list[GeneratedImageOut] = []
    model_config = {"from_attributes": True}


class ImageReviewPatch(BaseModel):
    review_status: Literal["pending", "approved", "rejected"]


# ---------------------------------------------------------------- 审核
class ReviewItemOut(BaseModel):
    id: int
    target_type: str
    target_id: int
    product_id: int
    rule_code: str
    level: str
    reason: str
    location: str
    suggestion: str
    needs_manual: bool
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ReviewPatch(BaseModel):
    status: Literal["open", "resolved", "ignored"]


class RuleIn(BaseModel):
    platform: str = "amazon"
    market: str = "*"
    category: str = "*"
    rule_type: str = "text"
    code: str
    level: str = "medium"
    description: str = ""
    suggestion: str = ""
    source: str = "用户自定义"
    needs_verify: bool = True
    enabled: bool = True


class RuleOut(RuleIn):
    id: int
    updated_at: datetime
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- 设置
class ModelSettingsIn(BaseModel):
    text_api_base: str = ""
    text_api_key: str = ""
    text_model: str = ""
    image_api_base: str = ""
    image_api_key: str = ""
    image_model: str = ""
    daily_budget_usd: float = 10.0
    per_task_budget_usd: float = 2.0
    max_skus_per_task: int = 50
    max_upload_mb: int = 10


class ModelSettingsOut(BaseModel):
    text_configured: bool
    image_configured: bool
    text_api_base: str
    text_api_key_masked: str
    text_model: str
    image_api_base: str
    image_api_key_masked: str
    image_model: str
    daily_budget_usd: float
    per_task_budget_usd: float
    max_skus_per_task: int
    max_upload_mb: int


# ---------------------------------------------------------------- 导出
class ExportCreate(BaseModel):
    type: Literal["listing_csv", "listing_xlsx", "images_zip", "full_package"]
    product_id: int | None = None
    market: str | None = None
    platform: str | None = None
    language: str | None = None
    image_ids: list[int] = []


class ExportTaskOut(BaseModel):
    id: int
    type: str
    params: dict
    status: str
    file_name: str
    file_size: int
    error: str
    created_at: datetime
    finished_at: datetime | None
    download_url: str = ""
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- 通用
class TaskStatusOut(BaseModel):
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    partial: int = 0


class DashboardOut(BaseModel):
    products: int = 0
    demo_products: int = 0
    listing_tasks: TaskStatusOut = TaskStatusOut()
    image_tasks: TaskStatusOut = TaskStatusOut()
    generated_images: int = 0
    simulated_images: int = 0
    open_reviews_high: int = 0
    open_reviews_total: int = 0
    text_configured: bool = False
    image_configured: bool = False
    today_cost_usd: float = 0.0
    daily_budget_usd: float = 10.0
