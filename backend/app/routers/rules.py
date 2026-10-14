"""规则中心：平台/市场/类目规则配置。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PlatformRule
from ..schemas import RuleIn, RuleOut

router = APIRouter(prefix="/api/rules", tags=["规则中心"])


@router.get("", response_model=list[RuleOut])
def list_rules(rule_type: str | None = None, platform: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(PlatformRule)
    if rule_type:
        q = q.filter(PlatformRule.rule_type == rule_type)
    if platform:
        q = q.filter(PlatformRule.platform.in_([platform, "*"]))
    return q.order_by(PlatformRule.id).all()


@router.post("", response_model=RuleOut)
def create_rule(payload: RuleIn, db: Session = Depends(get_db)):
    rule = PlatformRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleIn, db: Session = Depends(get_db)):
    rule = db.get(PlatformRule, rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    for k, v in payload.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(PlatformRule, rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    db.delete(rule)
    db.commit()
    return {"ok": True}
