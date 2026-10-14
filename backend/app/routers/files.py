"""文件服务：原图/生成图/导出文件的安全下载（防路径穿越）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from ..database import get_db
from ..models import ExportTask, GeneratedImage, ProductImage
from ..services.storage import get_storage
from ..security import safe_join
from ..config import EXPORTS_DIR
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter(prefix="/api/files", tags=["文件服务"])


@router.get("/image/{image_id}")
def get_image(image_id: int, db: Session = Depends(get_db)):
    im = db.get(ProductImage, image_id)
    if im:
        storage = get_storage()
        return Response(content=storage.read(im.path), media_type=im.mime or "image/jpeg")
    gim = db.get(GeneratedImage, image_id)
    if gim:
        storage = get_storage()
        return Response(content=storage.read(gim.path), media_type="image/png")
    raise HTTPException(404, "图片不存在")


@router.get("/generated/{image_id}")
def get_generated_image(image_id: int, db: Session = Depends(get_db)):
    gim = db.get(GeneratedImage, image_id)
    if not gim:
        raise HTTPException(404, "生成图片不存在")
    return Response(content=get_storage().read(gim.path), media_type="image/png")


@router.get("/export/{export_id}")
def download_export(export_id: int, db: Session = Depends(get_db)):
    task = db.get(ExportTask, export_id)
    if not task or not task.file_path:
        raise HTTPException(404, "导出文件不存在")
    storage = get_storage()
    try:
        path = storage.abs_path(task.file_path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not path.exists():
        raise HTTPException(410, "文件已被清理，请重新导出")
    return FileResponse(path, filename=task.file_name or path.name)
