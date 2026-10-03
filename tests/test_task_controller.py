import threading
import time
from concurrent.futures import Future

import pytest

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


@pytest.mark.parametrize("failure_source", ["query", "runtime"])
def test_manual_claim_failure_reaches_ui_and_allows_retry(monkeypatch, failure_source):
    controller = _controller(monkeypatch, [], threading.Event())
    messages = []
    uncaught = []
    done = threading.Event()
    controller._set_task_progress_text = lambda message: (
        messages.append(message),
        done.set(),
    )
    monkeypatch.setattr(
        threading,
        "excepthook",
        lambda args: (uncaught.append(args.exc_value), done.set()),
    )

    if failure_source == "runtime":
        future = Future()
        future.set_exception(TimeoutError("领取请求超时"))
        controller._runtime_is_running = lambda: True
        controller._claim_runtime_rewards = lambda: future
    else:

        async def fail_query(self, task_ids):
            raise RuntimeError("任务查询失败")

        monkeypatch.setattr(_FakeClient, "get_task_progress", fail_query)

    controller.claim_rewards()
    assert done.wait(3)
    assert not uncaught
    assert len(messages) == 1
    assert "领取奖励失败" in messages[0]
    assert not controller._reward_claim_inflight
    assert not controller._request_coordinator.is_active("task-api")
    done.clear()
    controller.claim_rewards()
    assert done.wait(3)
    assert len(messages) == 2


def test_idle_refresh_discards_snapshot_queued_before_task_change(monkeypatch):
    snapshots = []
    completed = threading.Event()
    controller = _controller(monkeypatch, snapshots, completed)
    queued = []
    controller._post_ui_task = lambda callback, *args, **kw: queued.append(
        (callback, args, kw)
    )
    controller.refresh(manual=False)
    _wait_for(lambda: not controller._task_refresh_inflight and queued)
    controller._get_task_ids = lambda: ["replacement"]
    for callback, args, kw in queued:
        callback(*args, **kw)
    assert snapshots == []
    assert controller._latest_task_progresses == []


def test_idle_claim_does_not_claim_tasks_replaced_during_query(monkeypatch):
    controller = _controller(monkeypatch, [], threading.Event())
    entered, release = threading.Event(), threading.Event()
    claims = []

    class Client(_FakeClient):
        async def get_task_progress(self, ids):
            entered.set()
            assert release.wait(3)
            return _progresses()

        async def receive_all_mission_rewards(self, ids):
            claims.append(ids)
            return []

    monkeypatch.setattr(task_controller_module, "BilibiliClient", Client)
    controller.claim_rewards()
    assert entered.wait(3)
    controller._get_task_ids = lambda: ["replacement"]
    release.set()
    _wait_for(lambda: not controller._reward_claim_inflight)
    assert claims == []


def test_ambiguous_checkpoint_result_is_not_assumed_claimed(monkeypatch):
    controller = _controller(monkeypatch, [], threading.Event())
    first = TaskCheckpointProgress("", "first", 2, 120, 60)
    second = TaskCheckpointProgress("", "second", 2, 120, 120)
    controller._latest_task_progresses = [
        TaskProgress("outer", "task", 2, 120, 120, check_points=[first, second])
    ]
    controller._record_claim_results(
        [MissionRewardClaimResult("outer", "task", "unknown", 6, "ok", True, False)]
    )
    assert [first.status, second.status] == [2, 2]


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
