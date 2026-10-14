"""商品管理：SKU CRUD、批量导入（CSV/XLSX/TXT）、图片上传与管理、参数提取。"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, ProductImage, ProductParam
from ..schemas import (ImportResult, ProductCreate, ProductOut, ProductParamIn,
                       ProductUpdate, ProductBrief)
from ..security import ext_of, validate_image_upload
from ..serializers import product_out as _to_out
from ..services.listing_service import extract_params_from_text
from ..services.storage import get_storage, new_filename
from ..config import IMAGES_DIR

router = APIRouter(prefix="/api/products", tags=["商品管理"])

_KIND_MAP = {"main": "main", "主图": "main", "实物": "实物", "细节": "细节",
             "包装": "包装", "场景": "场景", "logo": "logo", "参考": "参考"}


@router.get("", response_model=list[ProductBrief])
def list_products(q: str = "", db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.status == "active")
    if q:
        like = f"%{q}%"
        query = query.filter((Product.sku.like(like)) | (Product.name.like(like)))
    products = query.order_by(Product.created_at.desc()).all()
    return [ProductBrief(id=p.id, sku=p.sku, name=p.name, brand=p.brand,
                         category=p.category, image_count=len(p.images),
                         is_demo=p.is_demo, created_at=p.created_at) for p in products]


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    exists = db.query(Product).filter(Product.sku == payload.sku).first()
    if exists:
        raise HTTPException(409, f"SKU {payload.sku} 已存在")
    p = Product(sku=payload.sku, name=payload.name, brand=payload.brand,
                model=payload.model, category=payload.category,
                source_text=payload.source_text)
    db.add(p)
    db.flush()
    for param in payload.params:
        db.add(ProductParam(product_id=p.id, **param.model_dump()))
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    return _to_out(p)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """删除商品并清理关联图片文件与生成数据。"""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    storage = get_storage()
    for im in p.images:
        storage.delete(im.path)
    from ..models import GeneratedImage
    for gim in db.query(GeneratedImage).filter(GeneratedImage.product_id == product_id).all():
        storage.delete(gim.path)
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted": product_id}


# ---------------------------------------------------------------- 参数
@router.post("/{product_id}/params", response_model=ProductOut)
def add_params(product_id: int, params: list[ProductParamIn], db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    for param in params:
        db.add(ProductParam(product_id=p.id, **param.model_dump()))
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{product_id}/params/{param_id}", response_model=ProductOut)
def delete_param(product_id: int, param_id: int, db: Session = Depends(get_db)):
    param = db.get(ProductParam, param_id)
    if not param or param.product_id != product_id:
        raise HTTPException(404, "参数不存在")
    db.delete(param)
    db.commit()
    db.refresh(db.get(Product, product_id))
    return _to_out(db.get(Product, product_id))


@router.post("/{product_id}/extract-params", response_model=ProductOut)
def extract_params(product_id: int, db: Session = Depends(get_db)):
    """从商品中文详情中提取结构化参数（提取结果未验证，需用户确认）。"""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    if not p.source_text.strip():
        raise HTTPException(400, "请先填写商品中文详情")
    extracted = extract_params_from_text(p.source_text)
    existing = {x.key for x in p.params}
    added = 0
    for e in extracted:
        if e.key not in existing:
            db.add(ProductParam(product_id=p.id, **e.model_dump()))
            added += 1
    db.commit()
    db.refresh(p)
    return _to_out(p)


# ---------------------------------------------------------------- 图片
@router.post("/{product_id}/images", response_model=ProductOut)
async def upload_image(product_id: int, file: UploadFile = File(...),
                       kind: str = Form("main"), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    try:
        content, ext = await validate_image_upload(file)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    from PIL import Image
    with Image.open(io.BytesIO(content)) as im:
        w, h = im.size
    storage = get_storage()
    filename = new_filename(f"{p.sku}_{kind}", ext)
    rel = storage.save_image(content, filename, f"products/{p.id}/original")
    db.add(ProductImage(product_id=p.id, kind=_KIND_MAP.get(kind, kind),
                        filename=filename, path=rel, mime=file.content_type or "",
                        size=len(content), width=w, height=h))
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{product_id}/images/{image_id}", response_model=ProductOut)
def delete_image(product_id: int, image_id: int, db: Session = Depends(get_db)):
    im = db.get(ProductImage, image_id)
    if not im or im.product_id != product_id:
        raise HTTPException(404, "图片不存在")
    get_storage().delete(im.path)
    db.delete(im)
    db.commit()
    db.refresh(db.get(Product, product_id))
    return _to_out(db.get(Product, product_id))


# ---------------------------------------------------------------- 批量导入
@router.post("/import", response_model=ImportResult)
async def import_products(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """批量导入 SKU：支持 CSV / XLSX / TXT。

    CSV/XLSX 需包含 sku 列（可选 name/brand/model/category/source_text 列）；
    TXT 按“SKU||名称||品牌||型号||类目||中文详情”每行一个商品。
    """
    ext = ext_of(file.filename or "")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "导入文件超过 20MB 限制")
    result = ImportResult()
    rows: list[dict] = []

    try:
        if ext in ("csv", "txt"):
            text = content.decode("utf-8-sig")
            if ext == "txt":
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = [x.strip() for x in line.split("||")]
                    rows.append({"sku": parts[0] if parts else "",
                                 "name": parts[1] if len(parts) > 1 else "",
                                 "brand": parts[2] if len(parts) > 2 else "",
                                 "model": parts[3] if len(parts) > 3 else "",
                                 "category": parts[4] if len(parts) > 4 else "",
                                 "source_text": parts[5] if len(parts) > 5 else ""})
            else:
                import pandas as pd
                df = pd.read_csv(io.BytesIO(content)).fillna("")
                rows = df.to_dict(orient="records")
        elif ext in ("xlsx", "xls"):
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content)).fillna("")
            rows = df.to_dict(orient="records")
        else:
            raise HTTPException(400, f"不支持的导入格式 .{ext}，支持 csv/xlsx/txt")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"文件解析失败：{e}") from e

    for i, row in enumerate(rows):
        sku = str(row.get("sku") or row.get("SKU") or "").strip()
        if not sku:
            result.skipped += 1
            result.errors.append(f"第 {i + 1} 行缺少 SKU，已跳过")
            continue
        if db.query(Product).filter(Product.sku == sku).first():
            result.skipped += 1
            result.errors.append(f"SKU {sku} 已存在，已跳过")
            continue
        try:
            p = Product(
                sku=sku[:64],
                name=str(row.get("name") or row.get("名称") or "")[:255],
                brand=str(row.get("brand") or row.get("品牌") or "")[:128],
                model=str(row.get("model") or row.get("型号") or "")[:128],
                category=str(row.get("category") or row.get("类目") or "")[:128],
                source_text=str(row.get("source_text") or row.get("中文详情") or ""),
            )
            db.add(p)
            db.flush()
            result.imported += 1
            result.product_ids.append(p.id)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"SKU {sku} 导入失败：{e}")
    db.commit()
    return result
