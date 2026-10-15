"""AI 适配器抽象基类与数据结构。

成本模型约定：
- estimate_cost 返回 None 表示【费用未知】（模型不在价格表中），
  绝不允许按 0 费用处理——未知费用不计入已花费统计，但会在任务与日志中明确标记。
- TextGenResult.cost_known=False 时 cost_usd 无意义。
"""
from __future__ import annotations

from dataclasses import dataclass, field


class AINotConfigured(Exception):
    """未配置 API：调用方必须将结果标记为“模拟”，不得伪造真实调用。"""


# 价格表版本：调整 PRICING / PRICING_PER_IMAGE 时同步递增，
# 每次调用记录都会带上该版本，便于追溯「估算依据」。
PRICING_VERSION = "2026-10-15.1"


@dataclass
class TextGenResult:
    fields: dict                       # 结构化 Listing 字段
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None      # None = 费用未知
    cost_known: bool = True            # False 时 cost_usd 无效（未知价格模型）
    raw: str = ""


@dataclass
class ImageGenResult:
    images: list[bytes] = field(default_factory=list)  # PNG 字节
    model: str = ""
    cost_usd: float | None = None      # None = 费用未知
    cost_known: bool = True
    raw_meta: dict = field(default_factory=dict)


class TextAdapter:
    """文本模型适配器接口（可替换实现）。"""

    name = "base"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120,
                 max_retries: int = 2, json_mode: str = "json_object"):
        """统一初始化接口：基类/注册器/具体适配器签名一致。

        json_mode: "json_object" 请求 response_format；"none" 不请求
        （供应商不支持时由适配器内部自动降级，见 OpenAITextAdapter）。
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.json_mode = json_mode if json_mode in ("json_object", "none") else "json_object"

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def generate_listing(self, *, product: dict, platform: str, market: str,
                         language: str, rules: list[dict]) -> TextGenResult:
        raise NotImplementedError

    def generate_seo(self, *, product: dict, market: str, language: str) -> TextGenResult:
        raise NotImplementedError

    # 成本估算表（USD / 1K tokens: 输入, 输出）。不在表中的模型返回 None（费用未知）。
    PRICING: dict[str, tuple[float, float]] = {
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4o": (0.0025, 0.01),
        "gpt-4.1-mini": (0.0004, 0.0016),
        "gpt-4.1": (0.002, 0.008),
        "gpt-4.1-nano": (0.0001, 0.0004),
        "gpt-5-mini": (0.00025, 0.002),
        "gpt-5": (0.00125, 0.01),
    }

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float | None:
        """返回估算费用（USD）；未知模型返回 None，绝不当作 0。"""
        price = self.PRICING.get(self.model)
        if not price:
            return None
        return round((tokens_in / 1000) * price[0] + (tokens_out / 1000) * price[1], 6)

    def price_known(self) -> bool:
        return self.model in self.PRICING


class ImageAdapter:
    """图像模型适配器接口（可替换实现）。"""

    name = "base"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    # 各模型实际支持的输出尺寸（按供应商文档）：
    # - gpt-image-1 / dall-e-2：1024x1024、1024x1536、1536x1024
    # - dall-e-3：仅 1024x1024、1792x1024、1024x1792
    MODEL_SIZES: dict[str, dict[str, str]] = {
        "gpt-image-1": {
            "1:1": "1024x1024", "3:4": "1024x1536", "9:16": "1024x1536",
            "4:3": "1536x1024", "16:9": "1536x1024"},
        "dall-e-3": {
            "1:1": "1024x1024", "16:9": "1792x1024", "4:3": "1792x1024",
            "9:16": "1024x1792", "3:4": "1024x1792"},
        "dall-e-2": {
            "1:1": "1024x1024", "3:4": "1024x1536", "9:16": "1024x1536",
            "4:3": "1536x1024", "16:9": "1536x1024"},
    }
    _DEFAULT_SIZES = {
        "1:1": "1024x1024", "3:4": "1024x1536", "4:3": "1536x1024",
        "9:16": "1024x1536", "16:9": "1536x1024"}

    def size_for(self, aspect_ratio: str) -> str:
        sizes = self.MODEL_SIZES.get(self.model, self._DEFAULT_SIZES)
        if aspect_ratio not in sizes:
            raise ValueError(
                f"模型 {self.model} 不支持画幅 {aspect_ratio}，"
                f"可用：{', '.join(sorted(sizes))}")
        return sizes[aspect_ratio]

    def generate(self, *, prompt: str, size: str, n: int = 1) -> ImageGenResult:
        raise NotImplementedError

    def edit(self, *, prompt: str, image_bytes: bytes, size: str, n: int = 1) -> ImageGenResult:
        raise NotImplementedError

    # 每张图片价格（USD）。不在表中的模型返回 None（费用未知）。
    PRICING_PER_IMAGE: dict[str, float] = {
        "gpt-image-1": 0.04,
        "dall-e-3": 0.04,
        "dall-e-2": 0.02,
    }

    def estimate_cost(self, n: int) -> float | None:
        """返回估算费用（USD）；未知模型返回 None，绝不当作 0。"""
        price = self.PRICING_PER_IMAGE.get(self.model)
        if price is None:
            return None
        return round(price * n, 6)

    def price_known(self) -> bool:
        return self.model in self.PRICING_PER_IMAGE
