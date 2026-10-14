"""演示数据：无 API Key 时完整体验端到端流程（导入→生成→审核→导出）。"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, ProductImage, ProductParam
from ..services.review_service import ensure_default_rules
from ..services.storage import get_storage, new_filename

router = APIRouter(prefix="/api/demo", tags=["演示数据"])


def _demo_image(sku: str, kind: str, color: tuple[int, int, int]) -> bytes:
    """绘制演示用商品示意图（明确为演示素材，非真实商品照片）。"""
    img = Image.new("RGB", (900, 900), (245, 247, 250))
    d = ImageDraw.Draw(img)
    # 简单商品轮廓（示意）
    d.rounded_rectangle([250, 300, 650, 600], radius=40, fill=color,
                        outline=(60, 70, 85), width=6)
    d.rectangle([380, 380, 520, 520], fill=(255, 255, 255), outline=(60, 70, 85), width=4)
    d.text((450, 200), f"DEMO {sku}", fill=(90, 100, 115), anchor="mm")
    d.text((450, 700), f"{kind} · 演示示意图", fill=(120, 130, 145), anchor="mm")
    d.text((450, 740), "仅供功能演示，非真实商品照片", fill=(150, 160, 175), anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


DEMO_PRODUCTS = [
    {
        "sku": "DEMO-BOTTLE-001", "name": "便携式运动保温水壶 750ml",
        "brand": "DemoBrand", "model": "TB-750", "category": "outdoor",
        "source_text": ("便携式运动保温水壶，750ml 大容量。材质：304 不锈钢。"
                        "颜色：哑光黑 / 天空蓝 / 樱花粉。重量：380g。"
                        "保温时长：12 小时。适用人群：运动健身爱好者。"
                        "适用场景：健身房、户外徒步、办公室、校园。"
                        "包装清单：水壶 x1、杯刷 x1、说明书 x1。"
                        "注意事项：首次使用前请清洗；请勿放入微波炉。"),
        "params": [
            ("basic", "品名", "便携式运动保温水壶", ""),
            ("spec", "容量", "750", "ml"),
            ("spec", "材质", "304 不锈钢", ""),
            ("spec", "颜色", "哑黑/天蓝/樱粉", ""),
            ("spec", "重量", "380", "g"),
            ("spec", "保温时长", "12", "小时"),
            ("usage", "适用人群", "运动健身爱好者", ""),
            ("usage", "适用场景", "健身房、户外徒步、办公室", ""),
            ("package", "包装清单", "水壶 x1、杯刷 x1、说明书 x1", ""),
            ("usage", "注意事项", "首次使用前清洗；勿入微波炉", ""),
        ],
        "image_kinds": [("main", (52, 120, 200)), ("实物", (52, 120, 200)),
                        ("细节", (80, 140, 210)), ("场景", (70, 130, 220))],
    },
    {
        "sku": "DEMO-LAMP-002", "name": "智能触控护眼台灯",
        "brand": "DemoBrand", "model": "TL-Pro", "category": "electronics",
        "source_text": ("智能触控护眼台灯，无频闪，国AA 级照度。材质：ABS+铝合金。"
                        "颜色：白色。功率：12W。色温：2700K-6500K 无极调光。"
                        "适用人群：学生、办公人群。适用场景：书桌、床头、办公室。"
                        "包装清单：台灯 x1、电源适配器 x1、说明书 x1。"
                        "注意事项：请使用原装适配器；避免潮湿环境。"),
        "params": [
            ("basic", "品名", "智能触控护眼台灯", ""),
            ("spec", "功率", "12", "W"),
            ("spec", "色温范围", "2700K-6500K", ""),
            ("spec", "材质", "ABS+铝合金", ""),
            ("spec", "颜色", "白色", ""),
            ("usage", "适用人群", "学生、办公人群", ""),
            ("usage", "适用场景", "书桌、床头、办公室", ""),
            ("package", "包装清单", "台灯 x1、适配器 x1、说明书 x1", ""),
        ],
        "image_kinds": [("main", (240, 180, 60)), ("实物", (240, 180, 60)),
                        ("细节", (250, 200, 90))],
    },
    {
        "sku": "DEMO-ORGANIZER-003", "name": "抽屉式桌面收纳盒套装",
        "brand": "DemoBrand", "model": "ORG-Set5", "category": "home",
        "source_text": ("抽屉式桌面收纳盒套装，5 件组。材质：PP 塑料。"
                        "颜色：白/灰。尺寸：大 24x16x8cm、中 20x14x7cm、小 16x11x6cm。"
                        "适用人群：家庭、学生、办公。适用场景：书桌、梳妆台、厨房抽屉。"
                        "包装清单：收纳盒 x5。注意事项：避免阳光直射以防变色。"),
        "params": [
            ("basic", "品名", "抽屉式桌面收纳盒套装", ""),
            ("spec", "规格", "5 件组", ""),
            ("spec", "材质", "PP 塑料", ""),
            ("spec", "尺寸", "大24x16x8cm/中20x14x7cm/小16x11x6cm", ""),
            ("usage", "适用人群", "家庭、学生、办公", ""),
            ("package", "包装清单", "收纳盒 x5", ""),
        ],
        "image_kinds": [("main", (120, 200, 140)), ("实物", (120, 200, 140))],
    },
]


@router.post("/seed")
def seed_demo(db: Session = Depends(get_db)):
    """创建演示商品与演示图片（幂等：已存在则跳过）。"""
    ensure_default_rules(db)
    storage = get_storage()
    created = []
    for spec in DEMO_PRODUCTS:
        if db.query(Product).filter(Product.sku == spec["sku"]).first():
            continue
        p = Product(sku=spec["sku"], name=spec["name"], brand=spec["brand"],
                    model=spec["model"], category=spec["category"],
                    source_text=spec["source_text"], is_demo=True)
        db.add(p)
        db.flush()
        for group, key, value, unit in spec["params"]:
            db.add(ProductParam(product_id=p.id, group=group, key=key, value=value,
                                unit=unit, verified=False, source="import"))
        for kind, color in spec["image_kinds"]:
            content = _demo_image(spec["sku"], kind, color)
            filename = new_filename(f"{spec['sku']}_{kind}", "png")
            rel = storage.save_image(content, filename, f"products/{p.id}/original")
            db.add(ProductImage(product_id=p.id, kind=kind, filename=filename,
                                path=rel, mime="image/png", size=len(content),
                                width=900, height=900))
        created.append(spec["sku"])
    db.commit()
    return {"ok": True, "created": created, "message": "演示商品与演示图片已创建"}
