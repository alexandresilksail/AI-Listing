"""AI 适配器抽象基类与数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field


class AINotConfigured(Exception):
    """未配置 API：调用方必须将结果标记为“模拟”，不得伪造真实调用。"""


@dataclass
class TextGenResult:
    fields: dict                       # 结构化 Listing 字段
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    raw: str = ""


@dataclass
class ImageGenResult:
    images: list[bytes] = field(default_factory=list)  # PNG 字节
    model: str = ""
    cost_usd: float = 0.0
    raw_meta: dict = field(default_factory=dict)


class TextAdapter:
    """文本模型适配器接口（可替换实现）。"""

    name = "base"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def generate_listing(self, *, product: dict, platform: str, market: str,
                         language: str, rules: list[dict]) -> TextGenResult:
        raise NotImplementedError

    def generate_seo(self, *, product: dict, market: str, language: str) -> TextGenResult:
        raise NotImplementedError

    # 成本估算表（USD / 1K tokens），未知模型返回 None（按 0 计并标注估算不可用）
    PRICING: dict[str, tuple[float, float]] = {
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4o": (0.0025, 0.01),
        "gpt-4.1-mini": (0.0004, 0.0016),
        "gpt-4.1": (0.002, 0.008),
    }

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        price = self.PRICING.get(self.model)
        if not price:
            return 0.0
        return (tokens_in / 1000) * price[0] + (tokens_out / 1000) * price[1]


class ImageAdapter:
    """图像模型适配器接口（可替换实现）。"""

    name = "base"

    # 画幅比例 → 各模型支持的输出尺寸
    SIZES = {
        "1:1": "1024x1024",
        "3:4": "1024x1536",
        "4:3": "1536x1024",
        "9:16": "1024x1536",
        "16:9": "1536x1024",
    }

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def size_for(self, aspect_ratio: str) -> str:
        return self.SIZES.get(aspect_ratio, "1024x1024")

    def generate(self, *, prompt: str, size: str, n: int = 1) -> ImageGenResult:
        raise NotImplementedError

    def edit(self, *, prompt: str, image_bytes: bytes, size: str, n: int = 1) -> ImageGenResult:
        raise NotImplementedError

    PRICING_PER_IMAGE: dict[str, float] = {
        "gpt-image-1": 0.04,
        "dall-e-3": 0.04,
        "dall-e-2": 0.02,
    }

    def estimate_cost(self, n: int) -> float:
        return self.PRICING_PER_IMAGE.get(self.model, 0.0) * n
