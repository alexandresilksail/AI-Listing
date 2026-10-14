"""图片工作台：生成任务、版本管理、人工审核状态。"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import MARKET_LANGUAGES
from ..database import get_db
from ..models import GeneratedImage, ImageGenTask, Product
from ..schemas import GeneratedImageOut, ImageReviewPatch, ImageTaskCreate, ImageTaskOut
from ..serializers import generated_image_out, image_task_out
from ..services.review_service import review_generated_image
from ..services.task_queue import get_queue

router = APIRouter(prefix="/api/images", tags=["图片工作台"])

_VALID_TYPES = {"main", "scene", "selling", "info", "brand", "localize"}
_VALID_RATIOS = {"1:1", "3:4", "4:3", "9:16", "16:9"}

# 提交锁：串行化“查重 + 落库”，消除并发重复提交竞态（防重复扣费）
_submit_lock = threading.Lock()


@router.post("/tasks", response_model=ImageTaskOut)
def create_task(payload: ImageTaskCreate, db: Session = Depends(get_db)):
    if not db.get(Product, payload.product_id):
        raise HTTPException(404, "商品不存在")
    if payload.image_type not in _VALID_TYPES:
        raise HTTPException(400, f"不支持的图片类型 {payload.image_type}")
    if payload.market not in MARKET_LANGUAGES:
        raise HTTPException(400, f"不支持的市场代码 {payload.market}")
    if payload.aspect_ratio not in _VALID_RATIOS:
        raise HTTPException(400, f"不支持的画幅比例 {payload.aspect_ratio}")

    with _submit_lock:
        # 去重：同商品+类型+市场+比例+提示词 已有进行中任务则不重复提交
        existing = db.query(ImageGenTask).filter(
            ImageGenTask.product_id == payload.product_id,
            ImageGenTask.image_type == payload.image_type,
            ImageGenTask.market == payload.market,
            ImageGenTask.aspect_ratio == payload.aspect_ratio,
            ImageGenTask.status.in_(["pending", "processing"])).first()
        if existing:
            return image_task_out(existing)

        task = ImageGenTask(
            product_id=payload.product_id, image_type=payload.image_type,
            platform=payload.platform, market=payload.market,
            language=MARKET_LANGUAGES[payload.market]["language"],
            aspect_ratio=payload.aspect_ratio, count=payload.count,
            style=payload.style, background=payload.background,
            prompt=payload.prompt, ref_image_ids=payload.ref_image_ids,
            status="pending")
        db.add(task)
        db.commit()
        db.refresh(task)
        get_queue().submit("image", task.id, payload.idempotency_key or f"image:{task.id}")
    return image_task_out(task)


@router.get("/tasks", response_model=list[ImageTaskOut])
def list_tasks(product_id: int | None = None, status: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(ImageGenTask)
    if product_id:
        q = q.filter(ImageGenTask.product_id == product_id)
    if status:
        q = q.filter(ImageGenTask.status == status)
    return [image_task_out(t) for t in q.order_by(ImageGenTask.created_at.desc()).limit(200).all()]


@router.get("/tasks/{task_id}", response_model=ImageTaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ImageGenTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return image_task_out(t)


@router.post("/tasks/{task_id}/retry", response_model=ImageTaskOut)
def retry_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ImageGenTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in ("pending", "processing"):
        raise HTTPException(409, "任务正在进行中")
    t.status = "pending"
    t.error = ""
    db.commit()
    get_queue().retry("image", task_id)
    db.refresh(t)
    return image_task_out(t)


@router.get("/generated", response_model=list[GeneratedImageOut])
def list_generated(product_id: int | None = None, market: str | None = None,
                   image_type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(GeneratedImage)
    if product_id:
        q = q.filter(GeneratedImage.product_id == product_id)
    if market:
        q = q.filter(GeneratedImage.market == market)
    if image_type:
        q = q.filter(GeneratedImage.image_type == image_type)
    rows = q.order_by(GeneratedImage.created_at.desc()).limit(500).all()
    return [generated_image_out(r) for r in rows]


@router.patch("/generated/{image_id}", response_model=GeneratedImageOut)
def review_image(image_id: int, payload: ImageReviewPatch, db: Session = Depends(get_db)):
    im = db.get(GeneratedImage, image_id)
    if not im:
        raise HTTPException(404, "生成图片不存在")
    im.review_status = payload.review_status
    db.commit()
    db.refresh(im)
    return generated_image_out(im)


@router.post("/generated/{image_id}/recheck")
def recheck_image(image_id: int, db: Session = Depends(get_db)):
    items = review_generated_image(db, image_id)
    return {"checked": len(items)}
