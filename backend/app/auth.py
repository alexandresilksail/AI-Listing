"""统一 API 鉴权。

设计边界（单租户部署）：
- 本应用为单租户工具，未实现多用户系统。所有 /api/* 管理接口由同一枚 API 令牌保护。
- 生产模式（PL_ENV=production）必须在启动时配置 PL_API_TOKEN，否则拒绝启动（fail-fast）；
  绝不存在“因为令牌为空就公开管理接口”的生产状态。
- development 模式下允许无令牌访问（仅限本机开发），每次启动会输出醒目警告。

使用方式：
- 请求头 `Authorization: Bearer <token>` 或 `X-API-Token: <token>`。
- /api/health 与 /api/meta 为公开探活端点（不返回任何敏感信息）。
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Depends, HTTPException, Request, status

from .config import effective_settings

logger = logging.getLogger("polylisting.auth")

# 公开端点（探活与前端静态元信息，不含敏感数据）
PUBLIC_PATHS = {"/api/health", "/api/meta"}


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-token") or "").strip()


async def require_api_token(request: Request) -> None:
    """FastAPI 依赖：校验 API 令牌。作为全局依赖挂载到 app 上。"""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return
    s = effective_settings()
    if not s.api_token:
        # 未配置令牌：仅 development 放行，production 已在启动时 fail-fast
        if s.is_production:  # 双保险，理论上启动时已被拦截
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "服务未配置访问令牌，已拒绝请求")
        return
    supplied = _extract_token(request)
    if not supplied:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "缺少访问令牌：请在请求头携带 Authorization: Bearer <PL_API_TOKEN> 或 X-API-Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(supplied, s.api_token):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "访问令牌无效",
            headers={"WWW-Authenticate": "Bearer"})


def warn_if_insecure() -> None:
    """开发模式无令牌启动时输出醒目警告。"""
    s = effective_settings()
    if not s.api_token and not s.is_production:
        logger.warning(
            "⚠️  当前为 development 模式且未配置 PL_API_TOKEN，所有管理接口无鉴权开放。"
            "请勿将此配置暴露到公网。生产部署必须设置 PL_ENV=production 与 PL_API_TOKEN。")
