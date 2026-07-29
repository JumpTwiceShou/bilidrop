from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bilibili_drops_miner.domain import (
    DiscoveredTaskGroup,
    TaskSnapshot,
)


@dataclass(frozen=True, slots=True)
class ScheduledTaskSelection:
    group: DiscoveredTaskGroup | None
    phase: str
    next_check_seconds: int


@dataclass(frozen=True, slots=True)
class AutomaticAccountCheckResult:
    session_id: str
    selection: ScheduledTaskSelection
    snapshot: TaskSnapshot = field(default_factory=TaskSnapshot)
    live_status: int | None = None
    error: str = ""


def select_scheduled_task_group(
    groups: tuple[DiscoveredTaskGroup, ...],
    *,
    now: datetime,
) -> ScheduledTaskSelection:
    scheduled = [
        group
        for group in groups
        if group.start_at is not None and group.end_at is not None
    ]
    current = [
        group
        for group in scheduled
        if group.start_at <= now < group.end_at
    ]
    if current:
        return ScheduledTaskSelection(current[0], "current", 15 * 60)

    future = sorted(
        (group for group in scheduled if group.start_at > now),
        key=lambda group: group.start_at,
    )
    if future:
        seconds_to_start = max(
            1,
            int((future[0].start_at - now).total_seconds()),
        )
        return ScheduledTaskSelection(
            future[0],
            "future",
            min(60 * 60, seconds_to_start),
        )

    active = [group for group in groups if group.active]
    if len(active) == 1:
        return ScheduledTaskSelection(active[0], "current", 15 * 60)
    if len(groups) == 1:
        return ScheduledTaskSelection(groups[0], "current", 15 * 60)
    return ScheduledTaskSelection(None, "none", 15 * 60)


def all_tasks_completed(snapshot: TaskSnapshot) -> bool:
    if snapshot.error or not snapshot.progresses:
        return False
    for task in snapshot.progresses:
        checkpoints = list(task.check_points or [])
        if checkpoints:
            if not all(point.is_completed for point in checkpoints):
                return False
        elif not task.is_completed:
            return False
    return True


def claimable_reward_task_ids(snapshot: TaskSnapshot) -> list[str]:
    task_ids: list[str] = []
    for task in snapshot.progresses:
        checkpoints = list(task.check_points or [])
        if checkpoints:
            for point in checkpoints:
                if point.is_claimable and point.sid:
                    task_ids.append(point.sid)
        elif task.is_claimable and task.task_id:
            task_ids.append(task.task_id)
    return list(dict.fromkeys(task_ids))
