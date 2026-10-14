"""Listing 生成：任务提交、版本管理、编辑、单字段重生成。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import MARKET_LANGUAGES
from ..database import get_db
from ..models import ListingTask, ListingVersion, Product
from ..schemas import ListingEdit, ListingTaskCreate, ListingTaskOut, ListingVersionOut
from ..serializers import listing_task_out as _task_out
from ..serializers import version_out
from ..services.listing_service import edit_listing, regenerate_field
from ..services.task_queue import TaskQueue, get_queue

router = APIRouter(prefix="/api/listings", tags=["Listing 生成"])


@router.post("/tasks", response_model=list[ListingTaskOut])
def create_tasks(payload: ListingTaskCreate, db: Session = Depends(get_db)):
    """为同一 SKU 的多个市场一次性批量创建 Listing 生成任务。"""
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(404, "商品不存在")
    for m in payload.markets:
        if m not in MARKET_LANGUAGES:
            raise HTTPException(400, f"不支持的市场代码 {m}")
    queue = get_queue()
    out = []
    for market in payload.markets:
        lang = MARKET_LANGUAGES[market]["language"]
        # 去重：同商品+平台+市场已有进行中任务则不重复提交
        existing = db.query(ListingTask).filter(
            ListingTask.product_id == payload.product_id,
            ListingTask.platform == payload.platform,
            ListingTask.market == market,
            ListingTask.status.in_(["pending", "processing"])).first()
        if existing:
            out.append(_task_out(existing))
            continue
        task = ListingTask(product_id=payload.product_id, platform=payload.platform,
                           market=market, language=lang, status="pending",
                           idempotency_key=payload.idempotency_key or "")
        db.add(task)
        db.commit()
        db.refresh(task)
        queue.submit("listing", task.id,
                     payload.idempotency_key or f"listing:{task.id}")
        out.append(_task_out(task))
    return out


@router.get("/tasks", response_model=list[ListingTaskOut])
def list_tasks(product_id: int | None = None, status: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(ListingTask)
    if product_id:
        q = q.filter(ListingTask.product_id == product_id)
    if status:
        q = q.filter(ListingTask.status == status)
    return [_task_out(t) for t in q.order_by(ListingTask.created_at.desc()).limit(200).all()]


@router.get("/tasks/{task_id}", response_model=ListingTaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ListingTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return _task_out(t)


@router.post("/tasks/{task_id}/retry", response_model=ListingTaskOut)
def retry_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ListingTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in ("pending", "processing"):
        raise HTTPException(409, "任务正在进行中")
    # 失败任务保留已成功产出的原则：重试会生成新版本，旧版本保留
    t.status = "pending"
    t.error = ""
    db.commit()
    get_queue().retry("listing", task_id)
    db.refresh(t)
    return _task_out(t)


@router.get("/versions", response_model=list[ListingVersionOut])
def list_versions(product_id: int, db: Session = Depends(get_db)):
    versions = db.query(ListingVersion).filter(
        ListingVersion.product_id == product_id).order_by(
        ListingVersion.created_at.desc()).limit(100).all()
    return [version_out(v) for v in versions]


@router.get("/versions/{version_id}", response_model=ListingVersionOut)
def get_version(version_id: int, db: Session = Depends(get_db)):
    v = db.get(ListingVersion, version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return version_out(v)


@router.post("/versions/{version_id}/edit", response_model=ListingVersionOut)
def edit_version(version_id: int, payload: ListingEdit, db: Session = Depends(get_db)):
    try:
        v = edit_listing(db, version_id, [p.model_dump() for p in payload.fields], payload.note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return version_out(v)


@router.post("/versions/{version_id}/regenerate")
def regen_field(version_id: int, field: str, db: Session = Depends(get_db)):
    try:
        return regenerate_field(db, version_id, field)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/versions/{version_id}/review")
def review_version(version_id: int, db: Session = Depends(get_db)):
    """手动触发文案审核。"""
    from ..services.review_service import review_listing_version
    items = review_listing_version(db, version_id)
    return {"checked": len(items),
            "high": sum(1 for i in items if i.level == "high"),
            "medium": sum(1 for i in items if i.level == "medium"),
            "low": sum(1 for i in items if i.level == "low")}


@router.get("/diff/{old_id}/{new_id}")
def diff_versions(old_id: int, new_id: int, db: Session = Depends(get_db)):
    """版本对比：逐字段差异。"""
    old = db.get(ListingVersion, old_id)
    new = db.get(ListingVersion, new_id)
    if not old or not new:
        raise HTTPException(404, "版本不存在")
    old_fields = {f.field: f.content for f in old.fields}
    new_fields = {f.field: f.content for f in new.fields}
    diffs = []
    for key in sorted(set(old_fields) | set(new_fields)):
        o, n = old_fields.get(key), new_fields.get(key)
        if o != n:
            diffs.append({"field": key, "old": o, "new": n})
    return {"old_version": old.version, "new_version": new.version, "diffs": diffs}
