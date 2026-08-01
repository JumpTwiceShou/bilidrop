import threading
import time

from bilibili_drops_miner.client_parts.models import (
    MissionRewardClaimResult,
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.gui_parts import task_controller as task_controller_module
from bilibili_drops_miner.gui_parts.task_controller import TaskController


def _progresses() -> list[TaskProgress]:
    return [
        TaskProgress(
            "daily",
            "观看直播",
            1,
            181,
            300,
            check_points=[
                TaskCheckpointProgress(
                    "60",
                    "观看60分钟",
                    3,
                    181,
                    60,
                    "奖励A",
                    1,
                ),
                TaskCheckpointProgress(
                    "120",
                    "观看120分钟",
                    3,
                    181,
                    120,
                    "奖励B",
                    1,
                ),
                TaskCheckpointProgress(
                    "180",
                    "观看180分钟",
                    2,
                    181,
                    180,
                    "奖励C",
                    1,
                ),
                TaskCheckpointProgress(
                    "240",
                    "观看240分钟",
                    1,
                    181,
                    240,
                    "奖励D",
                    1,
                ),
                TaskCheckpointProgress(
                    "300",
                    "观看300分钟",
                    1,
                    181,
                    300,
                    "奖励E",
                    1,
                ),
            ],
        )
    ]


class _FakeClient:
    def __init__(self, _cookie: str) -> None:
        pass

    async def get_task_progress(self, _task_ids):
        return _progresses()

    async def receive_all_mission_rewards(self, _task_ids):
        return [
            MissionRewardClaimResult(
                task_id="180",
                task_name="观看直播",
                reward_name="奖励C",
                status=6,
                message="已领取",
                success=True,
                skipped=True,
            )
        ]

    async def close(self) -> None:
        return None


class _ExplodingClaimClient(_FakeClient):
    async def get_task_progress(self, _task_ids):
        raise ValueError("原始领奖异常")


def _controller(monkeypatch, snapshots, completed) -> TaskController:
    monkeypatch.setattr(task_controller_module, "BilibiliClient", _FakeClient)
    return TaskController(
        get_cookie=lambda: "DedeUserID=1; bili_jct=fixture",
        get_room_ids=lambda: [23612045],
        get_task_ids=lambda: ["daily"],
        show_warning=lambda *_args: None,
        set_task_progress_text=lambda _text: None,
        set_task_snapshot=lambda snapshot: snapshots.append(snapshot),
        set_live_watch_time_text=lambda _text: None,
        complete_task_refresh=lambda _text, _rerun: completed.set(),
        post_ui_task=lambda callback, *args, **kwargs: callback(*args, **kwargs),
    )


def _wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for background task")
        time.sleep(0.01)


def test_idle_refresh_returns_structured_five_node_snapshot(monkeypatch) -> None:
    snapshots = []
    completed = threading.Event()
    controller = _controller(monkeypatch, snapshots, completed)

    controller.refresh(manual=False)

    assert completed.wait(3)
    assert len(snapshots) == 1
    assert len(snapshots[0].progresses[0].check_points) == 5


def test_manual_claim_is_remembered_after_followup_refresh(monkeypatch) -> None:
    snapshots = []
    completed = threading.Event()
    controller = _controller(monkeypatch, snapshots, completed)
    controller.refresh(manual=False)
    assert completed.wait(3)
    completed.clear()

    controller.claim_rewards()

    _wait_for(lambda: len(snapshots) >= 2)
    refreshed = snapshots[-1].progresses[0].check_points
    assert refreshed[0].status == 3
    assert refreshed[1].status == 3
    assert refreshed[2].status == 3


def test_claim_exception_keeps_original_error_without_secondary_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        task_controller_module,
        "BilibiliClient",
        _ExplodingClaimClient,
    )
    messages: list[str] = []
    controller = TaskController(
        get_cookie=lambda: "DedeUserID=1; bili_jct=fixture",
        get_room_ids=lambda: [23612045],
        get_task_ids=lambda: ["daily"],
        show_warning=lambda *_args: None,
        set_task_progress_text=lambda text: messages.append(text),
        set_task_snapshot=lambda _snapshot: None,
        set_live_watch_time_text=lambda _text: None,
        complete_task_refresh=lambda *_args: None,
        post_ui_task=lambda callback, *args, **kwargs: callback(*args, **kwargs),
    )

    controller.claim_rewards()

    _wait_for(lambda: bool(messages))
    assert "原始领奖异常" in messages[-1]
    assert "local variable" not in messages[-1]
