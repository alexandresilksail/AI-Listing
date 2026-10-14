"""导出中心：Listing XLSX/CSV、图片 ZIP、完整商品包。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ExportTask, Product
from ..schemas import ExportCreate, ExportTaskOut
from ..services.export_service import (export_full_package, export_images_zip,
                                       export_listing)

router = APIRouter(prefix="/api/exports", tags=["导出中心"])


def _out(t: ExportTask) -> ExportTaskOut:
    out = ExportTaskOut.model_validate(t)
    if t.file_path and t.status == "completed":
        out.download_url = f"/api/files/export/{t.id}"
    return out


@router.post("", response_model=ExportTaskOut)
def create_export(payload: ExportCreate, db: Session = Depends(get_db)):
    if payload.type == "full_package":
        if not payload.product_id:
            raise HTTPException(400, "完整商品包必须指定商品")
        if not db.get(Product, payload.product_id):
            raise HTTPException(404, "商品不存在")
    task = ExportTask(type=payload.type,
                      params=payload.model_dump(exclude={"type"}),
                      status="processing")
    db.add(task)
    db.commit()
    db.refresh(task)
    try:
        if payload.type in ("listing_csv", "listing_xlsx"):
            fmt = "csv" if payload.type == "listing_csv" else "xlsx"
            export_listing(db, task.id, fmt, payload.product_id, payload.market,
                           payload.platform)
        elif payload.type == "images_zip":
            export_images_zip(db, task.id, payload.image_ids or None,
                              payload.product_id, payload.market)
        else:
            export_full_package(db, task.id, payload.product_id)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        task.status = "failed"
        task.error = str(e)
        db.commit()
    db.refresh(task)
    return _out(task)


@router.get("", response_model=list[ExportTaskOut])
def list_exports(db: Session = Depends(get_db)):
    return [_out(t) for t in db.query(ExportTask).order_by(
        ExportTask.created_at.desc()).limit(100).all()]


@router.get("/{export_id}", response_model=ExportTaskOut)
def get_export(export_id: int, db: Session = Depends(get_db)):
    t = db.get(ExportTask, export_id)
    if not t:
        raise HTTPException(404, "导出任务不存在")
    return _out(t)
