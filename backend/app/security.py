"""安全工具：上传文件校验、路径穿越防护、CSV 公式注入防护、密钥脱敏。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import UploadFile

from .config import effective_settings

# 图片文件魔数（magic bytes）
_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"RIFF": "webp",  # WEBP: RIFF....WEBP
}

# CSV 公式注入危险前缀
_CSV_FORMULA_RE = re.compile(r"^[=+\-@\t\r]")


def ext_of(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def sniff_image_ext(header: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if header.startswith(magic):
            return ext
    return None


async def validate_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """校验上传图片：扩展名、大小、魔数。返回 (内容, 扩展名)。"""
    s = effective_settings()
    ext = ext_of(file.filename or "")
    if ext not in s.allowed_image_ext:
        raise ValueError(f"不支持的图片格式 .{ext or '?'}，仅支持 {', '.join(s.allowed_image_ext)}")
    content = await file.read()
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise ValueError(f"图片超过大小限制（最大 {s.max_upload_mb}MB）")
    if len(content) < 12:
        raise ValueError("文件内容过小，不是有效图片")
    sniffed = sniff_image_ext(content[:16])
    if sniffed is None:
        raise ValueError("文件内容不是有效的图片（魔数校验失败）")
    # WEBP 需进一步校验
    if sniffed == "webp" and content[8:12] != b"WEBP":
        raise ValueError("文件内容不是有效的 WEBP 图片")
    # jpeg 保存为 .jpg 统一扩展名
    if sniffed == "jpg":
        sniffed = "jpg"
    return content, sniffed


def safe_join(base: Path, *parts: str) -> Path:
    """防止路径穿越：拼接后必须仍在 base 内。"""
    base = base.resolve()
    target = (base.joinpath(*parts)).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("非法路径")
    return target


def sanitize_filename(name: str) -> str:
    """清洗文件名中的危险字符。"""
    name = re.sub(r"[^\w\-.]+", "_", name, flags=re.UNICODE).strip("._")
    return name[:120] or "file"


def csv_safe(value) -> str:
    """防止 CSV 公式注入：危险前缀加单引号前缀。"""
    if value is None:
        return ""
    s = str(value)
    if _CSV_FORMULA_RE.match(s):
        return "'" + s
    return s


def mask_secret(secret: str) -> str:
    """密钥脱敏展示。"""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return secret[:4] + "****" + secret[-4:]
