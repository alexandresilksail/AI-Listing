"""V1.2 安全与可靠性加固测试。

覆盖 PROMPT 要求的新增用例：
- P0 前端 Token 不进入构建产物 / 构建参数 / 源码
- P0 文本适配器：实例化、构造参数一致、json_mode 真正生效、
  成功/超时/限流/服务端错误/非法响应/截断/缺字段/不伪装成功
- P1 任务 epoch：过期执行丢弃、终态条件写入、重试不互覆
- P1 预算：原子预留、并发防超支、释放、未知费用不预留
- P1 路径安全：../、绝对路径、同前缀目录、符号链接、不存在文件
- P1 图片下载：内容类型、单张失败容错、全部失败报错
- P1 迁移：幂等、V1.0 旧库升级、备份、数据保留
"""
from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.database import apply_migrations, init_db
from app.main import app
from app.models import ApiCallLog, ImageGenTask, ListingTask, Product
from app.security import safe_join
from app.services.ai.base import PRICING_VERSION, TextAdapter
from app.services.ai.openai_text import OpenAITextAdapter
from app.services.task_queue import TaskQueue

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_API_TOKEN = "test-secret-token-123456"
TOKEN_HEADERS = {"X-API-Token": TEST_API_TOKEN}


def _png_bytes(w=32, h=32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 100, 50)).save(buf, format="PNG")
    return buf.getvalue()


def _ok_chat_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200}}


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, handler):
    """把 httpx.Client 替换为 MockTransport 客户端（适配器内新建的 client 也生效）。"""
    real_init = httpx.Client.__init__

    def patched(self, *args, **kwargs):
        kwargs.pop("transport", None)
        real_init(self, *args, transport=_mock_transport(handler), **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched)


# ============================================================ P0：Token 泄露
class TestNoTokenLeak:
    """生产构建产物/构建参数/源码中不得出现 API 令牌注入。"""

    def test_compose_has_no_token_build_arg(self):
        text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        assert "VITE_API_TOKEN" not in text, \
            "docker-compose.yml 不得将令牌作为 build-arg 传给前端"

    def test_frontend_dockerfile_has_no_secret_arg(self):
        text = (PROJECT_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        assert "VITE_API_TOKEN" not in text
        assert "ARG VITE_API_TOKEN" not in text
        assert "ENV VITE_API_TOKEN" not in text

    def test_client_ts_does_not_read_build_env_token(self):
        text = (PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts").read_text(
            encoding="utf-8")
        code = "\n".join(line for line in text.splitlines()
                         if not line.strip().startswith(("*", "//")))
        assert "import.meta.env.VITE_API_TOKEN" not in code, \
            "前端不得从构建期环境变量读取令牌（会被打包进 bundle）"

    def test_dist_bundle_contains_no_token_injection(self):
        """dist 存在时校验产物无构建期令牌注入痕迹。"""
        dist = PROJECT_ROOT / "frontend" / "dist"
        if not dist.exists():
            pytest.skip("frontend/dist 未构建（本地开发跳过）")
        js_files = list(dist.rglob("*.js"))
        assert js_files, "dist 中没有 JS 产物"
        for f in js_files:
            text = f.read_text(encoding="utf-8", errors="ignore")
            # VITE_API_TOKEN 若被注入会以 import.meta.env 形式内联为字面量
            assert "VITE_API_TOKEN" not in text

    def test_unauthorized_requests_rejected(self, anon_client):
        for path in ("/api/products", "/api/settings", "/api/tasks/overview",
                     "/api/rules", "/api/exports"):
            r = anon_client.get(path)
            assert r.status_code == 401, f"{path} 未授权应 401，实得 {r.status_code}"

    def test_authorized_requests_accepted(self, client):
        assert client.get("/api/products").status_code == 200
        assert client.get("/api/tasks/overview").status_code == 200

    def test_api_key_not_in_error_response(self, client, monkeypatch,
                                           tmp_path, settings_env):
        """配置一个假 Key 后触发连接失败：错误响应不得包含 Key。"""
        secret = "sk-super-secret-value-123456"
        settings_env(text_api_base="https://127.0.0.1:1/v1",
                     text_api_key=secret, text_model="gpt-4o-mini")
        r = client.post("/api/settings/test", params={"kind": "text"})
        body = r.text
        assert secret not in body, "测试连接错误响应泄露了 API Key"


# ============================================================ P0：文本适配器
class TestTextAdapter:
    """适配器实例化、签名一致、json_mode 生效、异常路径。"""

    def _adapter(self, **kw):
        base = {"base_url": "https://api.example.com/v1", "api_key": "k",
                "model": "gpt-4o-mini"}
        base.update(kw)
        return OpenAITextAdapter(**base)

    def test_base_and_concrete_signature_consistent(self):
        """基类与具体适配器初始化签名一致（registry 传参不会炸）。"""
        import inspect
        base_params = set(inspect.signature(TextAdapter.__init__).parameters)
        conc_params = set(inspect.signature(OpenAITextAdapter.__init__).parameters)
        assert base_params == conc_params, \
            f"签名不一致：base={base_params} concrete={conc_params}"

    def test_json_mode_accepted_and_normalized(self):
        a = self._adapter(json_mode="json_object")
        assert a.json_mode == "json_object"
        b = self._adapter(json_mode="none")
        assert b.json_mode == "none"
        c = self._adapter(json_mode="garbage")  # 非法值回退默认
        assert c.json_mode == "json_object"

    def test_json_mode_truly_affects_request(self, monkeypatch, settings_env):
        """json_mode=json_object 时请求体必须带 response_format。"""
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini",
                     text_json_mode="json_object")
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_chat_payload('{"title": "t"}'))

        _patch_client(monkeypatch, handler)
        a = self._adapter(json_mode="json_object")
        a._chat("sys", "user")
        assert seen and seen[0].get("response_format") == {"type": "json_object"}

    def test_json_mode_none_omits_response_format(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini",
                     text_json_mode="none")
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_chat_payload('{"title": "t"}'))

        _patch_client(monkeypatch, handler)
        a = self._adapter(json_mode="none")
        a._chat("sys", "user")
        assert seen and "response_format" not in seen[0]

    def test_json_mode_degrades_on_supplier_400(self, monkeypatch, settings_env):
        """供应商不支持 response_format：自动降级重试且最终成功。"""
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(body)
            if "response_format" in body:
                return httpx.Response(
                    400, json={"error": {"message": "response_format not supported"}})
            return httpx.Response(200, json=_ok_chat_payload('{"title": "t"}'))

        _patch_client(monkeypatch, handler)
        a = self._adapter(json_mode="json_object")
        content, _, _ = a._chat("sys", "user")
        assert content == '{"title": "t"}'
        assert len(calls) == 2 and "response_format" not in calls[1]

    def test_rate_limit_retries_then_succeeds(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")
        n = {"i": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            n["i"] += 1
            if n["i"] == 1:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, json=_ok_chat_payload('{"title": "t"}'))

        _patch_client(monkeypatch, handler)
        a = self._adapter(max_retries=2)
        content, _, _ = a._chat("sys", "user")
        assert content == '{"title": "t"}' and n["i"] == 2

    def test_server_error_retries_then_fails(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        _patch_client(monkeypatch, handler)
        a = self._adapter(max_retries=1)
        with pytest.raises(RuntimeError, match="调用失败"):
            a._chat("sys", "user")

    def test_timeout_raises_runtime_error(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timeout", request=request)

        _patch_client(monkeypatch, handler)
        a = self._adapter(max_retries=0)
        with pytest.raises(RuntimeError, match="调用失败"):
            a._chat("sys", "user")

    def test_client_error_not_retried(self, monkeypatch, settings_env):
        """401 等客户端错误不重试（重试无意义），且错误不含密钥。"""
        secret = "sk-secret-abcdef123456"
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key=secret, text_model="gpt-4o-mini")
        n = {"i": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            n["i"] += 1
            return httpx.Response(401, json={"error": {"message": f"bad key {secret}"}})

        _patch_client(monkeypatch, handler)
        a = self._adapter(api_key=secret, max_retries=3)
        with pytest.raises(RuntimeError) as ei:
            a._chat("sys", "user")
        assert n["i"] == 1, "客户端错误不应重试"
        assert secret not in str(ei.value), "错误信息必须脱敏"

    def test_invalid_json_response_rejected(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ok_chat_payload("这不是 JSON 输出"))

        _patch_client(monkeypatch, handler)
        a = self._adapter()
        with pytest.raises(ValueError, match="未返回 JSON"):
            a.generate_listing(product={"sku": "X"}, platform="amazon",
                               market="US", language="en-US", rules=[])

    def test_truncated_json_rejected(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            # 模拟被截断的结构化输出
            return httpx.Response(
                200, json=_ok_chat_payload('{"title": "Half writ'))

        _patch_client(monkeypatch, handler)
        a = self._adapter()
        with pytest.raises(ValueError, match="未返回 JSON|截断"):
            a.generate_listing(product={"sku": "X"}, platform="amazon",
                               market="US", language="en-US", rules=[])

    def test_missing_core_field_rejected(self, monkeypatch, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=_ok_chat_payload('{"title": "只有标题"}'))

        _patch_client(monkeypatch, handler)
        a = self._adapter()
        with pytest.raises(ValueError, match="核心字段"):
            a.generate_listing(product={"sku": "X"}, platform="amazon",
                               market="US", language="en-US", rules=[])

    def test_unknown_model_cost_is_none(self):
        a = self._adapter(model="some-unknown-model")
        assert a.estimate_cost(1000, 1000) is None
        assert a.price_known() is False

    def test_known_model_cost_positive(self):
        a = self._adapter(model="gpt-4o-mini")
        cost = a.estimate_cost(1000, 1000)
        assert cost is not None and cost > 0


# ============================================================ P1：任务 epoch
class TestTaskEpochProtection:
    """epoch 机制：旧执行不得覆盖重试任务。"""

    def _db(self):
        from app.database import get_sessionmaker
        return get_sessionmaker()()

    def test_submit_increments_epoch(self, client, wait_task):
        r = client.post("/api/products", json={
            "sku": "EPOCH-SKU-1", "name": "epoch 测试", "category": "home"})
        pid = r.json()["id"]
        t = client.post("/api/listings/tasks",
                        json={"product_id": pid, "markets": ["US"]}).json()[0]
        assert t["epoch"] == 1
        # 等待任务终态后再重试（进行中的任务禁止重试 → 409）
        wait_task("listing", t["id"])
        # 重试 → epoch +1
        r2 = client.post(f"/api/listings/tasks/{t['id']}/retry")
        assert r2.status_code == 200
        assert r2.json()["epoch"] == 2

    def test_finalize_only_when_epoch_matches(self):
        db = self._db()
        try:
            p = Product(sku="EPOCH-FIN-1", name="fin", category="home")
            db.add(p)
            db.flush()
            t = ListingTask(product_id=p.id, market="US", language="en-US",
                            platform="amazon", status="processing", epoch=1)
            db.add(t)
            db.commit()
            tid = t.id
            # epoch 匹配 → 写入成功
            assert TaskQueue.finalize(db, ListingTask, tid, 1,
                                      {"status": "completed"}) is True
            # 模拟重试使 epoch 变 2，旧执行（epoch=1）写入被拒
            db.query(ListingTask).filter(ListingTask.id == tid).update({"epoch": 2})
            db.commit()
            assert TaskQueue.finalize(db, ListingTask, tid, 1,
                                      {"status": "failed"}) is False
            got = db.get(ListingTask, tid)
            assert got.status == "completed", "旧执行不得覆盖重试后的状态"
        finally:
            db.close()

    def test_stale_execution_discarded(self):
        """epoch 不匹配时 service 立即放弃：不写库、不调模型。"""
        from app.services.listing_service import run_listing_task
        db = self._db()
        try:
            p = Product(sku="EPOCH-STALE-1", name="stale", category="home")
            db.add(p)
            db.flush()
            t = ListingTask(product_id=p.id, market="US", language="en-US",
                            platform="amazon", status="pending", epoch=5)
            db.add(t)
            db.commit()
            tid = t.id
            # 传入过期 epoch（4），应直接丢弃
            run_listing_task(db, tid, epoch=4)
            got = db.get(ListingTask, tid)
            assert got.status == "pending", "过期执行不得改变任务状态"
        finally:
            db.close()

    def test_worker_exception_leaves_trace_and_queue_survives(self, client):
        """worker 未捕获异常：任务 failed 留痕，队列继续处理后续任务。"""
        from app.services.task_queue import get_queue

        def boom(db, task_id):
            raise RuntimeError("模拟 worker 爆炸")

        q = get_queue()
        db = self._db()
        try:
            p = Product(sku="EPOCH-EXC-1", name="exc", category="home")
            db.add(p)
            db.flush()
            t = ListingTask(product_id=p.id, market="DE", language="de-DE",
                            platform="amazon", status="pending")
            db.add(t)
            db.commit()
            tid = t.id
        finally:
            db.close()
        q.submit("listing", tid, idempotency_key=f"exc:{tid}",
                 runner=boom)
        # 等待 worker 处理（单 worker 串行）
        import time as _time
        deadline = _time.time() + 15
        status = ""
        while _time.time() < deadline:
            db = self._db()
            try:
                status = db.get(ListingTask, tid).status
            finally:
                db.close()
            if status in ("failed", "completed"):
                break
            _time.sleep(0.3)
        assert status == "failed"
        db = self._db()
        try:
            assert "爆炸" in (db.get(ListingTask, tid).error or "")
        finally:
            db.close()

    def test_timeout_marks_failed_and_epoch_guarded(self):
        """超时后 _mark_failed 尊重 epoch（被重试的任务不误标）。"""
        db = self._db()
        try:
            p = Product(sku="EPOCH-TO-1", name="to", category="home")
            db.add(p)
            db.flush()
            t = ListingTask(product_id=p.id, market="US", language="en-US",
                            platform="amazon", status="processing", epoch=3)
            db.add(t)
            db.commit()
            tid = t.id
            # epoch=2 的过期 job 不得把 epoch=3 的任务标记 failed
            TaskQueue._mark_failed({"kind": "listing", "task_id": tid,
                                    "epoch": 2}, "超时")
            db.refresh(db.get(ListingTask, tid))
            assert db.get(ListingTask, tid).status == "processing"
            # epoch=3 匹配 → 正常标记
            TaskQueue._mark_failed({"kind": "listing", "task_id": tid,
                                    "epoch": 3}, "超时")
            db.refresh(db.get(ListingTask, tid))
            assert db.get(ListingTask, tid).status == "failed"
        finally:
            db.close()


# ============================================================ P1：预算预留
@pytest.fixture
def isolated_db(monkeypatch, tmp_path, settings_env):
    """独立临时数据库：隔离 today_spend 等跨测试状态。"""
    import app.database as dbmod
    from app.config import get_settings
    db_file = tmp_path / "isolated.db"
    settings_env(database_url=f"sqlite:///{db_file.as_posix()}")
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._SessionLocal = None
    init_db()
    yield db_file
    dbmod._engine = None
    dbmod._SessionLocal = None
    get_settings.cache_clear()


class TestBudgetReservation:
    def _fresh_reserve(self):
        global _reserved_usd
        import app.services.task_queue as tq
        tq._reserved_usd = 0.0
        return tq

    def test_reserve_blocks_concurrent_overspend(self, isolated_db, settings_env):
        """并发场景：预留机制阻止同时穿过预算线。"""
        tq = self._fresh_reserve()
        settings_env(daily_budget_usd=0.001, per_task_budget_usd=1.0,
                     unknown_cost_policy="allow")
        # 第一个预留通过
        ok1, _ = TaskQueue.check_and_reserve(0.0008, 1.0)
        assert ok1 is True
        # 第二个（并发）即使单独看也在预算内，也必须被拒绝
        ok2, msg2 = TaskQueue.check_and_reserve(0.0008, 1.0)
        assert ok2 is False
        assert "预留" in msg2
        # 释放后恢复
        TaskQueue.release_reservation(0.0008)
        ok3, _ = TaskQueue.check_and_reserve(0.0008, 1.0)
        assert ok3 is True
        TaskQueue.release_reservation(0.0008)
        assert tq._reserved_usd == 0.0

    def test_unknown_cost_not_reserved(self, isolated_db, settings_env):
        tq = self._fresh_reserve()
        settings_env(daily_budget_usd=0.0001, per_task_budget_usd=1.0,
                     unknown_cost_policy="allow")
        ok, msg = TaskQueue.check_and_reserve(None, 1.0)
        assert ok is True
        assert tq._reserved_usd == 0.0, "未知费用不得预留（也无法预留）"
        assert "费用未知" in msg

    def test_release_is_idempotent_safe(self):
        tq = self._fresh_reserve()
        TaskQueue.release_reservation(0.5)
        assert tq._reserved_usd == 0.0  # 不会变成负数

    def test_per_task_budget_blocks(self, isolated_db, settings_env):
        self._fresh_reserve()
        settings_env(daily_budget_usd=100, per_task_budget_usd=0.01)
        ok, msg = TaskQueue.check_and_reserve(0.05, 0.01)
        assert ok is False
        assert "单任务预算" in msg


# ============================================================ P1：路径安全
class TestPathSafety:
    def test_normal_path_ok(self, tmp_path):
        base = tmp_path / "images"
        base.mkdir()
        target = safe_join(base, "a", "b.png")
        assert target == (base / "a" / "b.png").resolve()

    def test_dotdot_escape_blocked(self, tmp_path):
        base = tmp_path / "images"
        base.mkdir()
        with pytest.raises(ValueError, match="非法路径"):
            safe_join(base, "..", "..", "etc", "passwd")

    def test_absolute_path_blocked(self, tmp_path):
        base = tmp_path / "images"
        base.mkdir()
        with pytest.raises(ValueError, match="非法路径"):
            safe_join(base, "/etc/passwd")

    def test_sibling_prefix_directory_blocked(self, tmp_path):
        """同前缀目录（images_evil）必须被拒绝——startswith 会误放行。"""
        base = tmp_path / "images"
        base.mkdir()
        (tmp_path / "images_evil").mkdir()
        with pytest.raises(ValueError, match="非法路径"):
            safe_join(base, "..", "images_evil", "x.png")

    def test_symlink_escape_blocked(self, tmp_path):
        base = tmp_path / "images"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        link = base / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前文件系统不支持符号链接")
        with pytest.raises(ValueError, match="非法路径"):
            safe_join(base, "link", "secret.txt")

    def test_nonexistent_file_still_resolves(self, tmp_path):
        base = tmp_path / "images"
        base.mkdir()
        target = safe_join(base, "missing.png")
        assert target.name == "missing.png"

    def test_storage_abs_path_rejects_traversal(self):
        from app.services.storage import get_storage
        st = get_storage()
        with pytest.raises(ValueError):
            st.abs_path("../../etc/passwd")
        with pytest.raises(ValueError):
            st.abs_path("images/../../../etc/passwd")

    def test_is_within_helper(self, tmp_path):
        from app.security import is_within
        base = tmp_path / "images"
        base.mkdir()
        assert is_within(base, base / "a.png")
        assert not is_within(base, tmp_path / "images_evil" / "a.png")


# ============================================================ P1：图片下载
class TestImageDownloadSafety:
    def test_content_type_enforced(self, monkeypatch, settings_env):
        from app.security import safe_download
        settings_env(allow_insecure_download=True)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  content=b"<html>not an image</html>")

        _patch_client(monkeypatch, handler)
        with pytest.raises(ValueError, match="内容类型"):
            safe_download("https://example.com/x.png")

    def test_oversized_response_blocked(self, monkeypatch, settings_env):
        from app.security import safe_download
        settings_env(allow_insecure_download=True)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "image/png"},
                                  content=b"\x89PNG\r\n\x1a\n" + b"x" * 5000)

        _patch_client(monkeypatch, handler)
        with pytest.raises(ValueError, match="大小上限"):
            safe_download("https://example.com/big.png", max_bytes=100)

    def test_non_http_scheme_blocked(self):
        from app.security import safe_download
        with pytest.raises(ValueError, match="协议"):
            safe_download("file:///etc/passwd")

    def test_decode_skips_single_invalid_keeps_rest(self, monkeypatch,
                                                    settings_env):
        """单张不可用不拖垮整批；全部不可用才抛错。"""
        settings_env(image_api_base="https://api.example.com/v1",
                     image_api_key="k", image_model="gpt-image-1")
        good = base64.b64encode(_png_bytes()).decode()
        from app.services.ai.openai_image import OpenAIImageAdapter
        img_adapter = OpenAIImageAdapter("https://api.example.com/v1", "k",
                                         "gpt-image-1")
        out = img_adapter._decode({"data": [
            {"url": "https://169.254.169.254/meta"},   # SSRF：跳过
            {"b64_json": "not-base64!!"},               # 解码失败：跳过
            {"b64_json": good},                          # 有效：保留
        ]})
        assert len(out) == 1

    def test_decode_all_invalid_raises(self):
        from app.services.ai.openai_image import OpenAIImageAdapter
        img_adapter = OpenAIImageAdapter("https://api.example.com/v1", "k",
                                         "gpt-image-1")
        with pytest.raises(ValueError, match="无一可用"):
            img_adapter._decode({"data": [{"url": "https://127.0.0.1/x.png"}]})

    def test_decode_empty_data(self):
        from app.services.ai.openai_image import OpenAIImageAdapter
        img_adapter = OpenAIImageAdapter("https://api.example.com/v1", "k",
                                         "gpt-image-1")
        assert img_adapter._decode({"data": []}) == []


# ============================================================ P1：数据库迁移
class TestMigrations:
    """迁移幂等、V1.0 旧库升级、备份、数据保留。"""

    def _make_v10_old_db(self, tmp_path) -> Path:
        """构造一个 V1.0 风格的旧库：cost_usd NOT NULL，无 epoch/price_version。"""
        db_file = tmp_path / "old_v10.db"
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, sku VARCHAR(64) UNIQUE, name VARCHAR(255),
            brand VARCHAR(128), model VARCHAR(128), category VARCHAR(64),
            source_text TEXT, is_demo BOOLEAN, created_at DATETIME, updated_at DATETIME);
        CREATE TABLE listing_tasks (
            id INTEGER PRIMARY KEY, product_id INTEGER, platform VARCHAR(32),
            market VARCHAR(8), language VARCHAR(16), status VARCHAR(16),
            is_simulated BOOLEAN, model_name VARCHAR(64), error TEXT,
            cost_usd FLOAT NOT NULL DEFAULT 0, duration_ms INTEGER,
            idempotency_key VARCHAR(128), created_at DATETIME, updated_at DATETIME);
        CREATE TABLE image_gen_tasks (
            id INTEGER PRIMARY KEY, product_id INTEGER, image_type VARCHAR(32),
            platform VARCHAR(32), market VARCHAR(8), language VARCHAR(16),
            aspect_ratio VARCHAR(16), count INTEGER, style VARCHAR(128),
            background VARCHAR(128), prompt TEXT, ref_image_ids JSON,
            status VARCHAR(16), is_simulated BOOLEAN, model_name VARCHAR(64),
            error TEXT, cost_usd FLOAT NOT NULL DEFAULT 0, duration_ms INTEGER,
            idempotency_key VARCHAR(128), created_at DATETIME);
        CREATE TABLE api_call_logs (
            id INTEGER PRIMARY KEY, provider VARCHAR(32), model VARCHAR(64),
            purpose VARCHAR(64), status VARCHAR(16), latency_ms INTEGER,
            cost_usd FLOAT NOT NULL DEFAULT 0, tokens_in INTEGER,
            tokens_out INTEGER, error TEXT, created_at DATETIME);
        INSERT INTO products (sku, name, category) VALUES ('OLD-SKU-1', '旧库商品', 'home');
        INSERT INTO listing_tasks (product_id, market, language, status, cost_usd)
            VALUES (1, 'US', 'en-US', 'completed', 0.0123);
        INSERT INTO api_call_logs (provider, model, purpose, status, cost_usd)
            VALUES ('openai-compatible', 'gpt-4o-mini', 'listing', 'success', 0.0123);
        """)
        conn.commit()
        conn.close()
        return db_file

    def test_v10_old_database_upgrades_with_data_preserved(self, monkeypatch,
                                                           tmp_path,
                                                           settings_env):
        """V1.0 旧库经迁移升级到 V1.2：新列就位、数据保留、无清库。"""
        db_file = self._make_v10_old_db(tmp_path)
        settings_env(database_url=f"sqlite:///{db_file.as_posix()}")
        result = apply_migrations()
        # 迁移前自动备份
        assert result["backup"] is not None
        assert Path(result["backup"]).exists()
        # 校验新 schema
        conn = sqlite3.connect(db_file)
        try:
            cur = conn.cursor()
            cols = {r[1] for r in cur.execute("PRAGMA table_info(listing_tasks)")}
            assert "epoch" in cols
            tcols = {r[1] for r in cur.execute("PRAGMA table_info(api_call_logs)")}
            assert "cost_basis" in tcols and "price_version" in tcols
            # cost_usd 已可空：插入 NULL 不再报错
            cur.execute("INSERT INTO listing_tasks (product_id, market, language,"
                        " status, cost_usd) VALUES (1, 'DE', 'de-DE', 'failed', NULL)")
            conn.commit()
            # 旧数据保留
            row = cur.execute("SELECT cost_usd FROM listing_tasks WHERE market='US'").fetchone()
            assert abs(row[0] - 0.0123) < 1e-9
            log = cur.execute("SELECT cost_usd FROM api_call_logs").fetchone()
            assert abs(log[0] - 0.0123) < 1e-9
        finally:
            conn.close()

    def test_migrations_are_idempotent(self, monkeypatch, tmp_path,
                                       settings_env):
        """重复执行迁移不得报错（create_all 新库 + 迁移并存场景）。"""
        db_file = tmp_path / "fresh.db"
        settings_env(database_url=f"sqlite:///{db_file.as_posix()}")
        # 先 create_all（模拟 init_db 已建新 schema）
        import app.database as dbmod
        from app.config import get_settings
        get_settings.cache_clear()
        dbmod._engine = None
        dbmod._SessionLocal = None
        init_db()
        r1 = apply_migrations()
        r2 = apply_migrations()  # 第二次必须无错
        assert r1["revision"] == "head" and r2["revision"] == "head"

    def test_migration_failure_does_not_wipe_database(self, monkeypatch,
                                                      tmp_path, settings_env):
        """迁移失败：数据库保持原样（回滚），备份保留，抛出 RuntimeError。"""
        db_file = tmp_path / "failcase.db"
        conn = sqlite3.connect(db_file)
        conn.execute("CREATE TABLE keepme (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO keepme (v) VALUES ('original-data')")
        conn.commit()
        conn.close()
        settings_env(database_url=f"sqlite:///{db_file.as_posix()}")

        # 注入一个必然失败的迁移脚本（语法/逻辑错误）
        versions = Path(__file__).resolve().parent.parent / "migrations" / "versions"
        bad = versions / "9999_bad_migration_for_test.py"
        bad.write_text(
            "revision = '9999_bad_migration_for_test'\n"
            "down_revision = '0003_v12_epoch_cost_columns'\n"
            "def upgrade():\n"
            "    raise RuntimeError('模拟迁移失败')\n"
            "def downgrade():\n"
            "    pass\n", encoding="utf-8")
        try:
            with pytest.raises(RuntimeError, match="迁移失败"):
                apply_migrations()
        finally:
            bad.unlink(missing_ok=True)
        # 数据原样保留
        conn = sqlite3.connect(db_file)
        try:
            row = conn.execute("SELECT v FROM keepme").fetchone()
            assert row == ("original-data",)
        finally:
            conn.close()


# ============================================================ P1：成本追溯
class TestCostTraceability:
    def test_pricing_version_defined(self):
        assert PRICING_VERSION

    def test_cost_logs_expose_basis_and_version(self, client):
        """cost-logs 响应必须包含费用依据与价格版本字段。"""
        client.get("/api/settings/cost-logs")
        r = client.post("/api/products", json={
            "sku": "COST-TRACE-2", "name": "成本追溯2", "category": "home"})
        pid = r.json()["id"]
        t = client.post("/api/listings/tasks",
                        json={"product_id": pid, "markets": ["US"]}).json()[0]
        import time as _time
        deadline = _time.time() + 20
        while _time.time() < deadline:
            cur = client.get(f"/api/listings/tasks/{t['id']}").json()
            if cur["status"] in ("completed", "failed"):
                break
            _time.sleep(0.3)
        logs = client.get("/api/settings/cost-logs").json()
        items = logs.get("items", logs) if isinstance(logs, dict) else logs
        assert items, "应有调用日志"
        assert all("cost_basis" in it and "price_version" in it for it in items), \
            "调用日志必须包含 cost_basis 与 price_version 字段"

    def test_real_call_records_pricing_version(self, monkeypatch, settings_env):
        """真实（mock HTTP）调用落库：price_version 与 PRICING_VERSION 一致。"""
        from app.database import get_sessionmaker
        from app.services.listing_service import run_listing_task
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="k", text_model="gpt-4o-mini")

        def handler(request: httpx.Request) -> httpx.Response:
            payload = {"title": "T", "bullets": ["b1"], "description": "d",
                       "faq": [], "search_terms": "", "image_alt": "",
                       "marketing_slogan": "", "localization_note": "",
                       "risk_note": ""}
            return httpx.Response(200, json=_ok_chat_payload(json.dumps(payload)))

        _patch_client(monkeypatch, handler)
        db = get_sessionmaker()()
        try:
            p = Product(sku="COST-REAL-1", name="real", category="home",
                        source_text="材质：304 不锈钢")
            db.add(p)
            db.flush()
            t = ListingTask(product_id=p.id, market="US", language="en-US",
                            platform="amazon", status="pending", epoch=1)
            db.add(t)
            db.commit()
            tid = t.id
        finally:
            db.close()
        db = get_sessionmaker()()
        try:
            run_listing_task(db, tid, epoch=1)
            log = db.query(ApiCallLog).filter(
                ApiCallLog.purpose == "listing",
                ApiCallLog.status == "success").order_by(ApiCallLog.id.desc()).first()
            assert log is not None, "应有成功调用日志"
            assert log.price_version == PRICING_VERSION
            assert log.cost_basis == "estimated"
            assert log.cost_usd is not None and log.cost_usd > 0
        finally:
            db.close()

    def test_cost_logs_do_not_leak_key(self, client, settings_env):
        settings_env(text_api_base="https://api.example.com/v1",
                     text_api_key="sk-leak-check-987654",
                     text_model="gpt-4o-mini")
        r = client.get("/api/settings/cost-logs")
        assert "sk-leak-check-987654" not in r.text
