"""安全工具：API 鉴权辅助、上传文件校验、SSRF 防护、路径穿越防护、
CSV 公式注入防护、密钥脱敏与日志过滤。"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
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

# 私有/保留网段（SSRF 防护）
_BLOCKED_NETS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # 云元数据等高危链路本地地址
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),      # 多播
    ipaddress.ip_network("240.0.0.0/4"),      # 保留
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),         # IPv6 唯一本地地址
    ipaddress.ip_network("fe80::/10"),        # IPv6 链路本地
    ipaddress.ip_network("::ffff:0:0/96"),    # IPv4 映射地址单独校验
]


def ext_of(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def sniff_image_ext(header: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if header.startswith(magic):
            return ext
    return None


# ---------------------------------------------------------------- 上传校验
async def validate_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """校验上传图片：扩展名、大小、魔数、PIL 解码、像素上限。

    返回 (内容, 扩展名)。任何一步不满足都抛出 ValueError（调用方转 400）。
    """
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
    if sniffed == "webp" and content[8:12] != b"WEBP":
        raise ValueError("文件内容不是有效的 WEBP 图片")
    # PIL 完整解码校验：能通过魔数但无法解码的畸形文件必须拒绝
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = s.max_image_pixels  # 防解压炸弹
    try:
        with Image.open(io_bytes(content)) as im:
            im.load()
            w, h = im.size
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"图片解码失败，文件可能已损坏：{e}") from e
    if w * h > s.max_image_pixels:
        raise ValueError(f"图片像素超过上限（最大 {s.max_image_pixels // 1_000_000}MP）")
    return content, sniffed


def io_bytes(content: bytes):
    import io
    return io.BytesIO(content)


def verify_image_bytes(content: bytes) -> tuple[int, int]:
    """校验任意字节流是否为可解码图片，返回 (宽, 高)；失败抛 ValueError。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = effective_settings().max_image_pixels
    try:
        with Image.open(io_bytes(content)) as im:
            im.load()
            return im.size
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"不是可解码的图片：{e}") from e


# ---------------------------------------------------------------- SSRF 防护
def _ip_blocked(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True  # 无法解析视为不安全
    if ip.version == 4 and ip_text.startswith("::ffff:"):
        ip = ipaddress.ip_address(ip_text.split("::ffff:")[-1])
    for net in _BLOCKED_NETS:
        if ip.version == net.version and ip in net:
            return True
    return False


def assert_url_allowed(url: str, *, allow_insecure: bool | None = None) -> None:
    """校验 URL 是否允许服务端访问（防 SSRF）。

    - 生产仅允许 https；allow_insecure=True（开发调试）时允许 http
    - 主机名解析后的所有 IP 都不得处于私有/环回/链路本地/保留网段
      （allow_insecure=True 时跳过内网检查，仅限本地联调）
    """
    s = effective_settings()
    insecure = s.allow_insecure_download if allow_insecure is None else allow_insecure
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"不允许的 URL 协议：{parsed.scheme or '?'}（仅支持 https）")
    if parsed.scheme == "http" and not insecure:
        raise ValueError("不允许的 URL 协议：http（生产仅支持 https；开发可设置 PL_ALLOW_INSECURE_DOWNLOAD=true）")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    if insecure:
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"主机名解析失败：{host}") from e
    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise ValueError(f"主机名无解析结果：{host}")
    for ip_text in resolved:
        if _ip_blocked(ip_text):
            raise ValueError(f"URL 指向不允许访问的地址（{host} → {ip_text}）")


def safe_download(url: str, *, max_bytes: int | None = None,
                  timeout: int = 60) -> bytes:
    """安全下载模型返回的图片 URL：SSRF 校验 + 大小上限 + 重定向管控。

    - 首次请求前校验 URL；重定向目标逐跳校验（最多 5 跳）
    - 流式读取，超过 max_bytes 立即中断
    - insecure 模式（开发调试）下锁定主机：重定向不得跳转到其他主机，
      防止利用本地白名单跳转到云元数据等内网地址
    - 同步实现（调用链运行在 worker 线程中）
    """
    from urllib.parse import urlparse
    s = effective_settings()
    limit = max_bytes if max_bytes is not None else s.max_download_mb * 1024 * 1024
    current = url
    locked_host = urlparse(url).hostname if s.allow_insecure_download else None
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _hop in range(6):
            assert_url_allowed(current)
            if locked_host and urlparse(current).hostname != locked_host:
                raise ValueError(f"重定向跳转到了其他主机（{urlparse(current).hostname}），已拒绝")
            with client.stream("GET", current) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("重定向缺少 Location 头")
                    current = str(resp.url.join(location))
                    continue
                if resp.status_code >= 400:
                    raise ValueError(f"下载失败：HTTP {resp.status_code}")
                declared = resp.headers.get("content-length")
                if declared and int(declared) > limit:
                    raise ValueError(f"响应体超过大小上限（{limit // 1024 // 1024}MB）")
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ValueError(f"响应体超过大小上限（{limit // 1024 // 1024}MB）")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise ValueError("重定向次数过多")


# ---------------------------------------------------------------- 路径与文件
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


def scrub_secrets(text: str, *secrets: str) -> str:
    """把文本中出现的密钥替换为 ****，用于错误信息与日志，防止泄露。"""
    if not text:
        return text
    for sec in secrets:
        if sec and len(sec) >= 6 and sec in text:
            text = text.replace(sec, "****")
    return text
