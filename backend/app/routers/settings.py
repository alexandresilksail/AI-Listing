"""模型设置：API 配置（密钥仅服务端保存，输出永远脱敏）+ 连通性测试。"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import (effective_settings, load_runtime_settings, save_runtime_settings)
from ..database import get_db
from ..models import ApiCallLog
from ..schemas import ModelSettingsIn, ModelSettingsOut
from ..security import mask_secret

router = APIRouter(prefix="/api/settings", tags=["模型设置"])


@router.get("", response_model=ModelSettingsOut)
def get_model_settings():
    s = effective_settings()
    return ModelSettingsOut(
        text_configured=s.text_configured, image_configured=s.image_configured,
        text_api_base=s.text_api_base, text_api_key_masked=mask_secret(s.text_api_key),
        text_model=s.text_model,
        image_api_base=s.image_api_base, image_api_key_masked=mask_secret(s.image_api_key),
        image_model=s.image_model,
        daily_budget_usd=s.daily_budget_usd, per_task_budget_usd=s.per_task_budget_usd,
        max_skus_per_task=s.max_skus_per_task, max_upload_mb=s.max_upload_mb)


@router.put("", response_model=ModelSettingsOut)
def update_model_settings(payload: ModelSettingsIn):
    rt = load_runtime_settings()
    # 密钥留空表示不修改
    for k in ("text_api_base", "text_model", "image_api_base", "image_model",
              "daily_budget_usd", "per_task_budget_usd", "max_skus_per_task", "max_upload_mb"):
        setattr_val = getattr(payload, k)
        if setattr_val not in (None, ""):
            rt[k] = setattr_val
    if payload.text_api_key:
        rt["text_api_key"] = payload.text_api_key
    if payload.image_api_key:
        rt["image_api_key"] = payload.image_api_key
    save_runtime_settings(rt)
    return get_model_settings()


@router.post("/test")
def test_connection(kind: str = "text"):
    """测试模型 API 连通性（不会在响应中返回密钥）。"""
    s = effective_settings()
    if kind == "text":
        base, key, model = s.text_api_base, s.text_api_key, s.text_model
    else:
        base, key, model = s.image_api_base, s.image_api_key, s.image_model
    if not base or not key:
        return {"ok": False, "message": "未配置 API Base 或 Key，生成结果将为模拟演示"}
    started = time.monotonic()
    try:
        with httpx.Client(timeout=30) as client:
            if kind == "text":
                resp = client.post(
                    f"{base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": [{"role": "user", "content": "ping"}],
                          "max_tokens": 5})
            else:
                resp = client.get(f"{base.rstrip('/')}/models",
                                  headers={"Authorization": f"Bearer {key}"})
        ok = resp.status_code < 400
        return {"ok": ok, "status_code": resp.status_code,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "message": "连接成功" if ok else f"API 返回 {resp.status_code}：{resp.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": int((time.monotonic() - started) * 1000),
                "message": f"连接失败：{e}"}


@router.get("/cost-logs")
def cost_logs(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(ApiCallLog).order_by(ApiCallLog.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "provider": r.provider, "model": r.model, "purpose": r.purpose,
             "status": r.status, "latency_ms": r.latency_ms, "cost_usd": r.cost_usd,
             "error": r.error, "created_at": r.created_at.isoformat()} for r in rows]
