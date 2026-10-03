from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, replace
from time import monotonic, time

from bilibili_drops_miner.adaptive_concurrency import (
    AdaptiveConcurrencyController,
)
from bilibili_drops_miner.client import BilibiliClient
from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.domain import ApplicationState, RuntimeHealth, TaskSnapshot
from bilibili_drops_miner.logging_utils import redact_sensitive_text
from bilibili_drops_miner.notifier import MultiPlatformNotifier
from bilibili_drops_miner.request_coordinator import AccountRequestCoordinator
from bilibili_drops_miner.task_monitor import AccountTaskMonitor
from bilibili_drops_miner.x25kn_worker import X25KnWorker

LOGGER = logging.getLogger(__name__)

HealthCallback = Callable[[RuntimeHealth], None]
TaskSnapshotCallback = Callable[[TaskSnapshot], None]
RewardsSettledCallback = Callable[[tuple[str, ...]], None]


@dataclass(frozen=True, slots=True)
class SessionPlan:
    room_id: int
    session_no: int


class BilibiliWatchTimeMiner:
    """Run all room sessions in one owned asyncio event loop."""

    def __init__(
        self,
        config: MinerConfig,
        *,
        on_health: HealthCallback | None = None,
        on_task_snapshot: TaskSnapshotCallback | None = None,
        on_rewards_settled: RewardsSettledCallback | None = None,
        request_coordinator: AccountRequestCoordinator | None = None,
    ) -> None:
        self.config = config
        self._on_health = on_health
        self._on_task_snapshot = on_task_snapshot
        self._on_rewards_settled = on_rewards_settled
        self._thread_stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_stop_event: asyncio.Event | None = None
        self._task_monitor: AccountTaskMonitor | None = None
        self._session_tasks: dict[SessionPlan, asyncio.Task] = {}
        self._adaptive_controller: AdaptiveConcurrencyController | None = None
        self._running = False
        self._health = RuntimeHealth()
        self._notifier = MultiPlatformNotifier(config.notify_urls)
        self._request_coordinator = (
            request_coordinator or AccountRequestCoordinator()
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def health(self) -> RuntimeHealth:
        return self._health

    def _build_session_plans(
        self,
        sessions_per_room: int | None = None,
    ) -> list[SessionPlan]:
        count = sessions_per_room or self.config.thread_count
        return [
            SessionPlan(room_id=room_id, session_no=session_no)
            for room_id in self.config.room_ids
            for session_no in range(1, count + 1)
        ]

    def run(self) -> None:
        if self._running:
            raise RuntimeError("miner 已在运行")
        self.config.validate()
        self._running = True
        failure = ""
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            failure = redact_sensitive_text(str(exc)) or type(exc).__name__
            raise
        finally:
            self._loop = None
            self._async_stop_event = None
            self._task_monitor = None
            self._session_tasks = {}
            self._adaptive_controller = None
            self._running = False
            self._thread_stop_event.clear()
            self._set_health(
                state=ApplicationState.ERROR if failure else ApplicationState.IDLE,
                active_sessions=0,
                last_error=failure,
            )

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop_event = asyncio.Event()
        if self._thread_stop_event.is_set():
            self._async_stop_event.set()
            return
        if self.config.concurrency_mode == "automatic":
            self._adaptive_controller = AdaptiveConcurrencyController(
                start_in_steady_mode=(
                    self.config.automatic_start_in_steady_mode
                ),
                catchup_sessions=self.config.thread_count,
            )
            sessions_per_room = self._adaptive_controller.target_sessions
            concurrency_phase = self._adaptive_controller.phase
            concurrency_detail = self._adaptive_controller.status_detail
        else:
            sessions_per_room = self.config.thread_count
            concurrency_phase = "fixed"
            concurrency_detail = f"固定并发：每房间 {sessions_per_room} 个会话"
        plans = self._build_session_plans(sessions_per_room)
        self._set_health(
            state=ApplicationState.STARTING,
            target_sessions=len(plans),
            active_sessions=0,
            reconnect_count=0,
            last_error="",
            concurrency_mode=self.config.concurrency_mode,
            concurrency_phase=concurrency_phase,
            concurrency_detail=concurrency_detail,
        )

        uid, uname = await self._probe_login()
        if self._thread_stop_event.is_set():
            return
        if uid:
            LOGGER.info("登录成功: %s (UID: %s)", uname, uid)
        else:
            LOGGER.warning("Cookie 未登录，将以游客模式运行")

        monitor_client = BilibiliClient(self.config.cookie)
        account_label = uname.strip() or "Bilibili 账号"
        if uid:
            account_label = f"{account_label}（UID {uid}）"
        self._task_monitor = AccountTaskMonitor(
            client=monitor_client,
            notifier=self._notifier,
            config=self.config,
            account_label=account_label,
            on_snapshot=self._handle_task_snapshot,
            on_rewards_settled=self._on_rewards_settled,
            request_coordinator=self._request_coordinator,
        )
        monitor_task = asyncio.create_task(
            self._task_monitor.run(), name="account-task-monitor"
        )
        self._resize_session_tasks(sessions_per_room)
        self._set_health(state=ApplicationState.RUNNING)
        LOGGER.info(
            "开始运行: 房间 %s，每房间 %s 个连接，模式 %s（单一异步运行时）",
            self.config.room_ids,
            sessions_per_room,
            self.config.concurrency_mode,
        )

        try:
            await self._async_stop_event.wait()
        finally:
            await self._task_monitor.stop()
            session_tasks = list(self._session_tasks.values())
            for task in session_tasks:
                task.cancel()
            self._session_tasks.clear()
            monitor_task.cancel()
            await asyncio.gather(*session_tasks, monitor_task, return_exceptions=True)
            await monitor_client.close()
            LOGGER.info("所有异步连接已停止")

    async def _probe_login(self) -> tuple[int | None, str]:
        client = BilibiliClient(self.config.cookie)
        try:
            return await client.get_self_info()
        finally:
            await client.close()

    async def _session_loop(self, plan: SessionPlan, index: int) -> None:
        # Start at a bounded rate instead of creating a synchronized request burst.
        delay = (index - 1) * 0.25
        if delay and await self._wait_or_stop(delay):
            return
        client = BilibiliClient(self.config.cookie)
        worker = X25KnWorker(
            client=client,
            config=self.config,
            room_id=plan.room_id,
            session_id=f"s{plan.session_no}",
            stop_event=self._async_stop_event,
            on_heartbeat=self._on_heartbeat,
            on_reconnect=self._on_reconnect,
        )
        self._set_health(active_sessions=self._health.active_sessions + 1)
        try:
            await worker.run_forever()
        finally:
            await client.close()
            self._set_health(active_sessions=max(0, self._health.active_sessions - 1))

    async def _wait_or_stop(self, timeout: float) -> bool:
        if self._async_stop_event is None:
            return True
        try:
            await asyncio.wait_for(self._async_stop_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def stop(self, *, force: bool = False) -> None:
        del (
            force
        )  # cancellation is deterministic; force is retained for API compatibility
        self._thread_stop_event.set()
        loop = self._loop
        stop_event = self._async_stop_event
        if loop is not None and stop_event is not None and loop.is_running():
            loop.call_soon_threadsafe(stop_event.set)
        self._set_health(state=ApplicationState.STOPPING)

    def request_task_refresh(self) -> bool:
        loop = self._loop
        monitor = self._task_monitor
        if loop is None or monitor is None or not loop.is_running():
            return False
        loop.call_soon_threadsafe(monitor.request_refresh)
        return True

    def update_task_ids(self, task_ids: list[str]) -> bool:
        loop = self._loop
        monitor = self._task_monitor
        if loop is None or monitor is None or not loop.is_running():
            self.config.task_ids = list(task_ids)
            return False

        def apply() -> None:
            monitor.update_task_ids(task_ids)

        loop.call_soon_threadsafe(apply)
        return True

    def set_target_sessions_per_room(self, target: int) -> bool:
        loop = self._loop
        if loop is None or not loop.is_running():
            return False
        bounded = max(1, min(128, int(target)))
        loop.call_soon_threadsafe(self._resize_session_tasks, bounded)
        return True

    def force_fixed_sessions_per_room(self, target: int) -> bool:
        """Switch a running miner to a fixed session count without restart."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return False
        bounded = max(1, min(128, int(target)))

        def apply() -> None:
            self._adaptive_controller = None
            self.config.concurrency_mode = "fixed"
            self.config.thread_count = bounded
            self._resize_session_tasks(bounded)
            self._set_health(
                concurrency_mode="fixed",
                concurrency_phase="fixed",
                concurrency_detail=(
                    f"手动加速：每房间固定 {bounded} 个会话"
                ),
            )

        loop.call_soon_threadsafe(apply)
        return True

    def claim_rewards(self) -> Future | None:
        return self._submit_monitor_claim("claim_rewards")

    def claim_reward_task_ids(self, task_ids: list[str]) -> Future | None:
        return self._submit_monitor_claim("claim_reward_task_ids", list(task_ids))

    def _submit_monitor_claim(self, method: str, *args) -> Future | None:
        loop = self._loop
        monitor = self._task_monitor
        if loop is None or monitor is None or not loop.is_running():
            return None
        result = Future()

        def submit() -> None:
            if result.cancelled():
                return
            # Reserve the generation in queue order, before the coroutine gets
            # its first turn. A later queued task update must invalidate it.
            pending = asyncio.run_coroutine_threadsafe(
                getattr(monitor, method)(
                    *args, expected_generation=monitor.task_generation
                ),
                loop,
            )

            def complete(future) -> None:
                if result.cancelled():
                    return
                try:
                    error = future.exception()
                except FutureCancelledError:
                    result.cancel()
                    return
                try:
                    if error is not None:
                        result.set_exception(error)
                    else:
                        result.set_result(future.result())
                except InvalidStateError:
                    # Cancellation can race completion from the GUI thread.
                    if not result.cancelled():
                        raise

            def cancel_pending(future) -> None:
                if future.cancelled():
                    pending.cancel()

            pending.add_done_callback(complete)
            result.add_done_callback(cancel_pending)

        loop.call_soon_threadsafe(submit)
        return result

    def update_cookie(self, new_cookie: str) -> None:
        if self._running:
            raise RuntimeError("运行中不能切换账号，请先停止")
        self.config.cookie = new_cookie

    def update_notifier(self, notify_urls: list[str]) -> None:
        if self._running:
            raise RuntimeError("运行中不能修改通知地址，请先停止")
        self.config.notify_urls = list(notify_urls)
        self._notifier.update_urls(notify_urls)

    def _on_heartbeat(self, _room_id: int) -> None:
        self._set_health(last_heartbeat_at=time(), last_error="")

    def _on_reconnect(self, _room_id: int, detail: str) -> None:
        self._set_health(
            reconnect_count=self._health.reconnect_count + 1,
            last_error=detail,
        )

    def _handle_task_snapshot(self, snapshot: TaskSnapshot) -> None:
        if self._on_task_snapshot is not None:
            try:
                self._on_task_snapshot(snapshot)
            except Exception:
                LOGGER.exception("任务快照回调失败")
        controller = self._adaptive_controller
        if controller is None:
            return
        previous = self._health.target_sessions
        sessions_per_room = controller.observe(
            snapshot,
            observed_at=monotonic(),
        )
        desired_total = sessions_per_room * len(self.config.room_ids)
        if desired_total != previous:
            LOGGER.info(
                "自动并发调整: 每房间 %s 个连接（总计 %s）; %s",
                sessions_per_room,
                desired_total,
                controller.status_detail,
            )
            self._resize_session_tasks(sessions_per_room)
        self._set_health(
            concurrency_mode="automatic",
            concurrency_phase=controller.phase,
            concurrency_detail=controller.status_detail,
        )

    def _resize_session_tasks(self, sessions_per_room: int) -> None:
        if self._async_stop_event is None or self._async_stop_event.is_set():
            return
        plans = set(self._build_session_plans(sessions_per_room))
        for plan in tuple(self._session_tasks):
            if plan in plans:
                continue
            task = self._session_tasks.pop(plan)
            task.cancel()
        for plan in sorted(
            plans - self._session_tasks.keys(),
            key=lambda item: (item.room_id, item.session_no),
        ):
            self._session_tasks[plan] = asyncio.create_task(
                self._session_loop(plan, plan.session_no),
                name=f"room-{plan.room_id}-s{plan.session_no}",
            )
        self._set_health(target_sessions=len(plans))

    def _set_health(self, **changes) -> None:
        self._health = replace(self._health, **changes)
        if self._on_health is None:
            return
        try:
            self._on_health(self._health)
        except Exception:
            LOGGER.exception("运行状态回调失败")
