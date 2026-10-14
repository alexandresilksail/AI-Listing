"""SEO 优化引擎：关键词推导、标题候选、字段覆盖分析。

重要：本引擎输出均为“AI 关键词建议”，不接入真实搜索量数据源，
不得虚构搜索量、竞争度、排名或流量数据；评分仅用于辅助优化。
"""
from __future__ import annotations

import re
from collections import Counter

from ..models import (ListingField, ListingVersion, Product, SeoKeyword,
                      TitleCandidate)
from .market_data import CATEGORY_LEXICON, MARKET_PROFILE, PLATFORM_FIELD_RULES, SCENE_WORDS

_NOTE = "AI 关键词建议（无真实搜索量数据，仅供参考）"


def _tokens(text: str) -> list[str]:
    text = re.sub(r"[^\w\s\-]", " ", text.lower())
    return [t for t in text.split() if len(t) > 2]


def derive_keywords(product: Product, market: str, language: str) -> list[dict]:
    """基于商品资料推导关键词（启发式，可复现、无虚构数据）。"""
    out: list[dict] = []
    seen: set[str] = set()

    def add(kw: str, kw_type: str):
        kw = kw.strip()
        if not kw or kw.lower() in seen or len(kw) < 3:
            return
        seen.add(kw.lower())
        out.append({"keyword": kw, "type": kw_type})

    name = (product.name or "").strip()
    cat = (product.category or "").strip().lower()
    # 核心词：商品名称分词
    for t in _tokens(name):
        add(t, "core")
    if name:
        add(name, "core")
    # 类目词
    for w in CATEGORY_LEXICON.get(cat, []):
        add(w, "core")
    # 属性词：来自参数
    for p in product.params:
        v = (p.value or "").strip()
        if v and len(v) <= 40:
            add(v, "attribute")
        if p.key and len(p.key) <= 20:
            add(p.key, "attribute")
    # 场景词：按市场
    for w in SCENE_WORDS.get(market, SCENE_WORDS["US"]):
        add(w, "scene")
    # 长尾词：核心词 + 属性/场景组合
    cores = [k["keyword"] for k in out if k["type"] == "core"][:4]
    attrs = [k["keyword"] for k in out if k["type"] == "attribute"][:4]
    scenes = [k["keyword"] for k in out if k["type"] == "scene"][:3]
    for c in cores:
        for a in attrs[:3]:
            add(f"{c} {a}", "longtail")
        for s in scenes[:2]:
            add(f"{c} {s}", "longtail")
    return out[:40]


def generate_seo(db, product_id: int, market: str) -> dict:
    """生成并保存关键词与标题候选。"""
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("商品不存在")
    from ..config import MARKET_LANGUAGES
    language = MARKET_LANGUAGES.get(market, {}).get("language", "en-US")

    # 清空同市场旧 AI 建议（保留用户手动添加的）
    db.query(SeoKeyword).filter(
        SeoKeyword.product_id == product_id, SeoKeyword.market == market,
        SeoKeyword.source == "ai").delete()

    for kw in derive_keywords(product, market, language):
        db.add(SeoKeyword(product_id=product_id, market=market, language=language,
                          keyword=kw["keyword"], kw_type=kw["type"], source="ai",
                          note=_NOTE))
    db.flush()

    titles = build_title_candidates(product, market, language)
    db.query(TitleCandidate).filter(
        TitleCandidate.product_id == product_id,
        TitleCandidate.market == market).delete()
    for t in titles:
        db.add(TitleCandidate(product_id=product_id, market=market, language=language,
                              title=t["title"], scores=t["scores"]))
    db.commit()
    return {"keywords": len(titles) and db.query(SeoKeyword).filter(
        SeoKeyword.product_id == product_id, SeoKeyword.market == market).count() or 0,
        "titles": titles}


def build_title_candidates(product: Product, market: str, language: str,
                           platform: str = "amazon") -> list[dict]:
    """生成多个标题候选并评分（长度/关键词覆盖/可读性）。"""
    rules = PLATFORM_FIELD_RULES.get(platform, PLATFORM_FIELD_RULES["amazon"])
    max_len = rules["title_max"]
    brand = (product.brand or "").strip()
    name = (product.name or product.sku).strip()
    cat = (product.category or "").strip()
    attrs = [(p.value or "").strip() for p in product.params if p.value][:3]

    candidates: list[tuple[str, str]] = []
    if language.startswith("en"):
        candidates = [
            (f"{brand} {name}", "品牌+品名（简洁）"),
            (f"{brand} {name}, {attrs[0] if attrs else cat}", "品牌+品名+核心属性"),
            (f"{name} - {', '.join(attrs[:2])}" if attrs else f"{name} - {cat}", "品名+属性（转化导向）"),
            (f"{brand} {name} for {SCENE_WORDS.get(market, ['daily use'])[0]}", "品牌+品名+场景词"),
        ]
    elif language.startswith("de"):
        candidates = [
            (f"{brand} {name}", "Marke + Produktname"),
            (f"{brand} {name}, {attrs[0] if attrs else cat}", "Marke + Name + Attribut"),
            (f"{name} – {', '.join(attrs[:2])}" if attrs else f"{name} – {cat}", "Name + Attribute"),
        ]
    elif language.startswith("ja"):
        candidates = [
            (f"{brand} {name}", "ブランド＋商品名"),
            (f"{brand} {name} {attrs[0] if attrs else cat}", "ブランド＋商品名＋属性"),
            (f"{name}（{', '.join(attrs[:2])}）" if attrs else f"{name}（{cat}）", "商品名＋属性"),
        ]
    else:
        candidates = [
            (f"{brand} {name}", "品牌+品名"),
            (f"{brand} {name} {attrs[0] if attrs else cat}", "品牌+品名+属性"),
        ]

    keywords = [k.lower() for k in ([name] + [a for a in attrs if a] +
                ([cat] if cat else [])) if k]
    out = []
    seen: set[str] = set()
    for title, focus in candidates:
        title = title.strip()[:max_len]
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append({"title": title, "focus": focus,
                    "scores": score_title(title, keywords, max_len)})
    return out


def score_title(title: str, keywords: list[str], max_len: int) -> dict:
    """标题评分：长度合规、关键词覆盖、可读性（避免全大写/堆砌）。"""
    length = len(title)
    length_score = 100 if length <= max_len else max(0, 100 - (length - max_len))
    low = title.lower()
    covered = sum(1 for k in keywords if k.lower() in low)
    coverage = round(covered / max(1, len(keywords)) * 100)
    upper_ratio = sum(1 for c in title if c.isupper()) / max(1, len(title))
    readability = 100 if upper_ratio < 0.5 else max(0, 100 - int((upper_ratio - 0.5) * 200))
    # 重复词检测
    words = _tokens(title)
    dup = len(words) - len(set(words))
    if dup > 2:
        readability = max(0, readability - (dup - 2) * 10)
    overall = round(length_score * 0.4 + coverage * 0.4 + readability * 0.2)
    return {"overall": overall, "length": length_score, "keyword_coverage": coverage,
            "readability": readability, "char_count": length, "max_chars": max_len}


def analyze_coverage(db, version_id: int) -> dict:
    """分析关键词在 Listing 各字段中的自然融入情况。"""
    version = db.get(ListingVersion, version_id)
    if version is None:
        raise ValueError("Listing 版本不存在")
    keywords = db.query(SeoKeyword).filter(
        SeoKeyword.product_id == version.product_id,
        SeoKeyword.market == version.market).all()
    fields = {f.field: f.content for f in version.fields}

    def field_text(field: str) -> str:
        c = fields.get(field)
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return " ".join(str(x) for x in c)
        if isinstance(c, list) and c and isinstance(c[0], list):
            return " ".join(str(x) for pair in c for x in pair)
        return str(c or "")

    text_all = " ".join(field_text(f) for f in
                        ("title", "bullets", "description", "faq", "search_terms")).lower()
    rows = []
    missing_must, banned_used = [], []
    for kw in keywords:
        k = kw.keyword.lower()
        in_title = k in field_text("title").lower()
        in_bullets = k in field_text("bullets").lower()
        in_desc = k in field_text("description").lower()
        count = text_all.count(k)
        rows.append({"keyword": kw.keyword, "type": kw.kw_type, "in_title": in_title,
                     "in_bullets": in_bullets, "in_description": in_desc,
                     "occurrences": count,
                     "verdict": "已融入" if count else "未融入"})
        if kw.must_include and count == 0:
            missing_must.append(kw.keyword)
        if kw.banned and count > 0:
            banned_used.append(kw.keyword)
    coverage = round(sum(1 for r in rows if r["occurrences"]) / max(1, len(rows)) * 100)
    return {"coverage_percent": coverage, "keywords": rows,
            "missing_must_include": missing_must, "banned_used": banned_used,
            "note": _NOTE}
