"""平台规则与内容审核引擎（文案 + 图片）。

AI 检查不能替代平台官方审核；无法确认的规则一律标记 needs_manual（待核实）。
"""
from __future__ import annotations

import io
import logging
import re
from collections import Counter

from PIL import Image

from ..models import (GeneratedImage, ListingVersion, PlatformRule, Product,
                      ProductParam, ReviewItem, SeoKeyword)
from .market_data import ABSOLUTE_CLAIMS, CERTIFICATION_CLAIMS, PLATFORM_FIELD_RULES

logger = logging.getLogger("polylisting.review")


def _field_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for x in content:
            parts.extend(_field_text(x) if isinstance(x, (list, dict)) else [str(x)])
        return " ".join(parts)
    if isinstance(content, dict):
        return " ".join(str(v) for v in content.values())
    return str(content or "")


def _add(db, **kw):
    item = ReviewItem(**kw)
    db.add(item)
    return item


def review_listing_version(db, version_id: int) -> list[ReviewItem]:
    """文案风险检查：长度/平台限制/绝对化/认证宣称/关键词堆砌/语言一致性。"""
    version = db.get(ListingVersion, version_id)
    if version is None:
        raise ValueError("Listing 版本不存在")
    # 清理旧结果（重新审核）
    db.query(ReviewItem).filter(
        ReviewItem.target_type == "listing",
        ReviewItem.target_id == version_id).delete()

    rules = PLATFORM_FIELD_RULES.get(version.platform, PLATFORM_FIELD_RULES["amazon"])
    product = db.get(Product, version.product_id)
    fields = {f.field: f.content for f in version.fields}
    pid = version.product_id
    created: list[ReviewItem] = []

    def flag(code, level, reason, location, suggestion, needs_manual=False):
        created.append(_add(db, target_type="listing", target_id=version_id,
                            product_id=pid, rule_code=code, level=level, reason=reason,
                            location=location, suggestion=suggestion, needs_manual=needs_manual))

    # 1. 标题长度
    title = _field_text(fields.get("title", ""))
    if len(title) > rules["title_max"]:
        flag("title_length", "medium", f"标题 {len(title)} 字符，超出 {version.platform} 上限 {rules['title_max']}",
             "title", f"精简至 {rules['title_max']} 字符以内，优先保留品牌+核心词")
    elif 0 < len(title) < 30:
        flag("title_too_short", "low", "标题过短，可能浪费关键词展示空间",
             "title", "补充核心属性词或场景词")

    # 2. 五点卖点数量与长度
    bullets = fields.get("bullets") or []
    if isinstance(bullets, list):
        if len(bullets) > rules["bullets_max"]:
            flag("bullets_count", "medium",
                 f"卖点 {len(bullets)} 条，超出平台上限 {rules['bullets_max']}",
                 "bullets", "合并或删减次要卖点")
        for i, b in enumerate(bullets):
            if len(_field_text(b)) > rules["bullet_max_len"]:
                flag("bullet_length", "low", f"第 {i+1} 条卖点超过 {rules['bullet_max_len']} 字符",
                     f"bullets[{i}]", "压缩表述，突出单一卖点")

    # 3. 详情长度
    desc = _field_text(fields.get("description", ""))
    if len(desc) > rules["description_max"]:
        flag("description_length", "medium",
             f"详情 {len(desc)} 字符，超出上限 {rules['description_max']}",
             "description", "精简段落，保留核心信息")

    # 4. 绝对化/夸大宣称
    all_text = " ".join(_field_text(v) for v in fields.values()).lower()
    for claim in ABSOLUTE_CLAIMS:
        if claim.lower() in all_text:
            flag("absolute_claim", "high", f"检测到绝对化/夸大表述「{claim}」",
                 "文案全局", "删除或改为可验证的客观描述，避免违反广告法")

    # 5. 认证宣称需证据
    cert_params = [p for p in (product.params if product else [])
                   if p.group == "cert" and p.value and p.verified]
    for claim in CERTIFICATION_CLAIMS:
        if claim.lower() in all_text and not cert_params:
            flag("unverified_cert", "high",
                 f"文案包含认证/资质宣称「{claim}」，但商品资料中无已确认的认证参数",
                 "文案全局", "补充认证编号与检测报告，或删除该宣称", needs_manual=True)

    # 6. 关键词堆砌
    words = re.findall(r"[A-Za-z]{4,}", all_text)
    if words:
        counter = Counter(w.lower() for w in words)
        top_word, top_count = counter.most_common(1)[0]
        density = top_count / len(words)
        if density > 0.08 and top_count >= 5:
            flag("keyword_stuffing", "medium",
                 f"关键词「{top_word}」出现 {top_count} 次（密度 {density:.0%}），存在堆砌风险",
                 "文案全局", "使用同义词替换，控制核心词密度在 5% 以内")

    # 7. 禁用词
    banned = db.query(SeoKeyword).filter(
        SeoKeyword.product_id == pid, SeoKeyword.banned.is_(True)).all()
    for b in banned:
        if b.keyword.lower() in all_text:
            flag("banned_keyword", "high", f"使用了已设禁用的关键词「{b.keyword}」",
                 "文案全局", "替换该关键词")

    # 8. 必须包含的词
    must = db.query(SeoKeyword).filter(
        SeoKeyword.product_id == pid, SeoKeyword.must_include.is_(True)).all()
    for m in must:
        if m.keyword.lower() not in all_text:
            flag("missing_must_keyword", "medium", f"必须包含的关键词「{m.keyword}」未出现在文案中",
                 "文案全局", "自然融入标题或卖点")

    # 9. 语言一致性（英文市场出现大量 CJK）
    if version.language.startswith("en"):
        cjk = len(re.findall(r"[\u4e00-\u9fff]", all_text))
        if cjk > 5:
            flag("language_mismatch", "high", f"英文文案中检测到 {cjk} 个中文字符",
                 "文案全局", "检查是否残留中文内容")

    # 10. 模拟结果提示
    if version.is_simulated:
        flag("simulated_content", "high",
             "该版本为模拟演示内容（未配置文本模型 API），结构可用但禁止直接发布",
             "全局", "在“模型设置”中配置文本模型 API 后重新生成", needs_manual=True)

    db.commit()
    return created


def review_generated_image(db, image_id: int) -> list[ReviewItem]:
    """图片风险检查：尺寸/格式/主图背景/模拟标记/待人工核实项。"""
    image = db.get(GeneratedImage, image_id)
    if image is None:
        raise ValueError("生成图片不存在")
    db.query(ReviewItem).filter(
        ReviewItem.target_type == "image", ReviewItem.target_id == image_id).delete()
    created: list[ReviewItem] = []

    def flag(code, level, reason, suggestion, needs_manual=False):
        created.append(_add(db, target_type="image", target_id=image_id,
                            product_id=image.product_id, rule_code=code, level=level,
                            reason=reason, location=image.filename, suggestion=suggestion,
                            needs_manual=needs_manual))

    rules = PLATFORM_FIELD_RULES.get("amazon")  # 图片基线以最严平台为准
    min_px = rules["image_min_px"]

    if image.width and image.height:
        if image.width < min_px or image.height < min_px:
            flag("image_resolution", "medium",
                 f"图片 {image.width}x{image.height}，低于电商平台建议的最小边长 {min_px}px",
                 "重新生成更高分辨率版本")
    else:
        flag("image_unreadable", "high", "无法读取图片尺寸，文件可能损坏",
                 "重新生成")

    # 主图背景检查（采样四角亮度）
    if image.image_type == "main" and image.path:
        try:
            from .storage import get_storage
            content = get_storage().read(image.path)
            with Image.open(io.BytesIO(content)) as im:
                im = im.convert("RGB")
                w, h = im.size
                corners = [im.getpixel((4, 4)), im.getpixel((w - 5, 4)),
                           im.getpixel((4, h - 5)), im.getpixel((w - 5, h - 5))]
                avg = sum(sum(c) / 3 for c in corners) / 4
                if avg < 235:
                    flag("main_bg_not_white", "medium",
                         f"主图背景平均亮度 {avg:.0f}/255，非纯白背景",
                         "亚马逊等平台要求主图纯白背景，请重新生成或更换背景", needs_manual=True)
        except Exception:  # noqa: BLE001
            flag("image_check_failed", "low", "背景自动检查失败，需人工核实",
                 "人工查看原图确认", needs_manual=True)

    if image.is_simulated:
        flag("simulated_image", "high",
             "该图片为模拟占位图（未配置图像模型 API），不是真实 AI 生成结果，禁止用于发布",
             "配置图像模型 API 后重新生成", needs_manual=True)

    # 人工核实项（无法自动判定的必须标记）
    flag("manual_visual_check", "info",
         "商品外观一致性（轮廓/颜色/结构/配件/Logo）需人工与原图比对确认",
         "在“图片审核中心”对比原图与生成图后人工审核", needs_manual=True)
    flag("manual_text_check", "info",
         "图片中的文字准确性（参数/数字/功能）需人工校对，不能假定模型渲染正确",
         "人工校对图片文字与商品资料", needs_manual=True)

    db.commit()
    return created


def review_generated_images_of_task(db, task_id: int) -> int:
    images = db.query(GeneratedImage).filter(GeneratedImage.task_id == task_id).all()
    for im in images:
        review_generated_image(db, im.id)
    return len(images)


def ensure_default_rules(db) -> int:
    """初始化内置平台规则（均标记 needs_verify，以官方最新规则为准）。"""
    if db.query(PlatformRule).count() > 0:
        return 0
    defaults = [
        ("amazon", "*", "text", "amazon_title_200", "medium",
         "亚马逊标题建议不超过 200 字符（部分类目更短）", "控制核心词前置", "亚马逊官方指南（需以最新为准）"),
        ("amazon", "*", "text", "amazon_bullets_5", "medium",
         "亚马逊五点卖点（Bullet Points）不超过 5 条", "每条突出单一卖点", "亚马逊官方指南（需以最新为准）"),
        ("amazon", "*", "image", "amazon_main_white_bg", "high",
         "亚马逊主图要求纯白背景 RGB(255,255,255)，无文字/水印/边框", "使用主图优化模式重新生成", "亚马逊官方指南（需以最新为准）"),
        ("amazon", "*", "image", "amazon_main_min_1000", "medium",
         "亚马逊主图建议最短边 ≥1000px 以支持缩放", "提高生成分辨率", "亚马逊官方指南（需以最新为准）"),
        ("temu", "*", "text", "temu_title_200", "medium",
         "Temu 标题长度限制与亚马逊相近，以平台最新要求为准", "控制标题长度", "Temu 商家中心（需以最新为准）"),
        ("temu", "*", "image", "temu_image_spec", "medium",
         "Temu 对主图尺寸与展示模板有额外要求", "按 Temu 图片规范生成", "Temu 商家中心（需以最新为准）"),
        ("*", "*", "text", "no_absolute_claims", "high",
         "禁止绝对化用语与无法证实的性能宣称（各市场广告法）", "改为客观描述", "通用合规基线（需以最新法规为准）"),
        ("*", "*", "text", "no_unverified_cert", "high",
         "认证/资质宣称必须具备可查证的编号与报告", "补充证据或删除宣称", "通用合规基线（需以最新法规为准）"),
        ("*", "*", "image", "no_fake_evidence", "high",
         "禁止将 AI 场景图伪装成真实用户拍摄的使用证据", "场景图需可识别为示意", "通用合规基线"),
    ]
    for platform, market, rtype, code, level, desc, sug, source in defaults:
        db.add(PlatformRule(platform=platform, market=market, rule_type=rtype, code=code,
                            level=level, description=desc, suggestion=sug, source=source,
                            needs_verify=True))
    db.commit()
    return len(defaults)
