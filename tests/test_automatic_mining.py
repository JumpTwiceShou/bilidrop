from datetime import datetime
from zoneinfo import ZoneInfo

from bilibili_drops_miner.automatic_mining import (
    all_tasks_completed,
    claimable_reward_task_ids,
    select_scheduled_task_group,
)
from bilibili_drops_miner.client_parts.models import (
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.domain import (
    DiscoveredTaskGroup,
    TaskSnapshot,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _group(
    label: str,
    start: tuple[int, int, int, int, int],
    end: tuple[int, int, int, int, int],
) -> DiscoveredTaskGroup:
    return DiscoveredTaskGroup(
        label,
        (label,),
        start_at=datetime(*start, tzinfo=SHANGHAI),
        end_at=datetime(*end, tzinfo=SHANGHAI),
    )


def test_current_day_wins_over_future_groups() -> None:
    day1 = _group(
        "day1",
        (2026, 7, 29, 17, 30),
        (2026, 7, 30, 17, 0),
    )
    day2 = _group(
        "day2",
        (2026, 7, 30, 17, 30),
        (2026, 7, 31, 17, 0),
    )

    selected = select_scheduled_task_group(
        (day1, day2),
        now=datetime(2026, 7, 29, 21, 0, tzinfo=SHANGHAI),
    )

    assert selected.group == day1
    assert selected.phase == "current"
    assert selected.next_check_seconds == 15 * 60


def test_future_group_polls_hourly_but_wakes_at_start() -> None:
    future = _group(
        "day2",
        (2026, 7, 30, 17, 30),
        (2026, 7, 31, 17, 0),
    )
    far = select_scheduled_task_group(
        (future,),
        now=datetime(2026, 7, 30, 12, 0, tzinfo=SHANGHAI),
    )
    near = select_scheduled_task_group(
        (future,),
        now=datetime(2026, 7, 30, 17, 25, tzinfo=SHANGHAI),
    )

    assert far.next_check_seconds == 60 * 60
    assert near.next_check_seconds == 5 * 60


def test_all_reward_nodes_must_be_complete_before_stopping_heartbeats() -> None:
    task = TaskProgress(
        "daily",
        "观看直播",
        1,
        181,
        300,
        check_points=[
            TaskCheckpointProgress("60", "60分钟", 3, 181, 60),
            TaskCheckpointProgress("120", "120分钟", 3, 181, 120),
            TaskCheckpointProgress("180", "180分钟", 2, 181, 180),
            TaskCheckpointProgress("240", "240分钟", 1, 181, 240),
        ],
    )
    assert not all_tasks_completed(TaskSnapshot(progresses=(task,)))

    task.cur_value = 240
    task.check_points[-1].cur_value = 240
    task.check_points[-1].status = 2
    assert all_tasks_completed(TaskSnapshot(progresses=(task,)))
    assert claimable_reward_task_ids(TaskSnapshot(progresses=(task,))) == [
        "180",
        "240",
    ]
