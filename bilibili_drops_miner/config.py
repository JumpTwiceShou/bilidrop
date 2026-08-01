from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


DEFAULT_SESSIONS_PER_ROOM = 16
MAX_SESSIONS_PER_ROOM = 128
MIN_RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_DELAY_SECONDS = 3600
MIN_TASK_QUERY_INTERVAL_SECONDS = 10
MAX_TASK_QUERY_INTERVAL_SECONDS = 3600
CONCURRENCY_MODES = {"fixed", "automatic"}


@dataclass(slots=True)
class MinerConfig:
    cookie: str
    room_ids: list[int]
    thread_count: int = DEFAULT_SESSIONS_PER_ROOM
    reconnect_delay_seconds: int = 8
    enable_web_heartbeat: bool = True
    task_ids: list[str] = field(default_factory=list)
    task_query_interval_seconds: int = 30
    notify_urls: list[str] = field(default_factory=list)
    notify_on_task_complete: bool = True
    concurrency_mode: str = "fixed"
    task_started_at: datetime | None = None
    automatic_start_in_steady_mode: bool = False

    def validate(self) -> None:
        if not self.cookie.strip():
            raise ValueError("cookie 不能为空")
        if not self.room_ids:
            raise ValueError("room_ids 不能为空")
        if any(room_id <= 0 for room_id in self.room_ids):
            raise ValueError("room_ids 中存在非法房间号")
        if not 1 <= self.thread_count <= MAX_SESSIONS_PER_ROOM:
            raise ValueError(
                f"thread_count 必须在 1 到 {MAX_SESSIONS_PER_ROOM} 之间"
            )
        if self.concurrency_mode not in CONCURRENCY_MODES:
            raise ValueError("concurrency_mode 必须是 fixed 或 automatic")
        if not MIN_RECONNECT_DELAY_SECONDS <= self.reconnect_delay_seconds <= MAX_RECONNECT_DELAY_SECONDS:
            raise ValueError(
                "reconnect_delay_seconds 必须在 "
                f"{MIN_RECONNECT_DELAY_SECONDS} 到 {MAX_RECONNECT_DELAY_SECONDS} 之间"
            )
        if not MIN_TASK_QUERY_INTERVAL_SECONDS <= self.task_query_interval_seconds <= MAX_TASK_QUERY_INTERVAL_SECONDS:
            raise ValueError(
                "task_query_interval_seconds 必须在 "
                f"{MIN_TASK_QUERY_INTERVAL_SECONDS} 到 {MAX_TASK_QUERY_INTERVAL_SECONDS} 之间"
            )
