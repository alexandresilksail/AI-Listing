"""市场语言包：本地化词典与规则基线。

simulated 模式使用这些模板生成“结构正确但内容为占位/演示”的文案，
所有 simulated 结果在 UI 与数据层均带 is_simulated 标记。
"""
from __future__ import annotations

# 各市场的单位制与表达习惯
MARKET_PROFILE = {
    "US": {"unit_system": "imperial", "spelling": "美式英语", "tone": "直接、强调价值与便利", "currency": "USD"},
    "UK": {"unit_system": "metric", "spelling": "英式英语", "tone": "礼貌、注重品质与细节", "currency": "GBP"},
    "DE": {"unit_system": "metric", "spelling": "德语", "tone": "严谨、数据与参数驱动", "currency": "EUR"},
    "FR": {"unit_system": "metric", "spelling": "法语", "tone": "优雅、生活方式导向", "currency": "EUR"},
    "ES": {"unit_system": "metric", "spelling": "西班牙语", "tone": "热情、家庭与性价比", "currency": "EUR"},
    "IT": {"unit_system": "metric", "spelling": "意大利语", "tone": "设计感与生活品味", "currency": "EUR"},
    "JP": {"unit_system": "metric", "spelling": "日语", "tone": "礼貌、细节与安心感", "currency": "JPY"},
    "BR": {"unit_system": "metric", "spelling": "巴西葡萄牙语", "tone": "友好活泼、促销敏感", "currency": "BRL"},
    "ID": {"unit_system": "metric", "spelling": "印尼语", "tone": "实用、价格友好", "currency": "IDR"},
    "TH": {"unit_system": "metric", "spelling": "泰语", "tone": "友好、注重视觉与口碑", "currency": "THB"},
    "SA": {"unit_system": "metric", "spelling": "阿拉伯语", "tone": "尊敬、家庭与礼物场景", "currency": "SAR", "rtl": True},
}

# 平台字段规则基线（无法从官方实时确认的部分标记 needs_verify）
PLATFORM_FIELD_RULES = {
    "amazon": {
        "title_max": 200, "bullets_max": 5, "bullet_max_len": 500,
        "description_max": 2000, "search_terms_max": 250,
        "image_min_px": 1000, "main_bg": "纯白 RGB(255,255,255)",
        "notes": "主图不得出现文字/水印/边框；细节图与场景图不受此限。具体以类目要求为准。",
    },
    "temu": {
        "title_max": 200, "bullets_max": 5, "bullet_max_len": 300,
        "description_max": 1500, "search_terms_max": 100,
        "image_min_px": 800, "main_bg": "简洁背景",
        "notes": "Temu 对主图与价格展示有额外模板要求，以平台最新规则为准。",
    },
    "独立站": {
        "title_max": 120, "bullets_max": 8, "bullet_max_len": 300,
        "description_max": 5000, "search_terms_max": 0,
        "image_min_px": 800, "main_bg": "无强制要求",
        "notes": "独立站无平台审核，仍需遵守广告法与目标市场消费者保护法。",
    },
}

# 高风险绝对化/夸大用语（多语言，审核引擎使用）
ABSOLUTE_CLAIMS = [
    "best", "#1", "number one", "guaranteed", "100%", "cure", "miracle",
    "world's", "amazing", "perfect", "unbeatable", "risk-free",
    "beste", "garantiert", "wunder", "mejor", "garantizado", "meilleur",
    "最高", "完璧", "最強", "絶対", " garantia",
]

# 需要认证支撑的宣称
CERTIFICATION_CLAIMS = ["fda", "ce", "ul", "rohs", "energy star", "iso ", "reach",
                        "cpSC".lower(), "食品级", "medical grade", "hospital grade",
                        "organic", "eco-friendly", "biodegradable", "recyclable"]

# 常见商品类目关键词词根（模拟模式 + SEO 启发式使用）
CATEGORY_LEXICON = {
    "kitchen": ["kitchen", "cooking", "utensil", "chef", "home"],
    "electronics": ["wireless", "bluetooth", "portable", "charger", "device"],
    "home": ["home", "living", "organizer", "storage", "decor"],
    "outdoor": ["outdoor", "camping", "hiking", "travel", "portable"],
    "beauty": ["skincare", "beauty", "gentle", "daily care"],
    "baby": ["baby", "kids", "bpa free", "safe", "toddler"],
    "sports": ["fitness", "workout", "training", "gym", "sport"],
}

# 场景词库（按市场调整）
SCENE_WORDS = {
    "US": ["for daily use", "at home", "on the go", "for gifts"],
    "UK": ["for everyday use", "around the house", "while travelling"],
    "DE": ["für den Alltag", "für Zuhause", "für unterwegs"],
    "FR": ["pour un usage quotidien", "à la maison", "en déplacement"],
    "ES": ["para uso diario", "para el hogar", "para regalar"],
    "IT": ["per l'uso quotidiano", "per la casa", "in movimento"],
    "JP": ["日常使い", "ご家庭で", "外出先で", "プレゼントに"],
    "BR": ["para o dia a dia", "para casa", "para presentear"],
    "ID": ["untuk sehari-hari", "untuk rumah", "untuk hadiah"],
    "TH": ["สำหรับใช้งาน quotidien".replace(" quotidien", "ทุกวัน"), "สำหรับของขวัญ"],
    "SA": ["للاستخدام اليومي", "للمنزل", "كهدية"],
}

IMAGE_TYPE_LABELS = {
    "main": "商品主图优化",
    "scene": "商品场景图",
    "selling": "商品卖点图",
    "info": "商品信息图",
    "brand": "品牌营销图",
    "localize": "多语言图片本地化",
}
