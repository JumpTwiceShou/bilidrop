from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from bilibili_drops_miner.client import BilibiliClient, TaskProgress
from bilibili_drops_miner.automatic_mining import all_task_rewards_claimed
from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.domain import TaskSnapshot
from bilibili_drops_miner.notifier import MultiPlatformNotifier
from bilibili_drops_miner.request_coordinator import (
    TASK_API_GROUP,
    AccountRequestCoordinator,
    RequestPermit,
    looks_rate_limited,
)

LOGGER = logging.getLogger(__name__)

TaskSnapshotCallback = Callable[[TaskSnapshot], None]
RewardsSettledCallback = Callable[[tuple[str, ...]], None]


@dataclass(frozen=True, slots=True)
class _CompletionUnit:
    marker_id: str
    claim_task_id: str
    task: TaskProgress
    progress: object


@dataclass(frozen=True, slots=True)
class _ClaimAttempt:
    unit: _CompletionUnit
    result: object | None


def _completed_units(progresses: list[TaskProgress]) -> list[_CompletionUnit]:
    units: list[_CompletionUnit] = []
    for task in progresses:
        checkpoints = list(task.check_points or [])
        if checkpoints:
            for index, point in enumerate(checkpoints, start=1):
                if not point.is_completed:
                    continue
                point_id = point.sid.strip() or str(index)
                units.append(
                    _CompletionUnit(
                        marker_id=f"{task.task_id}:checkpoint:{point_id}",
                        claim_task_id=point.sid.strip() or task.task_id,
                        task=task,
                        progress=point,
                    )
                )
            continue
        if task.is_completed:
            units.append(
                _CompletionUnit(
                    marker_id=f"{task.task_id}:task",
                    claim_task_id=task.task_id,
                    task=task,
                    progress=task,
                )
            )
    return units


class AccountTaskMonitor:
    """Own task polling and completion notifications once per account."""

    _CLAIM_RETRY_DELAYS = (60.0, 300.0, 900.0, 3600.0)

    def __init__(
        self,
        *,
        client: BilibiliClient,
        notifier: MultiPlatformNotifier,
        config: MinerConfig,
        account_label: str = "",
        on_snapshot: TaskSnapshotCallback | None = None,
        on_rewards_settled: RewardsSettledCallback | None = None,
        request_coordinator: AccountRequestCoordinator | None = None,
    ) -> None:
        self.client = client
        self.notifier = notifier
        self.config = config
        self.account_label = account_label.strip() or "未识别账号"
        self.on_snapshot = on_snapshot
        self.on_rewards_settled = on_rewards_settled
        self._request_coordinator = (
            request_coordinator or AccountRequestCoordinator()
        )
        self._stop_event = asyncio.Event()
        self._refresh_event = asyncio.Event()
        self._claim_lock = asyncio.Lock()
        self._notified_completed_ids: set[str] = set()
        self._notified_claimed_ids: set[str] = set()
        self._auto_claimed_completion_ids: set[str] = set()
        self._claim_failure_counts: dict[str, int] = {}
        self._claim_retry_after: dict[str, float] = {}
        self._latest_progresses: list[TaskProgress] = []
        self._rewards_settled_notified = False

    def request_refresh(self) -> None:
        self._refresh_event.set()

    async def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()

    async def run(self) -> None:
        while not self._stop_event.is_set():
            task_ids = tuple(self.config.task_ids)
            if not task_ids:
                self._emit(TaskSnapshot())
                await self._wait_for_next(max(10, self.config.task_query_interval_seconds))
                continue

            try:
                permit = await self._acquire_task_api("task-monitor-refresh")
                if permit is None:
                    await self._wait_for_next(2)
                    continue
                query_error: BaseException | None = None
                try:
                    progresses = await self.client.get_task_progress(
                        list(task_ids)
                    )
                except BaseException as exc:
                    query_error = exc
                    raise
                finally:
                    self._finish_task_api(permit, query_error)
                self._latest_progresses = list(progresses)
                self._apply_known_claimed_statuses(progresses)
                snapshot = TaskSnapshot(progresses=tuple(progresses))
                self._emit(snapshot)
                claim_results = await self._auto_claim_new_completions(progresses)
                if any(
                    self._claim_succeeded(attempt.result)
                    for attempt in claim_results
                ):
                    self._emit(TaskSnapshot(progresses=tuple(progresses)))
                try:
                    await self._notify_new_completions(
                        progresses,
                        claim_results,
                    )
                finally:
                    self._notify_rewards_settled(progresses)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                detail = str(exc).strip() or type(exc).__name__
                LOGGER.warning("账号任务刷新失败: %s", detail)
                self._emit(TaskSnapshot(error=detail))

            interval = max(10, self.config.task_query_interval_seconds)
            await self._wait_for_next(max(10, int(interval * random.uniform(0.9, 1.1))))

    async def claim_rewards(self):
        async with self._claim_lock:
            permit = await self._acquire_task_api("reward-claim")
            if permit is None:
                return []
            claim_error: BaseException | None = None
            task_ids = tuple(self.config.task_ids)
            try:
                if not task_ids:
                    return []
                if not self._latest_progresses:
                    self._latest_progresses = list(
                        await self.client.get_task_progress(list(task_ids))
                    )
                    self._apply_known_claimed_statuses(
                        self._latest_progresses
                    )
                units = [
                    unit
                    for unit in _completed_units(self._latest_progresses)
                    if self._is_claimable(unit.progress)
                ]
                claim_ids = [unit.claim_task_id for unit in units]
                if not claim_ids:
                    return []
                results = await self.client.receive_all_mission_rewards(
                    claim_ids
                )
                for unit, result in zip(units, results):
                    if self._claim_succeeded(result):
                        self._auto_claimed_completion_ids.add(unit.marker_id)
                        self._clear_claim_failure(unit.marker_id)
                        unit.progress.status = 3
                    else:
                        self._record_claim_failure(unit.marker_id)
                if units:
                    self._emit(
                        TaskSnapshot(progresses=tuple(self._latest_progresses))
                    )
                    self._notify_rewards_settled(self._latest_progresses)
                return results
            except BaseException as exc:
                claim_error = exc
                raise
            finally:
                self._finish_task_api(permit, claim_error)

    async def claim_reward_task_ids(self, task_ids: list[str]):
        normalized = list(dict.fromkeys(task_id for task_id in task_ids if task_id))
        if not normalized:
            return []
        async with self._claim_lock:
            permit = await self._acquire_task_api("reward-claim-task-ids")
            if permit is None:
                return []
            claim_error: BaseException | None = None
            try:
                return await self.client.receive_all_mission_rewards(normalized)
            except BaseException as exc:
                claim_error = exc
                raise
            finally:
                self._finish_task_api(permit, claim_error)

    async def _auto_claim_new_completions(
        self, progresses: list[TaskProgress]
    ) -> list[_ClaimAttempt]:
        completed_units = _completed_units(progresses)
        self._auto_claimed_completion_ids.update(
            unit.marker_id
            for unit in completed_units
            if self._is_claimed(unit.progress)
        )
        now = time.monotonic()
        pending_units = [
            unit
            for unit in completed_units
            if self._is_claimable(unit.progress)
            if unit.marker_id not in self._auto_claimed_completion_ids
            if now >= self._claim_retry_after.get(unit.marker_id, 0.0)
        ]
        if not pending_units:
            return []
        task_ids = [unit.claim_task_id for unit in pending_units]
        try:
            async with self._claim_lock:
                permit = await self._acquire_task_api("auto-reward-claim")
                if permit is None:
                    return []
                claim_error: BaseException | None = None
                try:
                    results = await self.client.receive_all_mission_rewards(
                        task_ids
                    )
                except BaseException as exc:
                    claim_error = exc
                    raise
                finally:
                    self._finish_task_api(permit, claim_error)
            attempts = [
                _ClaimAttempt(
                    unit=unit,
                    result=results[index] if index < len(results) else None,
                )
                for index, unit in enumerate(pending_units)
            ]
            claimed_count = 0
            for attempt in attempts:
                if not self._claim_succeeded(attempt.result):
                    self._record_claim_failure(attempt.unit.marker_id)
                    continue
                self._auto_claimed_completion_ids.add(attempt.unit.marker_id)
                self._clear_claim_failure(attempt.unit.marker_id)
                attempt.unit.progress.status = 3
                claimed_count += 1
            LOGGER.info(
                "奖励节点自动领取完成: 成功或已领取 %s/%s（%s 个外层任务）",
                claimed_count,
                len(pending_units),
                len({unit.task.task_id for unit in pending_units}),
            )
            return attempts
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            for unit in pending_units:
                self._record_claim_failure(unit.marker_id)
            LOGGER.warning("自动领取奖励失败，已进入冷却: %s", detail)
            return []

    async def _wait_for_next(self, timeout: int) -> None:
        if self._stop_event.is_set():
            return
        if self._refresh_event.is_set():
            self._refresh_event.clear()
            return
        stop_wait = asyncio.create_task(self._stop_event.wait())
        refresh_wait = asyncio.create_task(self._refresh_event.wait())
        try:
            completed, _pending = await asyncio.wait(
                (stop_wait, refresh_wait),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if refresh_wait in completed:
                self._refresh_event.clear()
        finally:
            for task in (stop_wait, refresh_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(stop_wait, refresh_wait, return_exceptions=True)

    def _apply_known_claimed_statuses(
        self,
        progresses: list[TaskProgress],
    ) -> None:
        for unit in _completed_units(progresses):
            if self._is_claimed(unit.progress):
                self._auto_claimed_completion_ids.add(unit.marker_id)
                self._clear_claim_failure(unit.marker_id)
            if unit.marker_id in self._auto_claimed_completion_ids:
                unit.progress.status = 3

    async def _notify_new_completions(
        self,
        progresses: list[TaskProgress],
        claim_attempts: list[_ClaimAttempt],
    ) -> None:
        if not self.config.notify_on_task_complete or not self.notifier.enabled:
            return
        results_by_marker = {
            attempt.unit.marker_id: attempt.result
            for attempt in claim_attempts
        }
        for unit in _completed_units(progresses):
            result = results_by_marker.get(unit.marker_id)
            if unit.marker_id not in self._notified_completed_ids:
                self._notified_completed_ids.add(unit.marker_id)
                already_claimed = (
                    self._is_claimed(unit.progress)
                    and result is None
                )
                if self._claim_succeeded(result) or already_claimed:
                    self._notified_claimed_ids.add(unit.marker_id)
                title = "Bilibili 掉宝任务已完成"
                body = self._build_notification_body(
                    unit.task,
                    unit.progress,
                    result,
                    already_claimed=already_claimed,
                )
            elif (
                self._claim_succeeded(result)
                and unit.marker_id not in self._notified_claimed_ids
            ):
                self._notified_claimed_ids.add(unit.marker_id)
                title = "Bilibili 掉宝奖励已领取"
                body = self._build_notification_body(
                    unit.task,
                    unit.progress,
                    result,
                    claim_retry_succeeded=True,
                )
            else:
                continue
            await asyncio.to_thread(self.notifier.notify, title=title, body=body)

    def _build_notification_body(
        self,
        task: TaskProgress,
        progress,
        claim_result,
        *,
        claim_retry_succeeded: bool = False,
        already_claimed: bool = False,
    ) -> str:
        if claim_retry_succeeded:
            state = "任务已完成；奖励重试领取成功"
        elif already_claimed:
            state = "任务已完成；奖励此前已领取"
        elif self._claim_succeeded(claim_result):
            state = (
                "任务已完成；奖励此前已领取"
                if bool(getattr(claim_result, "skipped", False))
                else "任务已完成；奖励已自动领取"
            )
        elif claim_result is not None:
            state = "任务已完成；奖励领取失败，将自动重试"
        else:
            state = "任务已完成；奖励状态待确认，将自动重试"

        room_ids = "、".join(str(room_id) for room_id in self.config.room_ids)
        task_name = task.task_name.strip() or task.task_id
        progress_name = str(getattr(progress, "alias", "") or "").strip()
        progress_id = str(getattr(progress, "sid", "") or "").strip()
        if progress is not task and progress_name and progress_name != task_name:
            task_name = f"{task_name} · {progress_name}"
        task_identifier = task.task_id
        if progress is not task and progress_id:
            task_identifier = f"{task.task_id}/{progress_id}"
        lines = [
            f"账号：{self.account_label}",
            f"直播间：{room_ids or '未设置'}",
            f"任务：{task_name}（{task_identifier}）",
            f"状态：{state}",
            (
                f"进度：{getattr(progress, 'cur_value', 0)}/"
                f"{getattr(progress, 'limit_value', 0)}"
            ),
        ]
        reward_name = str(getattr(claim_result, "reward_name", "")).strip()
        if reward_name:
            lines.append(f"奖励：{reward_name}")
        return "\n".join(lines)

    @staticmethod
    def _claim_succeeded(result) -> bool:
        return result is not None and bool(getattr(result, "success", False))

    @staticmethod
    def _is_claimable(progress) -> bool:
        return bool(getattr(progress, "is_claimable", False))

    @staticmethod
    def _is_claimed(progress) -> bool:
        return bool(getattr(progress, "is_claimed", False))

    def _record_claim_failure(self, marker_id: str) -> None:
        failure_count = self._claim_failure_counts.get(marker_id, 0) + 1
        self._claim_failure_counts[marker_id] = failure_count
        delay_index = min(failure_count - 1, len(self._CLAIM_RETRY_DELAYS) - 1)
        delay = self._CLAIM_RETRY_DELAYS[delay_index]
        self._claim_retry_after[marker_id] = time.monotonic() + delay
        LOGGER.warning(
            "奖励节点领取失败，%s 秒后再自动重试: %s",
            int(delay),
            marker_id,
        )

    def _clear_claim_failure(self, marker_id: str) -> None:
        self._claim_failure_counts.pop(marker_id, None)
        self._claim_retry_after.pop(marker_id, None)

    async def _acquire_task_api(
        self,
        operation: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> RequestPermit | None:
        deadline = time.monotonic() + timeout_seconds
        while not self._stop_event.is_set():
            permit = self._request_coordinator.try_begin(
                operation,
                group=TASK_API_GROUP,
            )
            if permit is not None:
                return permit
            if time.monotonic() >= deadline:
                return None
            cooldown = self._request_coordinator.cooldown_remaining(
                TASK_API_GROUP
            )
            await asyncio.sleep(min(1.0, max(0.1, cooldown)))
        return None

    def _finish_task_api(
        self,
        permit: RequestPermit,
        error: BaseException | None,
    ) -> None:
        self._request_coordinator.finish(
            permit,
            cooldown_seconds=(
                30.0 if error is not None and looks_rate_limited(error) else 0.0
            ),
        )

    def _emit(self, snapshot: TaskSnapshot) -> None:
        if self.on_snapshot is None:
            return
        try:
            self.on_snapshot(snapshot)
        except Exception:
            LOGGER.exception("任务快照回调失败")

    def _notify_rewards_settled(
        self,
        progresses: list[TaskProgress],
    ) -> None:
        if self._rewards_settled_notified:
            return
        if not all_task_rewards_claimed(
            TaskSnapshot(progresses=tuple(progresses))
        ):
            return
        self._rewards_settled_notified = True
        if self.on_rewards_settled is None:
            return
        try:
            self.on_rewards_settled(
                tuple(task.task_id for task in progresses if task.task_id)
            )
        except Exception:
            LOGGER.exception("任务奖励全部完成回调失败")
