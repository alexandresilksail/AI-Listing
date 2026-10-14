"""批量任务中心：状态总览与重试。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ImageGenTask, ListingTask
from ..schemas import TaskStatusOut
from ..services.task_queue import TaskQueue, get_queue

router = APIRouter(prefix="/api/tasks", tags=["批量任务"])


def _status_counts(db: Session, model) -> TaskStatusOut:
    rows = db.query(model.status, model.id).all()
    out = TaskStatusOut()
    for status, _ in rows:
        if status == "pending":
            out.pending += 1
        elif status == "processing":
            out.processing += 1
        elif status == "completed":
            out.completed += 1
        elif status == "partial":
            out.partial += 1
        elif status == "failed":
            out.failed += 1
    return out


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return {
        "listing_tasks": _status_counts(db, ListingTask),
        "image_tasks": _status_counts(db, ImageGenTask),
        "today_spend_usd": TaskQueue.today_spend_usd(),
        "today_unknown_cost_calls": TaskQueue.today_unknown_cost_calls(),
    }


@router.post("/listing/{task_id}/retry")
def retry_listing(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ListingTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in ("pending", "processing"):
        raise HTTPException(409, "任务正在进行中")
    t.status = "pending"
    t.error = ""
    db.commit()
    get_queue().retry("listing", task_id)
    return {"ok": True, "task_id": task_id}


@router.post("/image/{task_id}/retry")
def retry_image(task_id: int, db: Session = Depends(get_db)):
    t = db.get(ImageGenTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in ("pending", "processing"):
        raise HTTPException(409, "任务正在进行中")
    t.status = "pending"
    t.error = ""
    db.commit()
    get_queue().retry("image", task_id)
    return {"ok": True, "task_id": task_id}
