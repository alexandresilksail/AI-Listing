"""审核中心：风险项列表与人工处理。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ReviewItem
from ..schemas import ReviewItemOut, ReviewPatch

router = APIRouter(prefix="/api/reviews", tags=["审核中心"])


@router.get("", response_model=list[ReviewItemOut])
def list_reviews(target_type: str | None = None, product_id: int | None = None,
                 level: str | None = None, status: str = "open",
                 db: Session = Depends(get_db)):
    q = db.query(ReviewItem)
    if target_type:
        q = q.filter(ReviewItem.target_type == target_type)
    if product_id:
        q = q.filter(ReviewItem.product_id == product_id)
    if level:
        q = q.filter(ReviewItem.level == level)
    if status:
        q = q.filter(ReviewItem.status == status)
    return q.order_by(ReviewItem.created_at.desc()).limit(500).all()


@router.patch("/{review_id}", response_model=ReviewItemOut)
def patch_review(review_id: int, payload: ReviewPatch, db: Session = Depends(get_db)):
    item = db.get(ReviewItem, review_id)
    if not item:
        raise HTTPException(404, "审核项不存在")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return item


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    rows = db.query(ReviewItem).filter(ReviewItem.status == "open").all()
    return {
        "total": len(rows),
        "high": sum(1 for r in rows if r.level == "high"),
        "medium": sum(1 for r in rows if r.level == "medium"),
        "low": sum(1 for r in rows if r.level == "low"),
        "info": sum(1 for r in rows if r.level == "info"),
        "needs_manual": sum(1 for r in rows if r.needs_manual),
    }
