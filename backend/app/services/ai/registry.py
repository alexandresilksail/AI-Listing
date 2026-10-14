"""适配器注册表：根据当前配置返回可用适配器实例。"""
from __future__ import annotations

from .base import AINotConfigured, ImageAdapter, TextAdapter
from .openai_image import OpenAIImageAdapter
from .openai_text import OpenAITextAdapter


def get_text_adapter() -> TextAdapter:
    from ...config import effective_settings
    s = effective_settings()
    adapter = OpenAITextAdapter(s.text_api_base, s.text_api_key, s.text_model,
                                timeout=s.request_timeout_sec, max_retries=s.max_retries,
                                json_mode=s.text_json_mode)
    if not adapter.available():
        raise AINotConfigured("文本模型 API 未配置：请在“模型设置”中填写 API Base 与 Key")
    return adapter


def get_image_adapter() -> ImageAdapter:
    from ...config import effective_settings
    s = effective_settings()
    adapter = OpenAIImageAdapter(s.image_api_base, s.image_api_key, s.image_model,
                                 timeout=s.request_timeout_sec, max_retries=s.max_retries)
    if not adapter.available():
        raise AINotConfigured("图像模型 API 未配置：请在“模型设置”中填写 API Base 与 Key")
    return adapter


def text_available() -> bool:
    from ...config import effective_settings
    s = effective_settings()
    return s.text_configured


def image_available() -> bool:
    from ...config import effective_settings
    s = effective_settings()
    return s.image_configured
