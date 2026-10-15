"""OpenAI 兼容图像模型适配器（Images API：generate / edit）。

支持 dall-e-3 / gpt-image-1 及任何兼容 /images/generations、/images/edits
的服务商。生成与编辑均支持传入参考图（edit 模式使用 multipart 上传原图）。

安全：
- 模型返回的图片 URL 下载前经过 SSRF 校验（safe_download）：
  仅 https、禁止内网/环回/链路本地地址、重定向逐跳校验、大小上限。
- 错误信息经过密钥过滤。
"""
from __future__ import annotations

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
        # 分段超时：连接/读/写/池分别设限
        timeout = httpx.Timeout(connect=10.0, read=float(self.timeout),
                                write=60.0, pool=10.0)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    if files is not None:
                        resp = client.post(url, headers={"Authorization": f"Bearer {self.api_key}"},
                                           files=files, data=data)
                    else:
                        resp = client.post(url, headers={"Authorization": f"Bearer {self.api_key}"},
                                           json=json_body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError("rate limited/server error",
                                                request=resp.request, response=resp)
                if resp.status_code >= 400:
                    # 客户端错误不重试
                    raise RuntimeError(
                        f"图像模型返回 HTTP {resp.status_code}：{scrub_secrets(resp.text[:300], self.api_key)}")
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
                if attempt == self.max_retries:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if isinstance(e, RuntimeError) and "HTTP" in str(e):
                    break  # 客户端错误不重试
                if attempt == self.max_retries:
                    break
        raise RuntimeError(
            f"图像模型调用失败：{scrub_secrets(str(last_err), s.image_api_key)}")

    def _decode(self, data: dict) -> list[bytes]:
        """解码模型返回的图片（b64 或 URL）。

        - URL 分支走 safe_download（SSRF/大小/内容类型/重定向管控）
        - 单张下载失败/解码失败只跳过该张并留痕，不拖垮其余图片；
          全部失败时抛异常，由调用方把任务标记 failed——
          绝不生成虚假的成功记录。
        """
        import base64
        import binascii
        from ...security import safe_download, verify_image_bytes
        out: list[bytes] = []
        items = data.get("data") or []
        for idx, item in enumerate(items):
            try:
                if item.get("b64_json"):
                    try:
                        content = base64.b64decode(item["b64_json"], validate=True)
                    except (binascii.Error, ValueError) as e:
                        raise ValueError(f"第 {idx + 1} 张 base64 解码失败：{e}") from e
                elif item.get("url"):
                    # SSRF 防护：校验协议/地址/重定向/大小/内容类型后才下载
                    content = safe_download(item["url"])
                else:
                    logger.warning("第 %d 张返回既无 b64_json 也无 url，已跳过", idx + 1)
                    continue
                # 解码校验：无法解码为图片的内容直接拒绝，不落入库
                verify_image_bytes(content)
                out.append(content)
            except Exception as e:  # noqa: BLE001 单张失败不拖垮整批
                logger.warning("第 %d 张生成结果不可用，已跳过：%s", idx + 1, e)
                continue
        if not out and items:
            raise ValueError(f"模型返回了 {len(items)} 张图片但无一可用（下载或解码全部失败）")
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
