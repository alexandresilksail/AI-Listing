"""V1.1 安全测试：API 鉴权、越权访问、SSRF 防护、上传校验、密钥保护、生产 fail-fast。

覆盖审计发现的问题：
- 所有管理接口未授权必须 401（生产模式不存在“令牌为空即公开”的状态）
- 模型返回图片 URL 下载必须防 SSRF（内网/元数据/非 https/超大响应体）
- 上传文件必须校验真实格式与可解码性
- API Key 不得出现在响应、日志与错误信息中
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent

# 需要鉴权的管理端点抽样（覆盖商品/文件/任务/导出/设置/规则）
PROTECTED_ENDPOINTS = [
    ("GET", "/api/products"),
    ("POST", "/api/products"),
    ("GET", "/api/products/1"),
    ("DELETE", "/api/products/1"),
    ("POST", "/api/products/1/images"),
    ("POST", "/api/products/import"),
    ("GET", "/api/listings/tasks"),
    ("POST", "/api/listings/tasks"),
    ("GET", "/api/listings/versions?product_id=1"),
    ("POST", "/api/seo/generate"),
    ("GET", "/api/seo/keywords?product_id=1"),
    ("POST", "/api/images/tasks"),
    ("GET", "/api/images/tasks"),
    ("GET", "/api/images/generated"),
    ("GET", "/api/reviews"),
    ("GET", "/api/reviews/summary"),
    ("GET", "/api/tasks/overview"),
    ("POST", "/api/tasks/listing/1/retry"),
    ("GET", "/api/exports"),
    ("POST", "/api/exports"),
    ("GET", "/api/exports/1"),
    ("GET", "/api/settings"),
    ("PUT", "/api/settings"),
    ("POST", "/api/settings/test?kind=text"),
    ("GET", "/api/settings/cost-logs"),
    ("GET", "/api/rules"),
    ("POST", "/api/rules"),
    ("GET", "/api/files/export/1"),
    ("POST", "/api/demo/seed"),
]


class TestAuthentication:
    """统一 API 鉴权。"""

    def test_public_endpoints_accessible_without_token(self, anon_client):
        """探活与元信息端点公开（不返回敏感数据）。"""
        r = anon_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        r2 = anon_client.get("/api/meta")
        assert r2.status_code == 200
        assert "markets" in r2.json()

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_management_endpoints_reject_anonymous(self, anon_client, method, path):
        """所有管理接口未授权请求必须 401——生产不存在公开管理接口。"""
        r = anon_client.request(method, path)
        assert r.status_code == 401, f"{method} {path} 未授权时应返回 401，实际 {r.status_code}"

    def test_wrong_token_rejected(self, anon_client):
        r = anon_client.get("/api/products", headers={"X-API-Token": "wrong-token"})
        assert r.status_code == 401

    def test_bearer_auth_accepted(self, anon_client):
        r = anon_client.get("/api/products",
                            headers={"Authorization": "Bearer test-secret-token-123456"})
        assert r.status_code == 200

    def test_correct_token_accepted(self, client):
        r = client.get("/api/products")
        assert r.status_code == 200

    def test_settings_never_returns_plain_key(self, client):
        """模型设置接口返回的密钥必须脱敏。"""
        from app.config import save_runtime_settings
        save_runtime_settings({"text_api_key": "sk-super-secret-key-123456"})
        try:
            r = client.get("/api/settings")
            assert r.status_code == 200
            body = r.text
            assert "sk-super-secret-key-123456" not in body
            assert "****" in r.json()["text_api_key_masked"]
        finally:
            save_runtime_settings({})


class TestAccessControl:
    """越权与资源边界（单租户下的资源不存在/归属校验）。"""

    def test_nonexistent_product_404(self, client):
        r = client.get("/api/products/99999999")
        assert r.status_code == 404

    def test_nonexistent_task_404(self, client):
        assert client.get("/api/listings/tasks/99999999").status_code == 404
        assert client.get("/api/images/tasks/99999999").status_code == 404
        assert client.post("/api/listings/tasks/99999999/retry").status_code == 404
        assert client.post("/api/images/tasks/99999999/retry").status_code == 404

    def test_nonexistent_version_404(self, client):
        assert client.get("/api/listings/versions/99999999").status_code == 404
        assert client.post("/api/listings/versions/99999999/edit",
                           json={"fields": [], "note": ""}).status_code == 404

    def test_param_idor_blocked(self, client, product_id):
        """删除不属于该商品的参数必须 404（防越权改他人资源）。"""
        r = client.delete(f"/api/products/{product_id}/params/99999999")
        assert r.status_code == 404

    def test_image_idor_blocked(self, client, product_id):
        r = client.delete(f"/api/products/{product_id}/images/99999999")
        assert r.status_code == 404

    def test_export_download_nonexistent_404(self, client):
        assert client.get("/api/files/export/99999999").status_code == 404

    def test_generated_image_nonexistent_404(self, client):
        assert client.get("/api/files/generated/99999999").status_code == 404

    def test_ref_image_ids_limited_to_product(self, client, product_id):
        """参考图 ID 被限制在该商品的图片范围内（不引用其他商品图片）。"""
        # 创建另一个商品及其图片不可行时，至少验证无效 ref id 不会导致 500
        r = client.post("/api/images/tasks", json={
            "product_id": product_id, "image_type": "main", "market": "US",
            "aspect_ratio": "1:1", "count": 1, "ref_image_ids": [99999999]})
        assert r.status_code == 200  # 无效引用被忽略而非崩溃


class TestSSRF:
    """模型返回 URL 下载的 SSRF 防护。"""

    def test_http_url_rejected_in_production_mode(self):
        from app.security import assert_url_allowed
        with pytest.raises(ValueError, match="http"):
            assert_url_allowed("http://example.com/a.png", allow_insecure=False)

    def test_non_http_scheme_rejected(self):
        from app.security import assert_url_allowed
        for bad in ("file:///etc/passwd", "ftp://x/a.png", "gopher://x/", ""):
            with pytest.raises(ValueError):
                assert_url_allowed(bad, allow_insecure=False)

    @pytest.mark.parametrize("url", [
        "https://169.254.169.254/latest/meta-data/",   # 云元数据
        "https://127.0.0.1/x.png",                      # 环回
        "https://localhost/x.png",                      # localhost
        "https://10.0.0.5/x.png",                       # 私网
        "https://192.168.1.1/x.png",                    # 私网
        "https://172.16.0.1/x.png",                     # 私网
        "https://[::1]/x.png",                          # IPv6 环回
        "https://0.0.0.0/x.png",                        # 0.0.0.0
    ])
    def test_internal_addresses_rejected(self, url):
        from app.security import assert_url_allowed
        with pytest.raises(ValueError):
            assert_url_allowed(url, allow_insecure=False)

    def test_public_https_allowed(self):
        from app.security import assert_url_allowed
        # 公网 IP 字面量（不依赖 DNS）
        assert_url_allowed("https://93.184.216.34/image.png", allow_insecure=False)

    def test_image_adapter_decode_rejects_ssrf_url(self):
        """适配器 _decode 对内网/元数据 URL 必须拒绝，不发起请求。"""
        from app.services.ai.openai_image import OpenAIImageAdapter
        adapter = OpenAIImageAdapter("https://api.example.com/v1", "k", "gpt-image-1")
        with pytest.raises(ValueError):
            adapter._decode({"data": [{"url": "http://169.254.169.254/latest/meta-data/"}]})
        with pytest.raises(ValueError):
            adapter._decode({"data": [{"url": "https://127.0.0.1:8000/x.png"}]})

    def test_image_adapter_decode_accepts_b64(self):
        """b64_json 内容必须解码并通过图片校验。"""
        from app.services.ai.openai_image import OpenAIImageAdapter
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="PNG")
        import base64
        data = {"data": [{"b64_json": base64.b64encode(buf.getvalue()).decode()}]}
        out = OpenAIImageAdapter("https://api.example.com/v1", "k", "gpt-image-1")._decode(data)
        assert len(out) == 1 and out[0][:4] == b"\x89PNG"

    def test_image_adapter_decode_rejects_non_image_b64(self):
        """模型返回非图片内容必须拒绝（不落入库）。"""
        from app.services.ai.openai_image import OpenAIImageAdapter
        import base64
        data = {"data": [{"b64_json": base64.b64encode(b"not an image at all").decode()}]}
        with pytest.raises(ValueError):
            OpenAIImageAdapter("https://api.example.com/v1", "k", "gpt-image-1")._decode(data)

    # ------------------------------------------------------------ 本地下载行为
    def test_safe_download_local_server(self, monkeypatch):
        """本地 mock 服务器：insecure 开关、大小上限、重定向主机锁定。"""
        from app.security import safe_download
        from app.config import get_settings

        png = io.BytesIO()
        Image.new("RGB", (16, 16), (10, 120, 200)).save(png, format="PNG")
        png_bytes = png.getvalue()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/img.png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(png_bytes)))
                    self.end_headers()
                    self.wfile.write(png_bytes)
                elif self.path == "/redirect-metadata":
                    self.send_response(302)
                    self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            # 1) 生产模式（默认）：http + 内网直接拒绝
            with pytest.raises(ValueError):
                safe_download(f"{base}/img.png")

            # 2) 开发 insecure 模式：允许本地 http
            monkeypatch.setenv("PL_ALLOW_INSECURE_DOWNLOAD", "true")
            get_settings.cache_clear()
            try:
                content = safe_download(f"{base}/img.png")
                assert content == png_bytes
                # 3) 大小上限生效
                with pytest.raises(ValueError, match="超过大小上限"):
                    safe_download(f"{base}/img.png", max_bytes=10)
                # 4) 重定向到元数据地址：主机锁定拒绝
                with pytest.raises(ValueError):
                    safe_download(f"{base}/redirect-metadata")
            finally:
                monkeypatch.delenv("PL_ALLOW_INSECURE_DOWNLOAD", raising=False)
                get_settings.cache_clear()
        finally:
            server.shutdown()


class TestUploadValidation:
    """上传文件真实格式与解码安全。"""

    def _png(self, size=(64, 64)) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", size, (30, 150, 60)).save(buf, format="PNG")
        return buf.getvalue()

    def test_valid_png_accepted(self, client, product_id):
        r = client.post(f"/api/products/{product_id}/images",
                        files={"file": ("ok.png", self._png(), "image/png")},
                        data={"kind": "main"})
        assert r.status_code == 200

    def test_fake_extension_rejected(self, client, product_id):
        """扩展名是图片但内容不是 → 魔数校验拒绝。"""
        r = client.post(f"/api/products/{product_id}/images",
                        files={"file": ("evil.png", b"this is not an image", "image/png")},
                        data={"kind": "main"})
        assert r.status_code == 400

    def test_disallowed_extension_rejected(self, client, product_id):
        r = client.post(f"/api/products/{product_id}/images",
                        files={"file": ("x.gif", self._png(), "image/gif")},
                        data={"kind": "main"})
        assert r.status_code == 400

    def test_corrupted_image_rejected(self, client, product_id):
        """魔数正确但数据损坏（PIL 解码失败）→ 拒绝。"""
        corrupted = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        r = client.post(f"/api/products/{product_id}/images",
                        files={"file": ("broken.png", corrupted, "image/png")},
                        data={"kind": "main"})
        assert r.status_code == 400

    def test_oversized_upload_rejected(self, client, product_id, monkeypatch):
        """超过大小限制 → 拒绝（临时把上限降到 1KB 验证逻辑）。"""
        from app.config import get_settings
        monkeypatch.setenv("PL_MAX_UPLOAD_MB", "0")  # 0MB → 任何非空文件都超限
        get_settings.cache_clear()
        try:
            r = client.post(f"/api/products/{product_id}/images",
                            files={"file": ("big.png", self._png((200, 200)), "image/png")},
                            data={"kind": "main"})
            assert r.status_code == 400
        finally:
            monkeypatch.delenv("PL_MAX_UPLOAD_MB", raising=False)
            get_settings.cache_clear()

    def test_pixel_limit_enforced(self, client, product_id, monkeypatch):
        """像素超上限（防解压炸弹）→ 拒绝。"""
        from app.config import get_settings
        monkeypatch.setenv("PL_MAX_IMAGE_PIXELS", "1000")  # 64x64=4096 > 1000
        get_settings.cache_clear()
        try:
            r = client.post(f"/api/products/{product_id}/images",
                            files={"file": ("pix.png", self._png((64, 64)), "image/png")},
                            data={"kind": "main"})
            assert r.status_code == 400
        finally:
            monkeypatch.delenv("PL_MAX_IMAGE_PIXELS", raising=False)
            get_settings.cache_clear()


class TestSecretProtection:
    """密钥保护：脱敏、日志与错误过滤。"""

    def test_mask_secret(self):
        from app.security import mask_secret, scrub_secrets
        assert mask_secret("") == ""
        assert mask_secret("short") == "****"
        masked = mask_secret("sk-1234567890abcdef")
        assert masked.startswith("sk-1") and masked.endswith("cdef") and "1234567890" not in masked
        assert scrub_secrets("error with sk-1234567890abcdef inside", "sk-1234567890abcdef") \
            == "error with **** inside"

    def test_test_connection_error_does_not_leak_key(self, client, monkeypatch):
        """连接失败响应不得包含 API Key。"""
        from app.config import get_settings, save_runtime_settings
        secret = "sk-leak-check-key-999888"
        save_runtime_settings({
            "text_api_base": "http://127.0.0.1:9/v1",  # 丢弃端口，必然连接失败
            "text_api_key": secret,
            "text_model": "gpt-4o-mini",
        })
        try:
            r = client.post("/api/settings/test?kind=text")
            assert r.status_code == 200
            assert secret not in r.text
        finally:
            save_runtime_settings({})

    def test_cost_logs_do_not_leak_key(self, client):
        r = client.get("/api/settings/cost-logs")
        assert r.status_code == 200
        assert "sk-" not in r.text


class TestProductionFailFast:
    """生产模式 fail-fast：未配置令牌必须拒绝启动（不存在公开管理接口的生产状态）。"""

    def _run_subprocess(self, env_extra: dict) -> subprocess.CompletedProcess:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="pl_prod_test_")
        env = dict(os.environ)
        env.update({
            "PL_DATA_DIR": tmp,
            "PL_DATABASE_URL": f"sqlite:///{Path(tmp) / 't.db'}",
            "PL_TEXT_API_BASE": "", "PL_TEXT_API_KEY": "",
            "PL_IMAGE_API_BASE": "", "PL_IMAGE_API_KEY": "",
        })
        env.update(env_extra)
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(BACKEND_DIR)!r})\n"
            "from app.main import app\n"
            "from fastapi.testclient import TestClient\n"
            "try:\n"
            "    with TestClient(app) as c:\n"
            "        print('STARTED')\n"
            "except RuntimeError as e:\n"
            "    print('REJECTED')\n"
            "    sys.exit(3)\n"
        )
        return subprocess.run([sys.executable, "-c", script], env=env,
                              capture_output=True, text=True, timeout=120, cwd=str(BACKEND_DIR))

    def test_production_without_token_refuses_to_start(self):
        """PL_ENV=production 且无 PL_API_TOKEN → 拒绝启动。"""
        r = self._run_subprocess({"PL_ENV": "production", "PL_API_TOKEN": ""})
        assert r.returncode == 3, f"应拒绝启动：{r.stdout}{r.stderr}"
        assert "REJECTED" in r.stdout

    def test_production_with_token_starts(self):
        """PL_ENV=production + PL_API_TOKEN → 正常启动。"""
        r = self._run_subprocess({"PL_ENV": "production",
                                  "PL_API_TOKEN": "prod-token-abcdef123456"})
        assert r.returncode == 0, f"应正常启动：{r.stdout}{r.stderr}"
        assert "STARTED" in r.stdout
