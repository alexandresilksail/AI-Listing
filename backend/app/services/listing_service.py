"""Listing 生成服务：资料汇聚 → AI/模拟生成 → 版本落库 → 调用记录。"""
from __future__ import annotations

import re
import time
import logging
from datetime import datetime

from ..config import effective_settings
from ..models import (ApiCallLog, ListingField, ListingTask, ListingVersion, Product,
                      ProductParam)
from ..schemas import ProductParamIn
from .ai.registry import get_text_adapter, text_available
from .market_data import ABSOLUTE_CLAIMS, MARKET_PROFILE, PLATFORM_FIELD_RULES

logger = logging.getLogger("polylisting.listing")

# 中文商品详情常见参数抽取模式
_PARAM_PATTERNS: list[tuple[str, str, str]] = [
    (r"材质[：:]\s*([^\n；;，,]+)", "材质", "spec"),
    (r"材料[：:]\s*([^\n；;，,]+)", "材质", "spec"),
    (r"尺寸[：:]\s*([^\n；;，,]+)", "尺寸", "spec"),
    (r"规格[：:]\s*([^\n；;，,]+)", "规格", "spec"),
    (r"颜色[：:]\s*([^\n；;，,]+)", "颜色", "spec"),
    (r"重量[：:]\s*([^\n；;，,]+)", "重量", "spec"),
    (r"容量[：:]\s*([^\n；;，,]+)", "容量", "spec"),
    (r"功率[：:]\s*([^\n；;，,]+)", "功率", "spec"),
    (r"电池[：:]\s*([^\n；;，,]+)", "电池", "spec"),
    (r"适用人群[：:]\s*([^\n；;，,]+)", "适用人群", "usage"),
    (r"适用场景[：:]\s*([^\n；;，,]+)", "适用场景", "usage"),
    (r"包装清单[：:]\s*([^\n；;，,。]+)", "包装清单", "package"),
    (r"包装清单[：:]?\s*\n?((?:[^\n]+(?:\n|$)){1,4})", "包装清单", "package"),
    (r"注意事项[：:]\s*([^\n；;，,。]+)", "注意事项", "usage"),
    (r"认证[：:]\s*([^\n；;，,]+)", "认证", "cert"),
    (r"品牌[：:]\s*([^\n；;，,]+)", "品牌", "basic"),
    (r"型号[：:]\s*([^\n；;，,]+)", "型号", "basic"),
]


def extract_params_from_text(text: str) -> list[ProductParamIn]:
    """从中文明细提取结构化参数（启发式，结果需用户确认后才可标记 verified）。"""
    found: list[ProductParamIn] = []
    seen: set[str] = set()
    for pattern, key, group in _PARAM_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        value = m.group(1).strip(" \n\t·•-")
        value = re.sub(r"\s+", " ", value)[:200]
        if not value or key in seen:
            continue
        seen.add(key)
        found.append(ProductParamIn(group=group, key=key, value=value,
                                    verified=False, source="extracted"))
    return found


def product_facts(db, product_id: int) -> dict:
    """汇聚商品事实（AI 生成的唯一事实来源）。"""
    p: Product | None = db.get(Product, product_id)
    if p is None:
        raise ValueError("商品不存在")
    return {
        "sku": p.sku,
        "name": p.name,
        "brand": p.brand,
        "model": p.model,
        "category": p.category,
        "params": [
            {"key": x.key, "value": x.value, "unit": x.unit, "verified": x.verified}
            for x in p.params
        ],
        "images": [{"kind": x.kind, "filename": x.filename} for x in p.images],
        "source_text": p.source_text,
    }


def active_rules(db, platform: str, market: str) -> list[dict]:
    from ..models import PlatformRule
    rows = db.query(PlatformRule).filter(
        PlatformRule.enabled.is_(True),
        PlatformRule.rule_type == "text",
    ).all()
    out = []
    for r in rows:
        if r.platform not in (platform, "*"):
            continue
        if r.market not in (market, "*"):
            continue
        out.append({"code": r.code, "level": r.level, "description": r.description,
                    "suggestion": r.suggestion, "needs_verify": r.needs_verify})
    # 附加平台字段规则基线
    base = PLATFORM_FIELD_RULES.get(platform)
    if base:
        out.append({"code": "platform_field_baseline", "level": "medium",
                    "description": f"{platform} 字段规则基线：{base['notes']}",
                    "suggestion": "标题≤{title_max}字符，卖点≤{bullets_max}条，详情≤{description_max}字符".format(**base),
                    "needs_verify": True})
    return out


def _estimate_text_cost(adapter, facts: dict, rules: list[dict]) -> float | None:
    """文本任务执行前的保守费用预估（未知模型返回 None）。

    输入 token 按 资料+规则 JSON 长度粗估（中英混合约 2 字符/token），
    输出按 1500 token 预估；仅用于预算检查，实际费用以调用返回为准。
    """
    import json
    if not adapter.price_known():
        return None
    chars = len(json.dumps(facts, ensure_ascii=False)) + len(json.dumps(rules, ensure_ascii=False)) + 800
    est_in = max(500, chars // 2)
    est_out = 1500
    return adapter.estimate_cost(est_in, est_out)


# ---------------------------------------------------------------- 模拟生成
def _simulate_listing(product: Product, platform: str, market: str, language: str) -> dict:
    """未配置真实 API 时的演示文案：结构完整但为模板占位内容，全部标记 is_simulated。"""
    prof = MARKET_PROFILE.get(market, MARKET_PROFILE["US"])
    rules = PLATFORM_FIELD_RULES.get(platform, PLATFORM_FIELD_RULES["amazon"])
    name = product.name or product.sku
    brand = product.brand or "YourBrand"
    cat = product.category or "general"

    if language.startswith("en"):
        title = f"{brand} {name} - {prof['tone'].split('、')[0]} | {cat.title()}"
        bullets = [
            f"[模拟·待补充] 核心卖点 1：请基于已确认的商品参数填写",
            f"[模拟·待补充] 核心卖点 2：材质/尺寸等参数以商品资料为准",
            f"[模拟·待补充] 核心卖点 3：使用场景与适用人群",
            f"[模拟·待补充] 包装清单与配件",
            f"[模拟·待补充] 售后与保障（不得虚构认证）",
        ][: rules["bullets_max"]]
        description = ("[模拟内容] 这是未配置文本模型 API 时生成的演示结构。"
                       "请在“模型设置”中配置 API 后重新生成真实本地化文案。"
                       f"目标市场：{market}，语言习惯：{prof['spelling']}，语气：{prof['tone']}。")
        faq = [["[模拟] 常见问题 1？", "[模拟] 请基于商品资料作答，配置 API 后生成真实答案。"],
               ["[模拟] 常见问题 2？", "[模拟] 请基于商品资料作答。"]]
        search_terms = f"{cat} {name}".strip()[: rules["search_terms_max"]]
        alt = f"{brand} {name} product image"
        slogan = f"{brand} — {prof['tone'].split('、')[0]}"
    else:
        title = f"{brand} {name}（模拟·{market}）"
        bullets = [f"[模拟·待补充] 卖点 {i+1}（{language}）" for i in range(min(5, rules["bullets_max"]))]
        description = (f"[模拟内容] 未配置 API 的演示结构（{language} / {market}）。"
                       "配置模型 API 后可生成真实本地化文案。")
        faq = [[f"[模拟] 问题 {i+1}", "[模拟] 配置 API 后生成"] for i in range(2)]
        search_terms = f"{cat} {name}"[: rules["search_terms_max"]]
        alt = f"{brand} {name}"
        slogan = f"{brand}（模拟）"

    return {
        "title": title[: rules["title_max"]],
        "bullets": bullets,
        "description": description,
        "faq": faq,
        "search_terms": search_terms,
        "image_alt": alt,
        "marketing_slogan": slogan,
        "localization_note": (f"本结果为【模拟演示】——未配置文本模型 API。已按 {market}/{language} 的"
                              f"语言习惯（{prof['spelling']}、语气：{prof['tone']}）与 {platform} 字段规则构建结构，"
                              "但内容为占位文本，不得用于实际发布。"),
        "risk_note": "模拟内容未经 AI 真实生成，风险检查仅校验结构与长度。",
    }


def run_listing_task(db, task_id: int, epoch: int | None = None) -> ListingTask:
    """执行单个 Listing 生成任务（由任务队列调用）。

    epoch：提交时的任务版本号。执行前校验，执行后条件写终态——
    期间任务被重试（epoch 已变）时放弃本次执行，绝不覆盖重试任务。
    """
    from .ai.base import PRICING_VERSION
    from .task_queue import TaskQueue
    task: ListingTask | None = db.get(ListingTask, task_id)
    if task is None:
        raise ValueError("任务不存在")
    if TaskQueue.epoch_stale(db, ListingTask, task_id, epoch):
        logger.info("丢弃过期执行：Listing 任务 %s epoch=%s（已被重试或重置）",
                    task_id, epoch)
        return task

    task.status = "processing"
    task.error = ""
    db.commit()

    started = time.monotonic()
    product = db.get(Product, task.product_id)
    if product is None:
        TaskQueue.finalize(db, ListingTask, task_id, epoch, {
            "status": "failed", "error": "商品不存在或已删除"})
        db.refresh(task)
        return task

    facts = product_facts(db, task.product_id)
    rules = active_rules(db, task.platform, task.market)
    is_simulated = False
    model_name = ""
    cost: float | None = None
    fields: dict = {}
    est: float | None = None

    try:
        if text_available():
            adapter = get_text_adapter()
            model_name = adapter.model
            # 执行前预算检查 + 原子预留（防并发超支）；finally 中释放
            est = _estimate_text_cost(adapter, facts, rules)
            ok, msg = TaskQueue.check_and_reserve(est, effective_settings().per_task_budget_usd)
            if not ok:
                raise RuntimeError(f"预算检查未通过：{msg}")
            if msg:
                logger.warning("任务 %s 预算提示：%s", task.id, msg)
            result = adapter.generate_listing(
                product=facts, platform=task.platform, market=task.market,
                language=task.language, rules=rules)
            fields = result.fields
            cost = result.cost_usd  # None = 费用未知
            db.add(ApiCallLog(provider=adapter.name, model=model_name, purpose="listing",
                              status="success", latency_ms=int((time.monotonic() - started) * 1000),
                              cost_usd=cost,
                              cost_basis=("estimated" if cost is not None else "unknown"),
                              price_version=PRICING_VERSION,
                              tokens_in=result.tokens_in,
                              tokens_out=result.tokens_out))
        else:
            is_simulated = True
            fields = _simulate_listing(product, task.platform, task.market, task.language)
            db.add(ApiCallLog(provider="simulated", model="-", purpose="listing",
                              status="simulated",
                              latency_ms=int((time.monotonic() - started) * 1000),
                              error="文本模型 API 未配置，返回模拟演示内容"))
    except Exception as e:  # noqa: BLE001
        TaskQueue.finalize(db, ListingTask, task_id, epoch, {
            "status": "failed", "error": str(e),
            "duration_ms": int((time.monotonic() - started) * 1000)})
        db.add(ApiCallLog(provider="openai-compatible", model=model_name, purpose="listing",
                          status="failed", latency_ms=int((time.monotonic() - started) * 1000),
                          error=str(e), price_version=PRICING_VERSION))
        db.commit()
        db.refresh(task)
        return task
    finally:
        # 无论成功/失败都释放预算预留（未知费用未预留，无需释放）
        TaskQueue.release_reservation(est)

    # 关闭旧版本，写新版本
    db.query(ListingVersion).filter(
        ListingVersion.product_id == task.product_id,
        ListingVersion.platform == task.platform,
        ListingVersion.market == task.market,
        ListingVersion.language == task.language,
        ListingVersion.is_current.is_(True),
    ).update({"is_current": False})

    last_ver = db.query(ListingVersion).filter(
        ListingVersion.product_id == task.product_id,
        ListingVersion.platform == task.platform,
        ListingVersion.market == task.market,
        ListingVersion.language == task.language,
    ).count()
    version = ListingVersion(
        task_id=task.id, product_id=task.product_id, platform=task.platform,
        market=task.market, language=task.language, version=last_ver + 1,
        is_current=True, is_simulated=is_simulated,
        source="ai" if not is_simulated else "simulated",
        localization_note=fields.get("localization_note", ""),
        risk_note=fields.get("risk_note", ""),
    )
    db.add(version)
    db.flush()
    for field_name, content in fields.items():
        if field_name in ("localization_note", "risk_note"):
            continue
        db.add(ListingField(version_id=version.id, field=field_name, content=content))

    # 条件写终态：epoch 已变（期间被重试）则本次结果作废
    written = TaskQueue.finalize(db, ListingTask, task_id, epoch, {
        "status": "completed", "is_simulated": is_simulated,
        "model_name": model_name or ("simulated" if is_simulated else ""),
        "cost_usd": cost,
        "duration_ms": int((time.monotonic() - started) * 1000)})
    if not written:
        logger.info("Listing 任务 %s 执行期间被重试，本次结果已丢弃（epoch=%s）",
                    task_id, epoch)
        db.refresh(task)
        return task

    # 生成后自动执行文案审核
    try:
        from .review_service import review_listing_version
        review_listing_version(db, version.id)
    except Exception as e:  # noqa: BLE001 审核失败不影响主流程，但必须留痕
        logger.warning("文案审核失败 version=%s: %s", version.id, e)
    db.refresh(task)
    return task


def edit_listing(db, version_id: int, patches: list[dict], note: str = "") -> ListingVersion:
    """用户编辑：生成新版本并保留旧版本（支持版本对比）。"""
    version = db.get(ListingVersion, version_id)
    if version is None:
        raise ValueError("Listing 版本不存在")
    db.query(ListingVersion).filter(
        ListingVersion.product_id == version.product_id,
        ListingVersion.platform == version.platform,
        ListingVersion.market == version.market,
        ListingVersion.language == version.language,
        ListingVersion.is_current.is_(True),
    ).update({"is_current": False})

    new_ver = ListingVersion(
        task_id=version.task_id, product_id=version.product_id,
        platform=version.platform, market=version.market, language=version.language,
        version=version.version + 1, is_current=True,
        is_simulated=version.is_simulated, source="edit",
        localization_note=version.localization_note, risk_note=version.risk_note,
    )
    db.add(new_ver)
    db.flush()
    old_fields = {f.field: f.content for f in version.fields}
    patch_map = {p["field"]: p["content"] for p in patches}
    for field_name, content in {**old_fields, **patch_map}.items():
        db.add(ListingField(version_id=new_ver.id, field=field_name, content=content))
    if note:
        new_ver.localization_note = (new_ver.localization_note + " | 用户编辑：" + note).strip(" |")
    db.commit()
    try:
        from .review_service import review_listing_version
        review_listing_version(db, new_ver.id)
    except Exception:  # noqa: BLE001
        pass
    db.refresh(new_ver)
    return new_ver


def regenerate_field(db, version_id: int, field_name: str) -> dict:
    """单字段重新生成（当前适配器不可用时返回明确错误，不伪造内容）。"""
    if not text_available():
        raise ValueError("文本模型 API 未配置，无法真实重新生成。请先在“模型设置”中配置 API。")
    version = db.get(ListingVersion, version_id)
    if version is None:
        raise ValueError("Listing 版本不存在")
    product = db.get(Product, version.product_id)
    if product is None:
        raise ValueError("商品不存在")
    facts = product_facts(db, version.product_id)
    rules = active_rules(db, version.platform, version.market)
    adapter = get_text_adapter()
    from .task_queue import TaskQueue
    est = _estimate_text_cost(adapter, facts, rules)
    ok, msg = TaskQueue.check_and_reserve(est, effective_settings().per_task_budget_usd)
    if not ok:
        raise ValueError(f"预算检查未通过：{msg}")
    try:
        result = adapter.generate_listing(product=facts, platform=version.platform,
                                          market=version.market, language=version.language,
                                          rules=rules)
    finally:
        TaskQueue.release_reservation(est)
    if field_name not in result.fields:
        raise ValueError(f"模型未返回字段 {field_name}")
    from .ai.base import PRICING_VERSION
    db.add(ApiCallLog(provider=adapter.name, model=adapter.model, purpose="listing_regen",
                      status="success", cost_usd=result.cost_usd,
                      cost_basis=("estimated" if result.cost_usd is not None else "unknown"),
                      price_version=PRICING_VERSION,
                      tokens_in=result.tokens_in, tokens_out=result.tokens_out))
    db.commit()
    return {"field": field_name, "content": result.fields[field_name]}
