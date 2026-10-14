"""SEO 工作台：关键词生成与管理、标题候选、覆盖率分析。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import MARKET_LANGUAGES
from ..database import get_db
from ..models import Product, SeoKeyword, TitleCandidate
from ..schemas import (KeywordOut, SeoGenerateIn, SeoKeywordIn, TitleCandidateOut)
from ..services.seo_service import analyze_coverage, generate_seo

router = APIRouter(prefix="/api/seo", tags=["SEO 工作台"])


@router.post("/generate")
def generate(payload: SeoGenerateIn, db: Session = Depends(get_db)):
    if payload.market not in MARKET_LANGUAGES:
        raise HTTPException(400, f"不支持的市场代码 {payload.market}")
    try:
        return generate_seo(db, payload.product_id, payload.market)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/keywords", response_model=list[KeywordOut])
def list_keywords(product_id: int, market: str | None = None, db: Session = Depends(get_db)):
    q = db.query(SeoKeyword).filter(SeoKeyword.product_id == product_id)
    if market:
        q = q.filter(SeoKeyword.market == market)
    return q.order_by(SeoKeyword.kw_type, SeoKeyword.id).all()


@router.post("/keywords", response_model=KeywordOut)
def add_keyword(product_id: int, kw: SeoKeywordIn, market: str = "US",
                db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(404, "商品不存在")
    lang = MARKET_LANGUAGES.get(market, {}).get("language", "en-US")
    row = SeoKeyword(product_id=product_id, market=market, language=lang,
                     keyword=kw.keyword, kw_type=kw.kw_type, source="manual",
                     must_include=kw.must_include, banned=kw.banned,
                     note="用户手动添加")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, must_include: bool | None = None,
                   banned: bool | None = None, db: Session = Depends(get_db)):
    row = db.get(SeoKeyword, keyword_id)
    if not row:
        raise HTTPException(404, "关键词不存在")
    if must_include is not None:
        row.must_include = must_include
    if banned is not None:
        row.banned = banned
    db.commit()
    db.refresh(row)
    return row


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(SeoKeyword, keyword_id)
    if not row:
        raise HTTPException(404, "关键词不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/titles", response_model=list[TitleCandidateOut])
def list_titles(product_id: int, market: str | None = None, db: Session = Depends(get_db)):
    q = db.query(TitleCandidate).filter(TitleCandidate.product_id == product_id)
    if market:
        q = q.filter(TitleCandidate.market == market)
    return q.order_by(TitleCandidate.created_at.desc()).all()


@router.post("/titles/{title_id}/select", response_model=TitleCandidateOut)
def select_title(title_id: int, db: Session = Depends(get_db)):
    row = db.get(TitleCandidate, title_id)
    if not row:
        raise HTTPException(404, "标题候选不存在")
    db.query(TitleCandidate).filter(
        TitleCandidate.product_id == row.product_id,
        TitleCandidate.market == row.market).update({"is_selected": False})
    row.is_selected = True
    db.commit()
    db.refresh(row)
    return row


@router.get("/coverage/{version_id}")
def coverage(version_id: int, db: Session = Depends(get_db)):
    try:
        return analyze_coverage(db, version_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
