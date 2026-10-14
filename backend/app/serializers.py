"""集中式序列化：SQLAlchemy 模型 → Pydantic Schema（手动构造嵌套关系）。

Pydantic v2 的 model_validate(from_attributes=True) 不会递归转换
关系对象，因此统一在此手工构建，避免 500 错误。
"""
from __future__ import annotations

from .models import (GeneratedImage, ImageGenTask, ListingField, ListingTask,
                     ListingVersion, Product, ProductImage, ProductParam,
                     ReviewItem)
from .schemas import (GeneratedImageOut, ImageTaskOut, ListingFieldOut, ParamOut,
                      ListingTaskOut, ListingVersionOut, ProductImageOut,
                      ProductOut, ReviewItemOut)


def field_out(f: ListingField) -> ListingFieldOut:
    return ListingFieldOut(field=f.field, content=f.content)


def version_out(v: ListingVersion | None) -> ListingVersionOut | None:
    if v is None:
        return None
    return ListingVersionOut(
        id=v.id, product_id=v.product_id, platform=v.platform, market=v.market,
        language=v.language, version=v.version, is_current=v.is_current,
        is_simulated=v.is_simulated, source=v.source,
        localization_note=v.localization_note, risk_note=v.risk_note,
        fields=[field_out(f) for f in v.fields], created_at=v.created_at)


def listing_task_out(t: ListingTask) -> ListingTaskOut:
    return ListingTaskOut(
        id=t.id, product_id=t.product_id,
        product_sku=t.product.sku if t.product else "",
        platform=t.platform, market=t.market, language=t.language,
        status=t.status, is_simulated=t.is_simulated, model_name=t.model_name,
        error=t.error, cost_usd=t.cost_usd, duration_ms=t.duration_ms,
        created_at=t.created_at, updated_at=t.updated_at,
        version=version_out(t.versions[-1]) if t.versions else None)


def image_task_out(t: ImageGenTask) -> ImageTaskOut:
    return ImageTaskOut(
        id=t.id, product_id=t.product_id,
        product_sku=t.product.sku if t.product else "",
        image_type=t.image_type, platform=t.platform, market=t.market,
        language=t.language, aspect_ratio=t.aspect_ratio, count=t.count,
        prompt=t.prompt, status=t.status, is_simulated=t.is_simulated,
        model_name=t.model_name,
        error=t.error, cost_usd=t.cost_usd, duration_ms=t.duration_ms,
        created_at=t.created_at, updated_at=t.updated_at,
        images=[generated_image_out(im) for im in t.images])


def generated_image_out(im: GeneratedImage) -> GeneratedImageOut:
    return GeneratedImageOut(
        id=im.id, task_id=im.task_id, product_id=im.product_id,
        image_type=im.image_type, market=im.market, language=im.language,
        filename=im.filename, url=f"/api/files/generated/{im.id}",
        width=im.width, height=im.height, is_simulated=im.is_simulated,
        version=im.version, review_status=im.review_status,
        prompt=im.prompt, created_at=im.created_at)


def product_image_out(im: ProductImage) -> ProductImageOut:
    return ProductImageOut(
        id=im.id, kind=im.kind, filename=im.filename, mime=im.mime,
        size=im.size, width=im.width, height=im.height,
        url=f"/api/files/image/{im.id}", created_at=im.created_at)


def product_out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id, sku=p.sku, name=p.name, brand=p.brand, model=p.model,
        category=p.category, source_text=p.source_text, status=p.status,
        is_demo=p.is_demo,
        params=[ParamOut(id=x.id, group=x.group, key=x.key, value=x.value,
                         unit=x.unit, verified=x.verified, source=x.source)
                for x in p.params],
        images=[product_image_out(im) for im in p.images],
        created_at=p.created_at, updated_at=p.updated_at)


def review_out(r: ReviewItem) -> ReviewItemOut:
    return ReviewItemOut.model_validate(r)
