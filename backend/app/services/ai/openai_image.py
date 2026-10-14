"""OpenAI 兼容图像模型适配器（Images API：generate / edit）。

支持 dall-e-3 / gpt-image-1 及任何兼容 /images/generations、/images/edits
的服务商。生成与编辑均支持传入参考图（edit 模式使用 multipart 上传原图）。

安全：
- 模型返回的图片 URL 下载前经过 SSRF 校验（safe_download）：
  仅 https、禁止内网/环回/链路本地地址、重定向逐跳校验、大小上限。
- 错误信息经过密钥过滤。
"""
from __future__ import annotations

import base64
import logging

import httpx

from .base import AINotConfigured, ImageAdapter, ImageGenResult

logger = logging.getLogger("polylisting.ai.image")


class OpenAIImageAdapter(ImageAdapter):
    name = "openai-compatible-image"

    def _post_with_retry(self, url: str, *, json_body: dict | None = None,
                         files: dict | None = None, data: dict | None = None) -> dict:
        from ...config import effective_settings
        from ...security import scrub_secrets
        s = effective_settings()
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    if files is not None:
                        resp = client.post(url, headers={"Authorization": f"Bearer {self.api_key}"},
                                           files=files, data=data)
                    else:
                        resp = client.post(url, headers={"Authorization": f"Bearer {self.api_key}"},
                                           json=json_body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError("rate limited/server error",
                                                request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt == self.max_retries:
                    break
        raise RuntimeError(
            f"图像模型调用失败：{scrub_secrets(str(last_err), s.image_api_key)}")

    def _decode(self, data: dict) -> list[bytes]:
        from ...security import safe_download, verify_image_bytes
        out: list[bytes] = []
        for item in data.get("data") or []:
            if item.get("b64_json"):
                content = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                # SSRF 防护：校验协议/地址/重定向/大小后才下载
                content = safe_download(item["url"])
            else:
                continue
            # 解码校验：无法解码为图片的内容直接拒绝，不落入库
            verify_image_bytes(content)
            out.append(content)
        return out

    def generate(self, *, prompt: str, size: str, n: int = 1) -> ImageGenResult:
        if not self.available():
            raise AINotConfigured("图像模型 API 未配置")
        data = self._post_with_retry(
            f"{self.base_url}/images/generations",
            json_body={"model": self.model, "prompt": prompt, "size": size, "n": n},
        )
        cost = self.estimate_cost(n)
        return ImageGenResult(images=self._decode(data), model=self.model,
                              cost_usd=cost, cost_known=cost is not None,
                              raw_meta={"size": size})

    def edit(self, *, prompt: str, image_bytes: bytes, size: str, n: int = 1) -> ImageGenResult:
        if not self.available():
            raise AINotConfigured("图像模型 API 未配置")
        files = {"image": ("reference.png", image_bytes, "image/png")}
        data = {"model": self.model, "prompt": prompt, "size": size, "n": str(n)}
        resp = self._post_with_retry(f"{self.base_url}/images/edits", files=files, data=data)
        cost = self.estimate_cost(n)
        return ImageGenResult(images=self._decode(resp), model=self.model,
                              cost_usd=cost, cost_known=cost is not None,
                              raw_meta={"size": size, "edit": True})
