from __future__ import annotations

import threading
import time
from dataclasses import dataclass


TASK_API_GROUP = "task-api"


@dataclass(frozen=True, slots=True)
class RequestPermit:
    operation: str
    group: str
    sequence: int


class AccountRequestCoordinator:
    """Coordinate account-owned requests across GUI and runtime threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_groups: dict[str, RequestPermit] = {}
        self._cooldown_until: dict[str, float] = {}
        self._sequence = 0

    def try_begin(
        self,
        operation: str,
        *,
        group: str | None = None,
        now: float | None = None,
    ) -> RequestPermit | None:
        normalized_group = group or operation
        current = time.monotonic() if now is None else now
        with self._lock:
            if current < self._cooldown_until.get(normalized_group, 0.0):
                return None
            if normalized_group in self._active_groups:
                return None
            self._sequence += 1
            permit = RequestPermit(
                operation=operation,
                group=normalized_group,
                sequence=self._sequence,
            )
            self._active_groups[normalized_group] = permit
            return permit

    def finish(
        self,
        permit: RequestPermit,
        *,
        cooldown_seconds: float = 0.0,
        now: float | None = None,
    ) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            active = self._active_groups.get(permit.group)
            if active != permit:
                return
            self._active_groups.pop(permit.group, None)
            if cooldown_seconds > 0:
                self._cooldown_until[permit.group] = max(
                    self._cooldown_until.get(permit.group, 0.0),
                    current + cooldown_seconds,
                )

    def cooldown_remaining(
        self,
        group: str,
        *,
        now: float | None = None,
    ) -> float:
        current = time.monotonic() if now is None else now
        with self._lock:
            return max(0.0, self._cooldown_until.get(group, 0.0) - current)

    def acquire(
        self,
        operation: str,
        *,
        group: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> RequestPermit | None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            permit = self.try_begin(operation, group=group)
            if permit is not None:
                return permit
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(0.25, remaining))

    def is_active(self, group: str) -> bool:
        with self._lock:
            return group in self._active_groups


def looks_rate_limited(error: BaseException | str) -> bool:
    detail = str(error).casefold()
    return any(
        marker in detail
        for marker in ("限频", "频繁", "rate limit", "too many requests")
    )
