"""数据模型：商品/SKU、参数、图片、Listing、SEO、审核、任务、导出、模型配置、平台规则。"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------- 商品
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("sku", name="uq_products_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    brand: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    source_text: Mapped[str] = mapped_column(Text, default="")  # 原始中文详情
    status: Mapped[str] = mapped_column(String(32), default="active")  # active/archived
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    params: Mapped[list["ProductParam"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    listing_tasks: Mapped[list["ListingTask"]] = relationship(
        back_populates="product", cascade="all, delete-orphan")
    image_tasks: Mapped[list["ImageGenTask"]] = relationship(
        back_populates="product", cascade="all, delete-orphan")
    keywords: Mapped[list["SeoKeyword"]] = relationship(
        back_populates="product", cascade="all, delete-orphan")
    titles: Mapped[list["TitleCandidate"]] = relationship(
        back_populates="product", cascade="all, delete-orphan")


class ProductParam(Base):
    """结构化商品参数。verified=True 表示经用户确认，AI 不得覆盖。"""
    __tablename__ = "product_params"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    group: Mapped[str] = mapped_column(String(64), default="basic")  # basic/spec/cert/package/usage
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual/import/extracted

    product: Mapped[Product] = relationship(back_populates="params")


class ProductImage(Base):
    """原始商品图片（永不覆盖；生成图另存 GeneratedImage）。"""
    __tablename__ = "product_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="main")  # main/实物/细节/包装/场景/logo/参考
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(64), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    product: Mapped[Product] = relationship(back_populates="images")


# ---------------------------------------------------------------- Listing
class ListingTask(Base):
    __tablename__ = "listing_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="amazon")
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/processing/completed/partial/failed
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)  # 未配置 API 时为模拟结果
    model_name: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # cost_usd: NULL 表示费用未知（模型不在价格表）；绝不允许把未知当 0
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    # epoch：任务版本号。每次提交/重试/恢复 +1；worker 执行前后校验，
    # epoch 已变（期间被重试）则丢弃本次执行结果，防止旧执行覆盖重试任务。
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    product: Mapped[Product] = relationship(back_populates="listing_tasks")
    # 一个任务可能产生多个版本（重试会生成新版本），按 id 升序，取最后一个为最新
    versions: Mapped[list["ListingVersion"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="ListingVersion.id", lazy="selectin")


class ListingVersion(Base):
    """一个任务产出一个版本；用户编辑后生成新版本，保留版本对比。"""
    __tablename__ = "listing_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("listing_tasks.id", ondelete="CASCADE"), nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="amazon")
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai/edit/manual/import
    localization_note: Mapped[str] = mapped_column(Text, default="")
    risk_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    task: Mapped[ListingTask | None] = relationship(back_populates="versions")
    fields: Mapped[list["ListingField"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin")


class ListingField(Base):
    __tablename__ = "listing_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("listing_versions.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(48))  # title/bullets/description/faq/search_terms/image_alt/marketing_slogan
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # 结构化内容（字符串/列表/字典）
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    version: Mapped[ListingVersion] = relationship(back_populates="fields")


# ---------------------------------------------------------------- SEO
class SeoKeyword(Base):
    __tablename__ = "seo_keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    keyword: Mapped[str] = mapped_column(String(255))
    kw_type: Mapped[str] = mapped_column(String(16), default="core")  # core/longtail/scene/attribute
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai/manual
    must_include: Mapped[bool] = mapped_column(Boolean, default=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")  # 明确标注：AI 建议，无真实搜索量数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    product: Mapped[Product] = relationship(back_populates="keywords")


class TitleCandidate(Base):
    __tablename__ = "title_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    platform: Mapped[str] = mapped_column(String(32), default="amazon")
    title: Mapped[str] = mapped_column(Text)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)  # length/keyword_coverage/readability
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    product: Mapped[Product] = relationship(back_populates="titles")


# ---------------------------------------------------------------- 图片生成
class ImageGenTask(Base):
    __tablename__ = "image_gen_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    image_type: Mapped[str] = mapped_column(String(32), default="main")  # main/scene/selling/info/brand/localize
    platform: Mapped[str] = mapped_column(String(32), default="amazon")
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")
    count: Mapped[int] = mapped_column(Integer, default=1)
    style: Mapped[str] = mapped_column(String(128), default="")
    background: Mapped[str] = mapped_column(String(128), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    ref_image_ids: Mapped[list] = mapped_column(JSON, default=list)  # 参考原图 ID
    status: Mapped[str] = mapped_column(String(16), default="pending")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # cost_usd: NULL 表示费用未知（模型不在价格表）；绝不允许把未知当 0
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    # epoch：任务版本号（同 ListingTask，防旧执行覆盖重试结果）
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    product: Mapped[Product] = relationship(back_populates="image_tasks")
    images: Mapped[list["GeneratedImage"]] = relationship(
        back_populates="task", cascade="all, delete-orphan")


class GeneratedImage(Base):
    """AI 生成图片（独立版本管理，不覆盖原图）。"""
    __tablename__ = "generated_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("image_gen_tasks.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    image_type: Mapped[str] = mapped_column(String(32), default="main")
    market: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    prompt: Mapped[str] = mapped_column(Text, default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/approved/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    task: Mapped[ImageGenTask] = relationship(back_populates="images")


# ---------------------------------------------------------------- 审核
class ReviewItem(Base):
    """文案/图片风险检查结果。level: high/medium/low/info。"""
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), default="listing")  # listing/image
    target_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # listing_version.id / generated_image.id
    product_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    rule_code: Mapped[str] = mapped_column(String(64), default="")
    level: Mapped[str] = mapped_column(String(16), default="low")
    reason: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    needs_manual: Mapped[bool] = mapped_column(Boolean, default=False)  # 无法自动判定的标记待核实
    status: Mapped[str] = mapped_column(String(16), default="open")  # open/resolved/ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- 模型配置与调用记录
class ModelConfigRow(Base):
    """模型配置（API Key 仅服务端保存，API 输出永远脱敏）。"""
    __tablename__ = "model_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), default="default")
    text_api_base: Mapped[str] = mapped_column(String(255), default="")
    text_api_key: Mapped[str] = mapped_column(String(255), default="")
    text_model: Mapped[str] = mapped_column(String(64), default="")
    image_api_base: Mapped[str] = mapped_column(String(255), default="")
    image_api_key: Mapped[str] = mapped_column(String(255), default="")
    image_model: Mapped[str] = mapped_column(String(64), default="")
    daily_budget_usd: Mapped[float] = mapped_column(Float, default=10.0)
    per_task_budget_usd: Mapped[float] = mapped_column(Float, default=2.0)
    max_skus_per_task: Mapped[int] = mapped_column(Integer, default=50)
    max_upload_mb: Mapped[int] = mapped_column(Integer, default=10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="openai-compatible")
    model: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(String(64), default="")  # listing/seo/image/review
    status: Mapped[str] = mapped_column(String(16), default="success")  # success/failed/simulated
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # cost_usd: NULL 表示费用未知（模型不在价格表）；仅费用已知的调用计入预算统计
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    # cost_basis: actual=调用返回实际用量计费 / estimated=按价格表预估 / unknown=价格未知
    cost_basis: Mapped[str] = mapped_column(String(16), default="estimated")
    # price_version: 计费用价格表版本（PRICING_VERSION），便于追溯估算依据
    price_version: Mapped[str] = mapped_column(String(32), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")  # 绝不记录密钥
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- 导出
class ExportTask(Base):
    __tablename__ = "export_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), default="listing_xlsx")  # listing_csv/listing_xlsx/images_zip/full_package
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- 平台规则
class PlatformRule(Base):
    __tablename__ = "platform_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="amazon")  # amazon/temu/* 通用
    market: Mapped[str] = mapped_column(String(8), default="*")
    category: Mapped[str] = mapped_column(String(64), default="*")
    rule_type: Mapped[str] = mapped_column(String(16), default="text")  # text/image
    code: Mapped[str] = mapped_column(String(64), default="")
    level: Mapped[str] = mapped_column(String(16), default="medium")  # high/medium/low
    description: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255), default="内置基线（需以平台官方最新规则为准）")
    needs_verify: Mapped[bool] = mapped_column(Boolean, default=True)  # 无法确认的一律标记待核实
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
