"""存储服务：可替换存储接口。开发环境使用本地文件系统，生产可扩展对象存储。"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Protocol

from ..config import EXPORTS_DIR, IMAGES_DIR, UPLOADS_DIR
from ..security import safe_join, sanitize_filename


class StorageBackend(Protocol):
    def save_image(self, content: bytes, filename: str, subdir: str = "") -> str: ...
    def save_export(self, src_path: Path, filename: str) -> str: ...
    def read(self, rel_path: str) -> bytes: ...
    def abs_path(self, rel_path: str) -> Path: ...
    def delete(self, rel_path: str) -> None: ...


class LocalStorage:
    """本地文件系统存储。rel_path 为相对存储根的路径（防穿越）。"""

    def __init__(self) -> None:
        # resolve() 统一 Windows 短路径/长路径大小写，避免 relative_to 失败
        self.images_root = IMAGES_DIR.resolve()
        self.exports_root = EXPORTS_DIR.resolve()
        self.uploads_root = UPLOADS_DIR.resolve()
        self.root = self.images_root.parent
        for d in (self.images_root, self.exports_root, self.uploads_root):
            d.mkdir(parents=True, exist_ok=True)

    def save_image(self, content: bytes, filename: str, subdir: str = "") -> str:
        safe_name = sanitize_filename(filename)
        target_dir = safe_join(self.images_root, subdir) if subdir else self.images_root
        target_dir.mkdir(parents=True, exist_ok=True)
        target = safe_join(target_dir, safe_name)
        target.write_bytes(content)
        return str(target.resolve().relative_to(self.root)).replace("\\", "/")

    def save_export(self, src_path: Path, filename: str) -> str:
        safe_name = sanitize_filename(filename)
        target = safe_join(self.exports_root, safe_name)
        shutil.copyfile(src_path, target)
        return str(target.relative_to(self.root)).replace("\\", "/")

    def read(self, rel_path: str) -> bytes:
        return self.abs_path(rel_path).read_bytes()

    def abs_path(self, rel_path: str) -> Path:
        # rel_path 形如 images/xxx.png 或 exports/xxx.zip
        parts = rel_path.replace("\\", "/").split("/")
        if parts[0] not in ("images", "exports", "uploads"):
            raise ValueError("非法存储路径")
        root = {"images": self.images_root, "exports": self.exports_root,
                "uploads": self.uploads_root}[parts[0]]
        return safe_join(root, *parts[1:])

    def delete(self, rel_path: str) -> None:
        try:
            p = self.abs_path(rel_path)
            if p.exists():
                p.unlink()
        except Exception:
            pass


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage


def new_filename(prefix: str, ext: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"


def rel_path(target: "Path") -> str:
    """把绝对路径转换为相对 data 根的存储路径（统一 resolve，兼容 Windows 短路径）。"""
    root = EXPORTS_DIR.resolve().parent
    return str(Path(target).resolve().relative_to(root)).replace("\\", "/")
