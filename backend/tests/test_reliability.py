"""V1.1 可靠性测试：worker 异常留痕、重启任务恢复、执行超时、
并发提交去重、预算限制、未知模型成本处理、JSON/尺寸兼容性。

覆盖审计发现的问题：
- worker 异常曾被静默吞掉（无日志无状态）→ 必须留痕且队列继续存活
- 重启后 pending/processing 任务静默丢失 → 启动必须对账
- 预算检查函数从未被调用 → 执行前必须检查
- 未知模型价格曾被按 0 费用处理 → 必须标记为未知
"""
from __future__ import annotations

import time

import pytest

from app.database import get_sessionmaker
from app.models import ApiCallLog, ImageGenTask, ListingTask
from app.services.task_queue import TaskQueue, get_queue


@pytest.fixture
def settings_env(monkeypatch):
    """临时修改 PL_ 环境变量并清空 settings 缓存。"""
    from app.config import get_settings

    def _set(**kw):
        for k, v in kw.items():
            monkeypatch.setenv(f"PL_{k.upper()}", str(v))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _db():
    return get_sessionmaker()()


class TestWorkerReliability:
    """worker 异常与超时。"""

    def test_worker_exception_is_recorded_and_queue_survives(self, client, product_id):
        """runner 抛异常：任务标记 failed 且错误留痕；队列后续任务仍能执行。"""
        queue = get_queue()
        db = _db()
        task = ListingTask(product_id=product_id, platform="amazon", market="US",
                           language="en-US", status="pending")
        db.add(task)
        db.commit()
        task_id = task.id
        db.close()

        def boom(db_session, tid):
            raise RuntimeError("模拟 worker 内部崩溃")

        queue.submit("listing", task_id, runner=boom)
        # 等待任务进入终态
        deadline = time.time() + 15
        status = None
        while time.time() < deadline:
            db = _db()
            t = db.get(ListingTask, task_id)
            status = t.status
            err = t.error
            db.close()
            if status in ("failed", "completed", "partial"):
                break
            time.sleep(0.2)
        assert status == "failed", f"任务应被标记 failed，实际 {status}"
        assert "模拟 worker 内部崩溃" in (err or "")

        # 队列仍存活：再提交一个正常任务可以完成
        db = _db()
        t2 = ListingTask(product_id=product_id, platform="amazon", market="UK",
                         language="en-GB", status="pending")
        db.add(t2)
        db.commit()
        t2_id = t2.id
        db.close()
        queue.submit("listing", t2_id)
        deadline = time.time() + 30
        while time.time() < deadline:
            db = _db()
            st = db.get(ListingTask, t2_id).status
            db.close()
            if st in ("completed", "failed", "partial"):
                break
            time.sleep(0.2)
        assert st == "completed", f"worker 应继续处理后续任务，实际 {st}"

    def test_task_timeout_marks_failed(self, client, product_id, settings_env):
        """超过 PL_TASK_TIMEOUT_SEC 的任务标记失败（不永久卡在 processing）。"""
        settings_env(task_timeout_sec=1)
        queue = get_queue()
        db = _db()
        task = ImageGenTask(product_id=product_id, image_type="main", market="US",
                            language="en-US", aspect_ratio="1:1", count=1, status="pending")
        db.add(task)
        db.commit()
        task_id = task.id
        db.close()

        def slow_runner(db_session, tid):
            time.sleep(5)

        queue.submit("image", task_id, runner=slow_runner)
        deadline = time.time() + 20
        status = None
        err = ""
        while time.time() < deadline:
            db = _db()
            t = db.get(ImageGenTask, task_id)
            status, err = t.status, t.error
            db.close()
            if status in ("failed", "completed", "partial"):
                break
            time.sleep(0.2)
        assert status == "failed", f"超时任务应标记 failed，实际 {status}"
        assert "超时" in (err or "")


class TestRestartRecovery:
    """服务重启后的任务对账。"""

    def test_pending_task_requeued_after_restart(self, client, product_id):
        """重启前遗留 pending 任务：recover_on_startup 重新入队并最终完成。"""
        queue = get_queue()
        db = _db()
        task = ListingTask(product_id=product_id, platform="amazon", market="DE",
                           language="de-DE", status="pending")
        db.add(task)
        db.commit()
        task_id = task.id
        db.close()

        stats = queue.recover_on_startup()
        assert stats["requeued"] >= 1

        deadline = time.time() + 30
        while time.time() < deadline:
            db = _db()
            st = db.get(ListingTask, task_id).status
            db.close()
            if st in ("completed", "failed", "partial"):
                break
            time.sleep(0.2)
        assert st == "completed", f"恢复的排队任务应执行完成，实际 {st}"

    def test_processing_task_marked_failed_after_restart(self, client, product_id):
        """重启前遗留 processing 任务：标记 failed（不静默卡死），可重试。"""
        queue = get_queue()
        db = _db()
        task = ImageGenTask(product_id=product_id, image_type="scene", market="US",
                            language="en-US", aspect_ratio="1:1", count=1,
                            status="processing")
        db.add(task)
        db.commit()
        task_id = task.id
        db.close()

        stats = queue.recover_on_startup()
        assert stats["failed"] >= 1

        db = _db()
        t = db.get(ImageGenTask, task_id)
        assert t.status == "failed"
        assert "重启" in (t.error or "")
        db.close()


class TestDuplicateSubmission:
    """重复提交去重（防重复扣费）。"""

    def test_concurrent_duplicate_tasks_deduped(self, client, product_id):
        """并发提交相同商品+平台+市场任务：只应创建一个待处理任务。"""
        import concurrent.futures

        def submit(_):
            # ES 市场：避免与其他测试已创建的市场冲突（查重只针对 pending/processing）
            return client.post("/api/listings/tasks", json={
                "product_id": product_id, "platform": "amazon", "markets": ["ES"]})

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(submit, range(5)))

        ids = set()
        for r in results:
            assert r.status_code == 200
            ids.add(r.json()[0]["id"])
        assert len(ids) == 1, f"并发重复提交应去重为 1 个任务，实际 {len(ids)}"

        db = _db()
        count = db.query(ListingTask).filter(
            ListingTask.product_id == product_id,
            ListingTask.market == "ES").count()
        db.close()
        assert count == 1, f"DB 中应只有 1 个法国市场任务，实际 {count}"


class TestBudgetControl:
    """预算限制（执行前检查 + 并发安全）。"""

    def test_budget_blocks_execution_when_daily_exceeded(self, client, product_id,
                                                         settings_env):
        """每日预算为 0 时任务必须失败并提示预算（验证检查真实生效）。

        配置（假的）文本 API 使任务走真实调用分支——预算检查在调用前执行，
        未通过即失败，不会真正发起网络请求。
        """
        settings_env(daily_budget_usd=0,
                     text_api_base="https://api.example.com/v1",
                     text_api_key="test-key-for-budget-check")
        r = client.post("/api/listings/tasks", json={
            "product_id": product_id, "platform": "amazon", "markets": ["IT"]})
        assert r.status_code == 200
        task_id = r.json()[0]["id"]
        deadline = time.time() + 30
        status, err = None, ""
        while time.time() < deadline:
            t = client.get(f"/api/listings/tasks/{task_id}").json()
            status, err = t["status"], t["error"]
            if status in ("completed", "failed", "partial"):
                break
            time.sleep(0.2)
        assert status == "failed", f"预算不足任务应失败，实际 {status}"
        assert "预算" in (err or "")

    def test_check_budget_is_lock_protected(self):
        """check_budget 必须持有并发锁（竞态防护的基础）。"""
        from app.services import task_queue as tq
        assert isinstance(tq._budget_lock, type(threading_lock()))
        # 基本逻辑：花费 + 预估 超限 → 拒绝
        ok, msg = TaskQueue.check_budget(1e9, 2.0)
        assert ok is False
        assert "单任务预算" in msg
        ok2, msg2 = TaskQueue.check_budget(0.0001, 2.0)
        assert ok2 is True

    def test_today_spend_ignores_unknown_costs(self):
        """今日花费只统计费用已知的调用（NULL 不计入）。"""
        db = _db()
        db.add(ApiCallLog(provider="openai-compatible", model="m", purpose="image",
                          status="success", cost_usd=0.5))
        db.add(ApiCallLog(provider="openai-compatible", model="unknown-model",
                          purpose="image", status="success", cost_usd=None))
        db.commit()
        spend = TaskQueue.today_spend_usd()
        unknown = TaskQueue.today_unknown_cost_calls()
        db.close()
        assert spend >= 0.5
        assert unknown >= 1


def threading_lock():
    import threading
    return threading.Lock()


class TestUnknownCostHandling:
    """未知模型价格：不得按 0 费用处理。"""

    def test_text_unknown_model_returns_none(self):
        from app.services.ai.openai_text import OpenAITextAdapter
        a = OpenAITextAdapter("https://api.example.com/v1", "k", "some-unknown-model")
        assert a.estimate_cost(1000, 1000) is None
        assert a.price_known() is False
        known = OpenAITextAdapter("https://api.example.com/v1", "k", "gpt-4o-mini")
        assert known.estimate_cost(1000, 1000) == pytest.approx(0.00015 + 0.0006)
        assert known.price_known() is True

    def test_image_unknown_model_returns_none(self):
        from app.services.ai.openai_image import OpenAIImageAdapter
        a = OpenAIImageAdapter("https://api.example.com/v1", "k", "mystery-image-model")
        assert a.estimate_cost(3) is None
        assert a.price_known() is False
        known = OpenAIImageAdapter("https://api.example.com/v1", "k", "gpt-image-1")
        assert known.estimate_cost(3) == pytest.approx(0.12)

    def test_check_budget_unknown_cost_policy(self, settings_env):
        """未知费用：allow 策略放行并提示；block 策略拒绝。"""
        settings_env(unknown_cost_policy="allow")
        ok, msg = TaskQueue.check_budget(None, 2.0)
        assert ok is True
        assert "费用未知" in msg

        settings_env(unknown_cost_policy="block")
        ok2, msg2 = TaskQueue.check_budget(None, 2.0)
        assert ok2 is False
        assert "费用未知" in msg2

    def test_overview_reports_unknown_cost_calls(self, client):
        r = client.get("/api/tasks/overview")
        assert r.status_code == 200
        assert "today_unknown_cost_calls" in r.json()


class TestProviderCompatibility:
    """不同供应商兼容性：JSON 输出模式降级、图像尺寸映射。"""

    def test_image_size_mapping_per_model(self):
        from app.services.ai.openai_image import OpenAIImageAdapter
        dalle3 = OpenAIImageAdapter("https://api.example.com/v1", "k", "dall-e-3")
        assert dalle3.size_for("16:9") == "1792x1024"
        assert dalle3.size_for("3:4") == "1024x1792"
        gpt = OpenAIImageAdapter("https://api.example.com/v1", "k", "gpt-image-1")
        assert gpt.size_for("1:1") == "1024x1024"
        assert gpt.size_for("9:16") == "1024x1536"

    def test_unsupported_ratio_raises_clear_error(self):
        from app.services.ai.openai_image import OpenAIImageAdapter
        a = OpenAIImageAdapter("https://api.example.com/v1", "k", "dall-e-2")
        with pytest.raises(ValueError, match="不支持画幅"):
            a.size_for("21:9")

    def test_text_json_mode_configurable(self, settings_env):
        """text_json_mode 配置生效（none 时不发送 response_format）。"""
        settings_env(text_json_mode="none")
        from app.services.ai.openai_text import OpenAITextAdapter
        from app.config import effective_settings
        a = OpenAITextAdapter("https://api.example.com/v1", "k", "gpt-4o-mini",
                              json_mode=effective_settings().text_json_mode)
        assert a.json_mode == "none"

    def test_simulated_mode_preserved_without_api(self, client, product_id, wait_task):
        """未配置 API：模拟模式保留且明确标记（不得伪造真实结果）。"""
        r = client.post("/api/images/tasks", json={
            "product_id": product_id, "image_type": "main", "market": "US",
            "aspect_ratio": "1:1", "count": 1})
        task = wait_task("image", r.json()["id"])
        assert task["is_simulated"] is True
        assert task["cost_usd"] is None  # 模拟不产生费用，也不伪造已知费用
