"""商品图片生成服务：提示词构建 → 适配器调用 → 版本落库。

未配置图像 API 时生成本地占位图（Pillow 绘制，带 SIMULATED 水印），
并在数据层打 is_simulated 标记，绝不伪装成真实 AI 生成结果。
"""
from __future__ import annotations

import io
import logging
import time

from PIL import Image, ImageDraw, ImageFont

from ..config import effective_settings
from ..models import ApiCallLog, GeneratedImage, ImageGenTask, Product, ProductImage
from .ai.registry import get_image_adapter, image_available
from .market_data import IMAGE_TYPE_LABELS
from .storage import get_storage, new_filename

logger = logging.getLogger("polylisting.image")

_TYPE_INSTRUCTIONS = {
    "main": "生成符合电商平台要求的商品主图：纯白背景、主体突出、构图居中、无文字无水印。",
    "scene": "生成商品在真实生活环境中的使用场景图，贴合目标市场家居风格与生活方式。",
    "selling": "基于商品卖点生成营销视觉图，突出材质、尺寸、功能与使用优势，可含简短文字标注。",
    "info": "生成商品信息图：尺寸示意/使用步骤/结构细节/包装清单，参数必须与商品资料一致。",
    "brand": "生成品牌风格营销图，可用于独立站横幅或促销素材，保持品牌视觉。",
    "localize": "将图片中的文字转换为目标市场语言，保留布局与商品主体，阿拉伯语需从右向左排版。",
}

_SIZE_MAP = {"1:1": (768, 768), "3:4": (768, 1024), "4:3": (1024, 768),
             "9:16": (576, 1024), "16:9": (1024, 576)}


def build_image_prompt(task: ImageGenTask, product: Product, refs: list[ProductImage],
                       language: str) -> str:
    """根据商品事实自动构建图像提示词（含真实性与禁止项约束）。"""
    facts = []
    if product.name:
        facts.append(f"商品名称：{product.name}")
    if product.brand:
        facts.append(f"品牌：{product.brand}")
    for p in product.params[:12]:
        facts.append(f"{p.key}：{p.value}{p.unit}")
    type_label = IMAGE_TYPE_LABELS.get(task.image_type, task.image_type)
    prompt = f"""{_TYPE_INSTRUCTIONS.get(task.image_type, "")}
【图片类型】{type_label}　【目标市场】{task.market}（语言：{language}）　【画幅】{task.aspect_ratio}
【商品事实（唯一依据，禁止改变）】
{chr(10).join(facts)}
【必须保留】商品轮廓、颜色、材质纹理、按钮/接口/结构、品牌标识、包装内容、配件数量、商品比例。
【禁止】凭空增加配件、改变关键结构或功能、修改品牌 Logo、添加未经验证的认证/测试数据/性能数字、
将场景图伪装成真实用户拍摄证据。"""
    if task.background:
        prompt += f"\n【背景要求】{task.background}"
    if task.style:
        prompt += f"\n【风格要求】{task.style}"
    if task.prompt:
        prompt += f"\n【用户自定义】{task.prompt}"
    if refs:
        prompt += (f"\n【参考图】已提供 {len(refs)} 张商品原图作为参考，"
                   "必须保持商品外观与参考图一致。")
    return prompt


def _placeholder_image(task: ImageGenTask, product: Product, index: int) -> bytes:
    """模拟占位图：明确标注 SIMULATED / 未配置 API，不含真实商品视觉。"""
    w, h = _SIZE_MAP.get(task.aspect_ratio, (768, 768))
    img = Image.new("RGB", (w, h), (240, 243, 248))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, w - 10, h - 10], outline=(148, 163, 184), width=3)
    try:
        font_big = ImageFont.truetype("arial.ttf", max(24, w // 14))
        font_sm = ImageFont.truetype("arial.ttf", max(14, w // 28))
    except Exception:  # noqa: BLE001 无字体文件时使用默认字体
        font_big = ImageFont.load_default()
        font_sm = ImageFont.load_default()
    cx = w // 2
    d.text((cx, h // 2 - 40), "SIMULATED", font=font_big, fill=(203, 60, 60), anchor="mm")
    d.text((cx, h // 2 + 8), "模拟占位图 · 未配置图像模型 API", font=font_sm,
           fill=(80, 90, 105), anchor="mm")
    d.text((cx, h // 2 + 44), f"SKU {product.sku} · {task.image_type} · {task.market}",
           font=font_sm, fill=(120, 130, 145), anchor="mm")
    d.text((cx, h // 2 + 76), "配置 API 后重新生成真实商品图", font=font_sm,
           fill=(120, 130, 145), anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_image_task(db, task_id: int, epoch: int | None = None) -> ImageGenTask:
    """执行单个图片生成任务（由任务队列调用）。

    epoch：提交时的任务版本号。执行前校验，执行后条件写终态——
    期间任务被重试（epoch 已变）时放弃本次执行，绝不覆盖重试任务。
    已成功生成的图片保留（单张失败不清空整批）。
    """
    from .ai.base import PRICING_VERSION
    from .task_queue import TaskQueue
    task: ImageGenTask | None = db.get(ImageGenTask, task_id)
    if task is None:
        raise ValueError("任务不存在")
    if TaskQueue.epoch_stale(db, ImageGenTask, task_id, epoch):
        logger.info("丢弃过期执行：图片任务 %s epoch=%s（已被重试或重置）",
                    task_id, epoch)
        return task

    task.status = "processing"
    task.error = ""
    db.commit()

    started = time.monotonic()
    product = db.get(Product, task.product_id)
    if product is None:
        TaskQueue.finalize(db, ImageGenTask, task_id, epoch, {
            "status": "failed", "error": "商品不存在或已删除"})
        db.refresh(task)
        return task

    refs: list[ProductImage] = []
    if task.ref_image_ids:
        refs = [im for im in product.images if im.id in set(task.ref_image_ids)]
    prompt = build_image_prompt(task, product, refs, task.language)
    task.prompt = prompt
    db.commit()

    storage = get_storage()
    is_simulated = False
    model_name = ""
    cost: float | None = None
    produced: list[bytes] = []
    est: float | None = None

    try:
        if image_available():
            adapter = get_image_adapter()
            model_name = adapter.model
            size = adapter.size_for(task.aspect_ratio)
            # 执行前预算检查 + 原子预留（图片费用按张数预估）；finally 中释放
            est = adapter.estimate_cost(task.count)  # None = 费用未知
            ok, msg = TaskQueue.check_and_reserve(est, effective_settings().per_task_budget_usd)
            if not ok:
                raise RuntimeError(f"预算检查未通过：{msg}")
            if msg:
                logger.warning("任务 %s 预算提示：%s", task.id, msg)
            if refs:
                # 使用商品原图作为参考进行编辑/生成
                result = adapter.edit(prompt=prompt, image_bytes=storage.read(refs[0].path),
                                      size=size, n=task.count)
            else:
                result = adapter.generate(prompt=prompt, size=size, n=task.count)
            produced = result.images
            cost = result.cost_usd  # None = 费用未知
            db.add(ApiCallLog(provider=adapter.name, model=model_name, purpose="image",
                              status="success", latency_ms=int((time.monotonic() - started) * 1000),
                              cost_usd=cost,
                              cost_basis=("estimated" if cost is not None else "unknown"),
                              price_version=PRICING_VERSION))
        else:
            is_simulated = True
            for i in range(task.count):
                produced.append(_placeholder_image(task, product, i))
            db.add(ApiCallLog(provider="simulated", model="-", purpose="image",
                              status="simulated",
                              latency_ms=int((time.monotonic() - started) * 1000),
                              error="图像模型 API 未配置，生成模拟占位图"))
    except Exception as e:  # noqa: BLE001
        TaskQueue.finalize(db, ImageGenTask, task_id, epoch, {
            "status": "failed", "error": str(e),
            "duration_ms": int((time.monotonic() - started) * 1000)})
        db.add(ApiCallLog(provider="openai-compatible", model=model_name, purpose="image",
                          status="failed", latency_ms=int((time.monotonic() - started) * 1000),
                          error=str(e), price_version=PRICING_VERSION))
        db.commit()
        db.refresh(task)
        return task
    finally:
        # 无论成功/失败都释放预算预留（未知费用未预留，无需释放）
        TaskQueue.release_reservation(est)

    # 已成功生成的部分保留（任务失败不清空已产出）
    from ..security import verify_image_bytes
    existing = db.query(GeneratedImage).filter(GeneratedImage.task_id == task.id).count()
    saved = 0
    invalid = 0
    for i, content in enumerate(produced):
        try:
            w, hgt = verify_image_bytes(content)
        except ValueError:
            invalid += 1
            logger.warning("任务 %s 第 %d 张生成结果不是有效图片，已丢弃", task.id, i + 1)
            continue
        subdir = f"products/{product.id}/generated"
        filename = new_filename(f"{product.sku}_{task.image_type}_{task.market}", "png")
        rel = storage.save_image(content, filename, subdir)
        db.add(GeneratedImage(
            task_id=task.id, product_id=product.id, image_type=task.image_type,
            market=task.market, language=task.language, filename=filename,
            path=rel, width=w, height=hgt, prompt=prompt, is_simulated=is_simulated,
            version=existing + i + 1))
        saved += 1

    # 条件写终态：epoch 已变（期间被重试）则本次结果作废
    final_status = "completed" if saved == task.count else "partial"
    error_text = ""
    if saved < task.count:
        error_text = f"成功 {saved}/{task.count} 张，其余失败"
        if invalid:
            error_text += f"（其中 {invalid} 张不是有效图片已丢弃）"
    written = TaskQueue.finalize(db, ImageGenTask, task_id, epoch, {
        "status": final_status, "is_simulated": is_simulated,
        "model_name": model_name or ("simulated" if is_simulated else ""),
        "cost_usd": cost,  # None = 费用未知
        "duration_ms": int((time.monotonic() - started) * 1000),
        "error": error_text})
    if not written:
        logger.info("图片任务 %s 执行期间被重试，本次结果已丢弃（epoch=%s）",
                    task_id, epoch)
        db.refresh(task)
        return task

    # 生成后自动执行图片审核
    try:
        from .review_service import review_generated_images_of_task
        review_generated_images_of_task(db, task.id)
    except Exception as e:  # noqa: BLE001 审核失败不影响主流程，但必须留痕
        logger.warning("图片审核失败 task=%s: %s", task.id, e)
    db.refresh(task)
    return task
