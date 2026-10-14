"""后台任务队列：asyncio 队列 + 单 worker，支持重试、幂等去重、预算控制。

架构上保持与 Celery/Redis 可替换：任务逻辑全部封装在 services 层，
队列只负责任务调度与状态管理。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from ..database import get_sessionmaker
from ..models import ApiCallLog, ListingTask, ImageGenTask


class TaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._inflight: set[str] = set()  # 幂等键去重（进行中）
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.started = False
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    # ---------------------------------------------------------------- 提交
    def submit(self, kind: str, task_id: int, idempotency_key: str = "",
               runner: Callable[[Any, int], Any] | None = None) -> str:
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
            if kind == "listing":
                t = db.get(ListingTask, task_id)
            else:
                t = db.get(ImageGenTask, task_id)
            if t is None:
                raise ValueError("任务不存在")
            t.idempotency_key = idempotency_key
            t.status = "pending"
            db.commit()
        finally:
            db.close()
        self._inflight.add(idempotency_key)
        self._queue.put_nowait({"kind": kind, "task_id": task_id,
                                "idempotency_key": idempotency_key, "runner": runner})
        return idempotency_key

    def submit_many(self, items: list[tuple[str, int, str]]) -> list[str]:
        return [self.submit(kind, tid, key) for kind, tid, key in items]

    # ---------------------------------------------------------------- 执行
    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._execute(job)
            except Exception:  # noqa: BLE001 worker 不死
                pass
            finally:
                self._inflight.discard(job.get("idempotency_key"))
                self._queue.task_done()

    async def _execute(self, job: dict) -> None:
        kind = job["kind"]
        task_id = job["task_id"]
        runner = job["runner"]
        sm = get_sessionmaker()
        db = sm()
        try:
            await asyncio.to_thread(self._run_sync, db, kind, task_id, runner)
        finally:
            db.close()

    @staticmethod
    def _run_sync(db, kind: str, task_id: int, runner) -> None:
        from ..services.listing_service import run_listing_task
        from ..services.image_service import run_image_task
        fn = runner or (run_listing_task if kind == "listing" else run_image_task)
        try:
            fn(db, task_id)
        except Exception as e:  # noqa: BLE001
            model = ListingTask if kind == "listing" else ImageGenTask
            t = db.get(model, task_id)
            if t is not None and t.status not in ("completed", "partial"):
                t.status = "failed"
                t.error = f"队列执行异常：{e}"
                db.commit()

    # ---------------------------------------------------------------- 重试
    def retry(self, kind: str, task_id: int) -> str:
        return self.submit(kind, task_id,
                           idempotency_key=f"{kind}:{task_id}:retry:{uuid.uuid4().hex[:8]}")

    # ---------------------------------------------------------------- 预算
    @staticmethod
    def today_spend_usd() -> float:
        sm = get_sessionmaker()
        db = sm()
        try:
            start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            rows = db.query(ApiCallLog).filter(ApiCallLog.created_at >= start).all()
            return round(sum(r.cost_usd or 0.0 for r in rows), 6)
        finally:
            db.close()

    @staticmethod
    def check_budget(estimated_cost: float, per_task_budget: float) -> tuple[bool, str]:
        spend = TaskQueue.today_spend_usd()
        from ..config import effective_settings
        daily = effective_settings().daily_budget_usd
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
