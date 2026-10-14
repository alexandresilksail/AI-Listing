"""导出服务：Listing XLSX/CSV、图片 ZIP、完整商品内容包。"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..models import (ExportTask, GeneratedImage, ListingVersion, Product, ReviewItem,
                      SeoKeyword, TitleCandidate)
from ..security import csv_safe
from .storage import get_storage, rel_path

LISTING_COLUMNS = ["SKU", "商品名称", "平台", "市场", "语言", "版本", "是否模拟",
                   "标题", "五点卖点", "商品详情", "FAQ", "后台搜索词",
                   "图片ALT", "营销标语", "本地化说明", "风险提示", "生成时间"]


def _listing_rows(db, product_id: int | None, market: str | None,
                  platform: str | None) -> list[dict]:
    q = db.query(ListingVersion).filter(ListingVersion.is_current.is_(True))
    if product_id:
        q = q.filter(ListingVersion.product_id == product_id)
    if market:
        q = q.filter(ListingVersion.market == market)
    if platform:
        q = q.filter(ListingVersion.platform == platform)
    rows = []
    for v in q.order_by(ListingVersion.product_id, ListingVersion.market).all():
        product = db.get(Product, v.product_id)
        fields = {f.field: f.content for f in v.fields}

        def ft(c):
            if isinstance(c, list):
                if c and isinstance(c[0], list):
                    return "\n".join("Q: %s\nA: %s" % (p[0], p[1]) for p in c if len(p) >= 2)
                return "\n".join(str(x) for x in c)
            return str(c or "")

        rows.append({
            "SKU": product.sku if product else "",
            "商品名称": product.name if product else "",
            "平台": v.platform, "市场": v.market, "语言": v.language,
            "版本": v.version, "是否模拟": "是（模拟演示）" if v.is_simulated else "否",
            "标题": ft(fields.get("title", "")),
            "五点卖点": ft(fields.get("bullets", [])),
            "商品详情": ft(fields.get("description", "")),
            "FAQ": ft(fields.get("faq", [])),
            "后台搜索词": ft(fields.get("search_terms", "")),
            "图片ALT": ft(fields.get("image_alt", "")),
            "营销标语": ft(fields.get("marketing_slogan", "")),
            "本地化说明": v.localization_note,
            "风险提示": v.risk_note,
            "生成时间": v.created_at.strftime("%Y-%m-%d %H:%M"),
        })
    return rows


def export_listing(db, export_id: int, fmt: str, product_id: int | None,
                   market: str | None, platform: str | None) -> ExportTask:
    task = db.get(ExportTask, export_id)
    if task is None:
        raise ValueError("导出任务不存在")
    rows = _listing_rows(db, product_id, market, platform)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=LISTING_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: csv_safe(r[k]) for k in LISTING_COLUMNS})
        content = buf.getvalue().encode("utf-8-sig")
        from ..config import EXPORTS_DIR
        from ..security import safe_join
        target = safe_join(EXPORTS_DIR, f"listing_export_{export_id}.csv")
        target.write_bytes(content)
        task.file_path, task.file_name = rel_path(target), target.name
    else:
        import pandas as pd
        df = pd.DataFrame(rows, columns=LISTING_COLUMNS)
        from ..config import EXPORTS_DIR
        from ..security import safe_join
        target = safe_join(EXPORTS_DIR, f"listing_export_{export_id}.xlsx")
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Listings")
            ws = writer.sheets["Listings"]
            for col in ws.columns:
                maxlen = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(maxlen + 4, 60)
        task.file_path, task.file_name = rel_path(target), target.name
    task.file_size = get_storage().abs_path(task.file_path).stat().st_size
    task.status = "completed"
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return task


def export_images_zip(db, export_id: int, image_ids: list[int] | None,
                      product_id: int | None, market: str | None) -> ExportTask:
    task = db.get(ExportTask, export_id)
    if task is None:
        raise ValueError("导出任务不存在")
    q = db.query(GeneratedImage)
    if image_ids:
        q = q.filter(GeneratedImage.id.in_(image_ids))
    if product_id:
        q = q.filter(GeneratedImage.product_id == product_id)
    if market:
        q = q.filter(GeneratedImage.market == market)
    images = q.order_by(GeneratedImage.product_id, GeneratedImage.image_type).all()
    if not images:
        task.status = "failed"
        task.error = "没有符合条件的生成图片"
        db.commit()
        return task

    storage = get_storage()
    from ..config import EXPORTS_DIR
    from ..security import safe_join
    target = safe_join(EXPORTS_DIR, f"images_export_{export_id}.zip")
    manifest = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for im in images:
            product = db.get(Product, im.product_id)
            sku = product.sku if product else "unknown"
            arc = f"{sku}/{im.market}/{im.image_type}/{im.filename}"
            try:
                zf.writestr(arc, storage.read(im.path))
            except Exception:  # noqa: BLE001
                continue
            manifest.append({"file": arc, "sku": sku, "market": im.market,
                             "type": im.image_type, "width": im.width, "height": im.height,
                             "is_simulated": im.is_simulated, "version": im.version,
                             "prompt": im.prompt})
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    task.file_path = rel_path(target)
    task.file_name = target.name
    task.file_size = target.stat().st_size
    task.status = "completed"
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return task


def export_full_package(db, export_id: int, product_id: int) -> ExportTask:
    """完整商品内容包：Listing + SEO + FAQ + 图片 + 审核报告。"""
    task = db.get(ExportTask, export_id)
    if task is None:
        raise ValueError("导出任务不存在")
    product = db.get(Product, product_id)
    if product is None:
        task.status = "failed"
        task.error = "商品不存在"
        db.commit()
        return task

    storage = get_storage()
    from ..config import EXPORTS_DIR
    from ..security import safe_join
    target = safe_join(EXPORTS_DIR, f"package_{product.sku}_{export_id}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 商品资料
        facts = {
            "sku": product.sku, "name": product.name, "brand": product.brand,
            "model": product.model, "category": product.category,
            "params": [{"key": p.key, "value": p.value, "unit": p.unit,
                        "verified": p.verified} for p in product.params],
            "source_text": product.source_text,
        }
        zf.writestr("01_product_facts.json", json.dumps(facts, ensure_ascii=False, indent=2))

        # 2. 各市场 Listing（Markdown）
        versions = db.query(ListingVersion).filter(
            ListingVersion.product_id == product_id,
            ListingVersion.is_current.is_(True)).all()
        listing_md = []
        for v in versions:
            fields = {f.field: f.content for f in v.fields}
            listing_md.append(f"\n## {v.market} / {v.language} / {v.platform} "
                              f"（版本 v{v.version}{'，模拟演示' if v.is_simulated else ''}）\n")
            title = fields.get("title", "")
            listing_md.append(f"### 标题\n{title}\n")
            bullets = fields.get("bullets") or []
            if isinstance(bullets, list):
                listing_md.append("### 五点卖点\n" + "\n".join(f"- {b}" for b in bullets) + "\n")
            listing_md.append(f"### 详情\n{fields.get('description', '')}\n")
            faq = fields.get("faq") or []
            if isinstance(faq, list):
                listing_md.append("### FAQ\n" + "\n".join(
                    f"- Q: {p[0]}\n  A: {p[1]}" for p in faq if isinstance(p, list) and len(p) >= 2) + "\n")
            if fields.get("search_terms"):
                listing_md.append(f"### 后台搜索词\n{fields['search_terms']}\n")
            if fields.get("image_alt"):
                listing_md.append(f"### 图片 ALT\n{fields['image_alt']}\n")
            if v.localization_note:
                listing_md.append(f"### 本地化说明\n{v.localization_note}\n")
        zf.writestr("02_listings.md", "".join(listing_md))

        # 3. SEO 关键词与标题候选
        kws = db.query(SeoKeyword).filter(SeoKeyword.product_id == product_id).all()
        kw_lines = ["关键词,类型,来源,必须包含,禁用,备注"]
        for k in kws:
            kw_lines.append(csv_safe(",".join([
                k.keyword, k.kw_type, k.source, "是" if k.must_include else "否",
                "是" if k.banned else "否", k.note])))
        titles = db.query(TitleCandidate).filter(TitleCandidate.product_id == product_id).all()
        kw_lines.append("\n标题候选,评分")
        for t in titles:
            kw_lines.append(csv_safe(f"{t.title},{t.scores.get('overall', '')}"))
        zf.writestr("03_seo_keywords.csv", "\n".join(kw_lines))

        # 4. 生成图片（按类型分目录）
        images = db.query(GeneratedImage).filter(
            GeneratedImage.product_id == product_id).all()
        for im in images:
            try:
                zf.writestr(f"04_images/{im.image_type}/{im.market}/{im.filename}",
                            storage.read(im.path))
            except Exception:  # noqa: BLE001
                continue

        # 5. 审核报告
        reviews = db.query(ReviewItem).filter(ReviewItem.product_id == product_id).all()
        report = {
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "note": "AI 检查不能替代平台官方审核；needs_manual=true 的项必须人工核实",
            "items": [{"target": r.target_type, "level": r.level, "code": r.rule_code,
                       "reason": r.reason, "location": r.location,
                       "suggestion": r.suggestion, "needs_manual": r.needs_manual,
                       "status": r.status} for r in reviews],
        }
        zf.writestr("05_review_report.json", json.dumps(report, ensure_ascii=False, indent=2))

        # 6. 原始图片
        for im in product.images:
            try:
                zf.writestr(f"06_original_images/{im.kind}/{im.filename}", storage.read(im.path))
            except Exception:  # noqa: BLE001
                continue

    task.file_path = rel_path(target)
    task.file_name = target.name
    task.file_size = target.stat().st_size
    task.status = "completed"
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return task
