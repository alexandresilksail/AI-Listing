"""后台任务队列：独立后台线程 + 自有事件循环，支持重试、幂等去重、预算控制。

V1.1 可靠性修复：
- worker 运行在独立守护线程（自有事件循环），与 Web 请求循环解钩：
  任意请求循环提交任务都通过 call_soon_threadsafe 安全入队，
  重启/多客户端场景不会出现“跨事件循环”挂起。
- worker 异常全部记录日志并落库（不再静默吞掉）
- 单任务执行超时（PL_TASK_TIMEOUT_SEC），超时标记 failed
- 启动时恢复遗留任务：pending 重新入队；processing 标记 failed（可重试），
  杜绝重启后任务静默丢失或永久卡死
- 预算检查加进程内锁，且执行前真实检查（此前 check_budget 从未被调用）

架构上保持与 Celery/Redis 可替换：任务逻辑全部封装在 services 层，
队列只负责任务调度与状态管理。生产环境如需多 worker / 跨进程，
建议替换为 Redis + Celery（任务状态与去重已在 DB 层，迁移成本低）。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from ..database import get_sessionmaker
from ..models import ApiCallLog, ListingTask, ImageGenTask

logger = logging.getLogger("polylisting.queue")

# 预算检查锁：防止并发任务同时通过检查而突破每日预算
_budget_lock = threading.Lock()


class TaskQueue:
    """单 worker 任务队列（后台线程 + 独立事件循环）。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue | None = None
        self._inflight: set[str] = set()  # 幂等键去重（进行中）
        self.started = False
        self._start_lock = threading.Lock()

    # ---------------------------------------------------------------- 生命周期
    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._queue = asyncio.Queue()
        task = loop.create_task(self._run())
        try:
            loop.run_until_complete(task)
        except RuntimeError:
            # loop.stop() 被调用（服务关闭）：主动取消 worker 再退出
            task.cancel()
            try:
                loop.run_until_complete(task)
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            loop.close()
            asyncio.set_event_loop(None)
            self._loop = None
            self._queue = None

    async def start(self) -> None:
        with self._start_lock:
            if self.started and self._thread and self._thread.is_alive():
                return
            self.started = True
            self._thread = threading.Thread(
                target=self._thread_main, daemon=True, name="polylisting-queue")
            self._thread.start()
            logger.info("任务队列线程已启动")

    async def stop(self) -> None:
        self.started = False
        loop = self._loop
        thread = self._thread
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        if thread is not None:
            thread.join(timeout=10)
        self._thread = None
        logger.info("任务队列线程已停止")

    # ---------------------------------------------------------------- 提交
    def submit(self, kind: str, task_id: int, idempotency_key: str = "",
               runner=None) -> str:
        """提交任务。幂等键已存在（pending/processing）时返回原任务不重复提交。"""
        if not idempotency_key:
            idempotency_key = f"{kind}:{task_id}:{uuid.uuid4().hex[:8]}"
        if idempotency_key in self._inflight:
            return idempotency_key
        sm = get_sessionmaker()
        db = sm()
        try:
            model = ListingTask if kind == "listing" else ImageGenTask
            dup = db.query(model).filter(
                model.idempotency_key == idempotency_key,
                model.status.in_(["pending", "processing"])).first()
            if dup:
                return idempotency_key
            t = db.get(model, task_id)
            if t is None:
                raise ValueError("任务不存在")
            t.idempotency_key = idempotency_key
            t.status = "pending"
            db.commit()
        finally:
            db.close()
        self._inflight.add(idempotency_key)
        self._enqueue({"kind": kind, "task_id": task_id,
                       "idempotency_key": idempotency_key, "runner": runner})
        return idempotency_key

    def submit_many(self, items: list[tuple[str, int, str]]) -> list[str]:
        return [self.submit(kind, tid, key) for kind, tid, key in items]

    def _enqueue(self, job: dict) -> None:
        """线程安全入队：跨循环/跨线程调用均安全。"""
        loop, queue = self._loop, self._queue
        if loop is not None and queue is not None and loop.is_running():
            loop.call_soon_threadsafe(queue.put_nowait, job)
        else:
            # 队列线程未运行：任务保持 pending，下次启动由 recover_on_startup 恢复
            logger.warning("任务队列未运行，任务 %s#%s 保持 pending 等待恢复",
                           job.get("kind"), job.get("task_id"))

    # ---------------------------------------------------------------- 执行
    async def _run(self) -> None:
        queue = self._queue
        assert queue is not None
        while True:
            job = await queue.get()
            try:
                await self._execute(job)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 worker 不死，且必须留痕
                logger.exception("worker 执行任务异常 kind=%s task_id=%s: %s",
                                 job.get("kind"), job.get("task_id"), e)
                self._mark_failed(job, f"worker 异常：{e}")
            finally:
                self._inflight.discard(job.get("idempotency_key"))
                queue.task_done()

    async def _execute(self, job: dict) -> None:
        kind = job["kind"]
        task_id = job["task_id"]
        runner = job["runner"]
        sm = get_sessionmaker()
        db = sm()
        try:
            from ..config import effective_settings
            timeout = effective_settings().task_timeout_sec
            await asyncio.wait_for(
                asyncio.to_thread(self._run_sync, db, kind, task_id, runner),
                timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("任务超时 kind=%s task_id=%s", kind, task_id)
            self._mark_failed(job, f"任务执行超时（>{timeout}s），请重试或减少生成数量")
        finally:
            db.close()

    @staticmethod
    def _run_sync(db, kind: str, task_id: int, runner) -> None:
        from ..services.listing_service import run_listing_task
        from ..services.image_service import run_image_task
        fn = runner or (run_listing_task if kind == "listing" else run_image_task)
        fn(db, task_id)

    @staticmethod
    def _mark_failed(job: dict, error: str) -> None:
        """把未终态任务标记为 failed（worker 异常/超时对账）。"""
        kind, task_id = job.get("kind"), job.get("task_id")
        if not kind or not task_id:
            return
        sm = get_sessionmaker()
        db = sm()
        try:
            model = ListingTask if kind == "listing" else ImageGenTask
            t = db.get(model, task_id)
            if t is not None and t.status not in ("completed", "partial"):
                t.status = "failed"
                t.error = error
                db.commit()
                logger.info("任务已标记失败 kind=%s id=%s: %s", kind, task_id, error)
        except Exception:  # noqa: BLE001
            logger.exception("标记任务失败时出错 kind=%s id=%s", kind, task_id)
        finally:
            db.close()

    # ---------------------------------------------------------------- 重试
    def retry(self, kind: str, task_id: int) -> str:
        return self.submit(kind, task_id,
                           idempotency_key=f"{kind}:{task_id}:retry:{uuid.uuid4().hex[:8]}")

    # ---------------------------------------------------------------- 恢复
    def recover_on_startup(self) -> dict:
        """启动时对账遗留任务（服务重启后内存队列丢失）：

        - pending：未开始执行，重新入队（不静默丢失排队任务）
        - processing：执行中被重启中断，标记 failed（保留已成功产出，可重试）
        返回对账统计。
        """
        sm = get_sessionmaker()
        db = sm()
        stats = {"requeued": 0, "failed": 0}
        try:
            for model, kind in ((ListingTask, "listing"), (ImageGenTask, "image")):
                pendings = db.query(model).filter(model.status == "pending").all()
                for t in pendings:
                    logger.info("恢复排队任务 %s id=%s", kind, t.id)
                    stats["requeued"] += 1
                processings = db.query(model).filter(model.status == "processing").all()
                for t in processings:
                    t.status = "failed"
                    t.error = "服务重启导致任务中断（原执行未完成），请重试；已成功生成的内容会保留"
                    stats["failed"] += 1
                    logger.info("遗留 processing 任务标记失败 %s id=%s", kind, t.id)
                db.commit()
                for t in pendings:
                    self.submit(kind, t.id,
                                idempotency_key=f"{kind}:{t.id}:recover:{uuid.uuid4().hex[:8]}")
            if stats["requeued"] or stats["failed"]:
                logger.info("启动对账完成：重新入队 %d，标记失败 %d",
                            stats["requeued"], stats["failed"])
            return stats
        finally:
            db.close()

    # ---------------------------------------------------------------- 预算
    @staticmethod
    def today_spend_usd() -> float:
        """今日已花费（仅统计费用已知的调用；未知费用不计入）。"""
        sm = get_sessionmaker()
        db = sm()
        try:
            start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
            rows = db.query(ApiCallLog).filter(
                ApiCallLog.created_at >= start,
                ApiCallLog.cost_usd.isnot(None)).all()
            return round(sum(r.cost_usd or 0.0 for r in rows), 6)
        finally:
            db.close()

    @staticmethod
    def today_unknown_cost_calls() -> int:
        """今日费用未知的调用次数（用于提示预算控制盲区）。"""
        sm = get_sessionmaker()
        db = sm()
        try:
            start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
            return db.query(ApiCallLog).filter(
                ApiCallLog.created_at >= start,
                ApiCallLog.cost_usd.is_(None),
                ApiCallLog.status == "success").count()
        finally:
            db.close()

    @staticmethod
    def check_budget(estimated_cost: float | None,
                     per_task_budget: float) -> tuple[bool, str]:
        """预算检查（持锁执行，覆盖并发提交）。

        estimated_cost 为 None 表示费用未知（模型不在价格表）：
        - policy=block：拒绝执行
        - policy=allow：放行但返回提示（调用方需标记费用未知）
        """
        from ..config import effective_settings
        s = effective_settings()
        with _budget_lock:
            spend = TaskQueue.today_spend_usd()
            daily = s.daily_budget_usd
            if estimated_cost is None:
                if s.unknown_cost_policy == "block":
                    return False, ("当前模型不在价格表中，费用未知，且 PL_UNKNOWN_COST_POLICY=block，"
                                   "已拒绝执行。请在设置中更换已知价格模型，或将策略改为 allow。")
                return True, ("费用未知：当前模型不在内置价格表，本次调用费用无法估算，"
                              "未计入每日预算统计，请谨慎使用。")
            if estimated_cost > per_task_budget:
                return False, (f"预估成本 ${estimated_cost:.4f} 超过单任务预算 "
                               f"${per_task_budget:.2f}，请减少生成数量或在设置中调整预算")
            if spend + estimated_cost > daily:
                return False, (f"今日已花费 ${spend:.4f}，加上本次预估 ${estimated_cost:.4f} "
                               f"将超过每日预算 ${daily:.2f}")
            return True, ""


_queue: TaskQueue | None = None


def get_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue
