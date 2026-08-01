from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from bilibili_drops_miner.config import DEFAULT_SESSIONS_PER_ROOM


ACCOUNT_SETTINGS_VERSION = 1


@dataclass(slots=True)
class AccountSettings:
    rooms_text: str = ""
    thread_count: int = DEFAULT_SESSIONS_PER_ROOM
    reconnect_delay_seconds: int = 8
    task_query_interval_seconds: int = 30
    notify_on_task_complete: bool = True
    concurrency_mode: str = "automatic"

    @classmethod
    def from_mapping(
        cls,
        value: object,
    ) -> AccountSettings | None:
        if not isinstance(value, dict) or not any(
            key in value
            for key in (
                "rooms_text",
                "thread_count",
                "reconnect_delay_seconds",
                "task_query_interval_seconds",
                "notify_on_task_complete",
                "concurrency_mode",
            )
        ):
            return None
        try:
            return cls(
                rooms_text=str(value.get("rooms_text", "")).strip(),
                thread_count=max(
                    1,
                    min(128, int(value.get("thread_count", 16))),
                ),
                reconnect_delay_seconds=max(
                    5,
                    min(3600, int(value.get("reconnect_delay_seconds", 8))),
                ),
                task_query_interval_seconds=max(
                    10,
                    min(
                        3600,
                        int(value.get("task_query_interval_seconds", 30)),
                    ),
                ),
                notify_on_task_complete=bool(
                    value.get("notify_on_task_complete", True)
                ),
                concurrency_mode=(
                    "fixed"
                    if str(value.get("concurrency_mode", "automatic"))
                    == "fixed"
                    else "automatic"
                ),
            )
        except (TypeError, ValueError):
            return None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": ACCOUNT_SETTINGS_VERSION,
            **asdict(self),
        }
