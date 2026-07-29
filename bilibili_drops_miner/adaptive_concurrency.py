from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bilibili_drops_miner.domain import TaskSnapshot


@dataclass(frozen=True, slots=True)
class ProgressSample:
    observed_at: float
    value_minutes: float


class AdaptiveConcurrencyController:
    """Use 16 sessions while catching up, then lock the task to 2."""

    def __init__(
        self,
        *,
        task_started_at: datetime | None = None,
        catchup_sessions: int = 16,
        steady_sessions: int = 2,
        sample_window_seconds: float = 180.0,
        minimum_progress_delta: float = 16.0,
    ) -> None:
        self.catchup_sessions = max(steady_sessions, catchup_sessions)
        self.steady_sessions = max(1, steady_sessions)
        self.sample_window_seconds = max(30.0, sample_window_seconds)
        self.minimum_progress_delta = max(0.0, minimum_progress_delta)
        self._task_signature: tuple[str, ...] = ()
        self._settled = False
        self._auto_new_task_candidate = task_started_at is not None
        self._target = self._initial_target(task_started_at)
        self._evaluation_anchor: ProgressSample | None = None
        self._missing_progress_since: float | None = None
        self._status_detail = (
            "后台检测到任务刚开始，等待首个进度；"
            f"初始为 0 时保持每房间 {self.steady_sessions} 个会话"
            if self._target == self.steady_sessions
            else (
                f"追赶阶段使用每房间 {self.catchup_sessions} 个会话，"
                f"{int(self.sample_window_seconds // 60)} 分钟后检查进度增量"
            )
        )

    @property
    def target_sessions(self) -> int:
        return self._target

    @property
    def settled(self) -> bool:
        return self._settled

    @property
    def phase(self) -> str:
        return "steady" if self._target == self.steady_sessions else "catchup"

    @property
    def status_detail(self) -> str:
        return self._status_detail

    def observe(
        self,
        snapshot: TaskSnapshot,
        *,
        observed_at: float,
    ) -> int:
        signature = tuple(
            sorted(
                str(task.task_id)
                for task in snapshot.progresses
                if str(task.task_id)
            )
        )
        if signature and signature != self._task_signature:
            is_new_task_set = bool(self._task_signature)
            self._task_signature = signature
            self._settled = False
            self._evaluation_anchor = None
            self._missing_progress_since = None
            if is_new_task_set:
                self._target = self.catchup_sessions
                self._auto_new_task_candidate = True
                self._status_detail = (
                    "检测到下一组新任务，正在读取初始观看进度"
                )

        if self._settled:
            return self._target
        value = self._watch_progress_minutes(snapshot)
        if value is None:
            if self._missing_progress_since is None:
                self._missing_progress_since = observed_at
            missing_seconds = observed_at - self._missing_progress_since
            if (
                not self._settled
                and missing_seconds >= self.sample_window_seconds
            ):
                self._settle(
                    "连续 3 分钟未取得可比较的观看进度，已降至"
                    f"每房间 {self.steady_sessions} 个会话；"
                    "本任务期间不再升高"
                )
            else:
                self._status_detail = (
                    "暂时没有可比较的观看进度；检测中 "
                    f"({int(missing_seconds)}/{int(self.sample_window_seconds)} 秒)"
                )
            return self._target
        self._missing_progress_since = None
        sample = ProgressSample(observed_at, value)
        anchor = self._evaluation_anchor
        if anchor is None:
            self._evaluation_anchor = sample
            if self._auto_new_task_candidate and value <= 0:
                self._settle(
                    "新任务初始进度为 0，直接使用"
                    f"每房间 {self.steady_sessions} 个会话"
                )
                return self._target
            self._auto_new_task_candidate = False
            self._target = self.catchup_sessions
            self._status_detail = (
                f"首轮基准 {value:g}；使用每房间 {self.catchup_sessions} 个会话，"
                f"{int(self.sample_window_seconds // 60)} 分钟后检查是否增加 "
                f"{self.minimum_progress_delta:g}"
            )
            return self._target
        if value < anchor.value_minutes:
            self._evaluation_anchor = sample
            self._target = self.catchup_sessions
            self._status_detail = (
                "任务进度发生回退，已用当前值重新开始 3 分钟检测"
            )
            return self._target

        elapsed_seconds = observed_at - anchor.observed_at
        if elapsed_seconds < self.sample_window_seconds:
            self._status_detail = (
                f"自动追赶：基准 {anchor.value_minutes:g}，当前 {value:g}；"
                "检测中 "
                f"({int(elapsed_seconds)}/{int(self.sample_window_seconds)} 秒)"
            )
            return self._target
        progress_delta = value - anchor.value_minutes
        if progress_delta >= self.minimum_progress_delta:
            self._evaluation_anchor = sample
            self._status_detail = (
                f"本轮进度增加 {progress_delta:g}，达到 "
                f"{self.minimum_progress_delta:g}；继续每房间 "
                f"{self.catchup_sessions} 个会话并开始下一轮 3 分钟检测"
            )
            return self._target

        self._settle(
            f"3 分钟进度只增加 {progress_delta:g}（不足 "
            f"{self.minimum_progress_delta:g}），已降至每房间 "
            f"{self.steady_sessions} 个会话；本任务期间不再升高"
        )
        return self._target

    def _settle(self, detail: str) -> None:
        self._settled = True
        self._target = self.steady_sessions
        self._status_detail = detail

    def _initial_target(self, task_started_at: datetime | None) -> int:
        return (
            self.steady_sessions
            if task_started_at is not None
            else self.catchup_sessions
        )

    @staticmethod
    def _watch_progress_minutes(snapshot: TaskSnapshot) -> float | None:
        candidates: list[float] = []
        for task in snapshot.progresses:
            checkpoints = list(task.check_points or [])
            items = checkpoints or [task]
            for item in items:
                try:
                    limit = float(item.limit_value)
                    current = float(item.cur_value)
                except (TypeError, ValueError):
                    continue
                # Drop tasks use minute-scale checkpoints. Excluding tiny
                # counters avoids mistaking share/comment tasks for watch time.
                if limit >= 30:
                    candidates.append(current)
        return max(candidates) if candidates else None
