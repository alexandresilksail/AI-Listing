"""OpenAI 兼容图像模型适配器（Images API：generate / edit）。

支持 dall-e-3 / gpt-image-1 及任何兼容 /images/generations、/images/edits
的服务商。生成与编辑均支持传入参考图（edit 模式使用 multipart 上传原图）。
"""
from __future__ import annotations

import base64

import httpx

from .base import ImageAdapter, ImageGenResult


class OpenAIImageAdapter(ImageAdapter):
    name = "openai-compatible-image"

    def _post_with_retry(self, url: str, *, json_body: dict | None = None,
                         files: dict | None = None, data: dict | None = None) -> dict:
        last_err: Exception | None = None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    if files is not None:
                        resp = client.post(url, headers=headers, files=files, data=data)
                    else:
                        resp = client.post(url, headers=headers, json=json_body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError("rate limited/server error",
                                                request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt == self.max_retries:
                    break
        raise RuntimeError(f"图像模型调用失败：{last_err}")

    @staticmethod
    def _decode(data: dict) -> list[bytes]:
        out: list[bytes] = []
        for item in data.get("data") or []:
            if item.get("b64_json"):
                out.append(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                with httpx.Client(timeout=60) as client:
                    r = client.get(item["url"])
                    r.raise_for_status()
                    out.append(r.content)
        return out

    def generate(self, *, prompt: str, size: str, n: int = 1) -> ImageGenResult:
        from .base import AINotConfigured
        if not self.available():
            raise AINotConfigured("图像模型 API 未配置")
        data = self._post_with_retry(
            f"{self.base_url}/images/generations",
            json_body={"model": self.model, "prompt": prompt, "size": size, "n": n},
        )
        return ImageGenResult(images=self._decode(data), model=self.model,
                              cost_usd=self.estimate_cost(n), raw_meta={"size": size})

    def edit(self, *, prompt: str, image_bytes: bytes, size: str, n: int = 1) -> ImageGenResult:
        from .base import AINotConfigured
        if not self.available():
            raise AINotConfigured("图像模型 API 未配置")
        files = {"image": ("reference.png", image_bytes, "image/png")}
        data = {"model": self.model, "prompt": prompt, "size": size, "n": str(n)}
        resp = self._post_with_retry(f"{self.base_url}/images/edits", files=files, data=data)
        return ImageGenResult(images=self._decode(resp), model=self.model,
                              cost_usd=self.estimate_cost(n), raw_meta={"size": size, "edit": True})
