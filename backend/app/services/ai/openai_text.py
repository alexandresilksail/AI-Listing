"""OpenAI 兼容文本模型适配器（Chat Completions，JSON 输出）。

适用于任何提供 OpenAI 兼容 /chat/completions 接口的服务商，
通过配置 text_api_base / text_api_key / text_model 接入。

兼容性处理：
- response_format=json_object 部分供应商不支持（返回 400）：
  自动降级为不带 response_format 重试一次，保证可用性。
- 所有错误信息经过密钥过滤，绝不泄露 API Key。
"""
from __future__ import annotations

import json
import logging

import httpx

from .base import AINotConfigured, TextAdapter, TextGenResult

logger = logging.getLogger("polylisting.ai.text")

LISTING_SYSTEM_PROMPT = """你是资深跨境电商本地化文案专家，为亚马逊/Temu/独立站卖家撰写商品 Listing。
硬性规则：
1. 只能使用用户提供的商品资料中的事实信息，禁止编造材质、规格、认证、功能、性能、销量或评价。
2. 资料缺失的字段不要虚构，在 localization_note 中说明“信息缺失，建议补充”。
3. 按目标市场消费者的自然表达进行本地化，禁止生硬直译；调整语气、单位（公制/英制）、拼写（美式/英式）。
4. 关键词自然融入，禁止堆砌。
5. 严格遵守平台字段规则（标题长度、五点卖点数量、搜索词限制等）。
6. 医疗/健康/环保/性能宣称必须谨慎，无认证数据不得宣称。
7. 必须输出 JSON，不要输出任何其他文字。"""


class OpenAITextAdapter(TextAdapter):
    name = "openai-compatible-text"

    def __init__(self, *args, json_mode: str = "json_object", **kwargs):
        super().__init__(*args, **kwargs)
        self.json_mode = json_mode if json_mode in ("json_object", "none") else "json_object"

    def _post(self, client: httpx.Client, system: str, user: str,
              use_json_mode: bool) -> httpx.Response:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.6,
        }
        if use_json_mode:
            body["response_format"] = {"type": "json_object"}
        return client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )

    def _chat(self, system: str, user: str) -> tuple[str, int, int]:
        """返回 (内容, tokens_in, tokens_out)。带超时、有限重试与 JSON 模式降级。"""
        from ...config import effective_settings
        from ...security import scrub_secrets
        s = effective_settings()
        use_json_mode = s.text_json_mode == "json_object"
        last_err: Exception | None = None
        degraded = False  # 已因供应商不支持 json_object 而降级
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = self._post(client, system, user, use_json_mode)
                    # 供应商不支持 response_format：降级重试一次
                    if (resp.status_code == 400 and use_json_mode and not degraded
                            and "response_format" in resp.text[:500]):
                        logger.warning("供应商不支持 response_format=json_object，降级重试")
                        use_json_mode = False
                        degraded = True
                        resp = self._post(client, system, user, False)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError("rate limited/server error",
                                                    request=resp.request, response=resp)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage") or {}
                    return (content, int(usage.get("prompt_tokens") or 0),
                            int(usage.get("completion_tokens") or 0))
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt == self.max_retries:
                    break
        raise RuntimeError(f"文本模型调用失败：{scrub_secrets(str(last_err), s.text_api_key)}")

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("模型未返回 JSON")
        return json.loads(text[start:end + 1])

    def generate_listing(self, *, product: dict, platform: str, market: str,
                         language: str, rules: list[dict]) -> TextGenResult:
        if not self.available():
            raise AINotConfigured("文本模型 API 未配置")
        product_json = json.dumps(product, ensure_ascii=False, indent=1)
        rules_json = json.dumps(rules, ensure_ascii=False, indent=1)
        user_prompt = f"""目标平台：{platform}
目标市场：{market}（语言：{language}）
平台规则（必须遵守）：
{rules_json}

商品资料（唯一事实来源）：
{product_json}

请输出 JSON，字段如下：
{{
  "title": "商品标题",
  "bullets": ["五点卖点1", "..."],
  "description": "商品详情描述",
  "faq": [["问题1", "答案1"], ["问题2", "答案2"]],
  "search_terms": "后台搜索词（平台支持时）",
  "image_alt": "商品主图 ALT 文本",
  "marketing_slogan": "营销标语",
  "localization_note": "本地化说明与信息缺失提示",
  "risk_note": "风险提示"
}}"""
        content, tin, tout = self._chat(LISTING_SYSTEM_PROMPT, user_prompt)
        fields = self._extract_json(content)
        # 结构化校验
        fields.setdefault("title", "")
        fields.setdefault("bullets", [])
        fields.setdefault("description", "")
        fields.setdefault("faq", [])
        fields.setdefault("search_terms", "")
        fields.setdefault("image_alt", "")
        fields.setdefault("marketing_slogan", "")
        fields.setdefault("localization_note", "")
        fields.setdefault("risk_note", "")
        cost = self.estimate_cost(tin, tout)
        return TextGenResult(fields=fields, model=self.model, tokens_in=tin,
                             tokens_out=tout, cost_usd=cost, cost_known=cost is not None,
                             raw=content)

    def generate_seo(self, *, product: dict, market: str, language: str) -> TextGenResult:
        if not self.available():
            raise AINotConfigured("文本模型 API 未配置")
        product_json = json.dumps(product, ensure_ascii=False, indent=1)
        user_prompt = f"""目标市场：{market}（语言：{language}）
商品资料：
{product_json}

请输出 JSON：
{{
  "keywords": [
    {{"keyword": "...", "type": "core|longtail|scene|attribute", "reason": "推荐理由"}}
  ],
  "titles": [
    {{"title": "标题候选", "focus": "侧重点说明"}}
  ]
}}
注意：这是 AI 关键词建议，不得包含搜索量、竞争度等无法验证的数据。"""
        content, tin, tout = self._chat(
            "你是亚马逊 SEO 关键词研究员。只基于商品资料推导关键词，不虚构任何搜索量/竞争度数据。必须输出 JSON。",
            user_prompt)
        fields = self._extract_json(content)
        cost = self.estimate_cost(tin, tout)
        return TextGenResult(fields=fields, model=self.model, tokens_in=tin,
                             tokens_out=tout, cost_usd=cost, cost_known=cost is not None,
                             raw=content)
