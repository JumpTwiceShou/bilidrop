import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bilibili_drops_miner import miner as miner_module
from bilibili_drops_miner.automatic_mining import (
    all_tasks_completed,
    select_scheduled_task_group,
)
from bilibili_drops_miner.client import BilibiliClient
from bilibili_drops_miner.client_parts.models import (
    MissionRewardClaimResult,
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.domain import DiscoveredTaskGroup, TaskSnapshot
from bilibili_drops_miner.request_coordinator import (
    TASK_API_GROUP,
    AccountRequestCoordinator,
)
from bilibili_drops_miner.task_monitor import AccountTaskMonitor


def _progress(task_id, status=2):
    return TaskProgress(task_id, task_id, status, 60, 60)


def _reward(task_id, success=True):
    return MissionRewardClaimResult(task_id, task_id, "", 6, "", success, False)


def _monitor(client, on_snapshot=None):
    return AccountTaskMonitor(
        client=client,
        notifier=SimpleNamespace(enabled=False),
        config=MinerConfig("fixture", [1], task_ids=["a", "b"]),
        on_snapshot=on_snapshot,
    )


@pytest.mark.parametrize("returned_ids", [["a"], ["a", "foreign"], ["a", "a", "b"], []])
def test_client_rejects_progress_without_exact_requested_coverage(
    monkeypatch, returned_ids
):
    async def scenario():
        client = BilibiliClient("bili_jct=fixture")

        async def response(*args, **kwargs):
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"task_id": task_id, "cur_value": 60, "limit": 60}
                        for task_id in returned_ids
                    ]
                },
            }

        monkeypatch.setattr(client, "_signed_get_json", response)
        try:
            with pytest.raises(ValueError, match="任务进度.*不完整|任务.*不匹配"):
                await client.get_task_progress(["a", "b"])
        finally:
            await client.close()

    asyncio.run(scenario())


def test_client_accepts_complete_progress_in_response_order(monkeypatch):
    async def scenario():
        client = BilibiliClient("bili_jct=fixture")

        async def response(*args, **kwargs):
            assert args[1]["task_ids"] == "a,b"
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"task_id": "b", "cur_value": 0, "limit": 60},
                        {"task_id": "a", "cur_value": 60, "limit": 60},
                    ]
                },
            }

        monkeypatch.setattr(client, "_signed_get_json", response)
        try:
            progresses = await client.get_task_progress([" a ", "b", "a"])
            assert [task.task_id for task in progresses] == ["b", "a"]
            assert not all_tasks_completed(
                TaskSnapshot(progresses=tuple(progresses)),
                expected_task_ids=("a", "b"),
            )
        finally:
            await client.close()

    asyncio.run(scenario())


def test_completion_requires_all_expected_tasks():
    snapshot = TaskSnapshot(progresses=(_progress("a"),))
    assert not all_tasks_completed(snapshot, expected_task_ids=("a", "b"))
    assert not all_tasks_completed(snapshot, expected_task_ids=("foreign",))
    assert all_tasks_completed(snapshot, expected_task_ids=("a",))


def test_current_schedule_rechecks_before_its_end():
    now = datetime(2026, 10, 3, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    group = DiscoveredTaskGroup(
        "ending",
        ("a",),
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(seconds=20),
    )
    assert select_scheduled_task_group((group,), now=now).next_check_seconds <= 20


@pytest.mark.parametrize("manual", [False, True])
def test_claim_results_are_associated_by_id_not_response_position(manual):
    class Client:
        async def receive_all_mission_rewards(self, task_ids):
            assert task_ids == ["a", "b"]
            return [_reward("b"), _reward("a", success=False)]

    async def scenario():
        monitor = _monitor(Client())
        progresses = [_progress("a"), _progress("b")]
        monitor._latest_progresses = progresses
        if manual:
            await monitor.claim_rewards()
        else:
            await monitor._auto_claim_new_completions(progresses)
        assert [task.status for task in progresses] == [2, 3]

    asyncio.run(scenario())


def test_ambiguous_blank_checkpoint_ids_are_not_claimed_as_outer_task():
    calls = []

    class Client:
        async def receive_all_mission_rewards(self, task_ids):
            calls.append(task_ids)
            return [_reward(task_id) for task_id in dict.fromkeys(task_ids)]

    async def scenario():
        monitor = _monitor(Client())
        points = [
            TaskCheckpointProgress("", "first", 2, 100, 30),
            TaskCheckpointProgress("", "second", 2, 100, 60),
            TaskCheckpointProgress("separate", "third", 2, 100, 90),
        ]
        task = TaskProgress("outer", "outer", 1, 100, 300, check_points=points)
        await monitor._auto_claim_new_completions([task])
        assert calls == [["separate"]]
        assert [point.status for point in points] == [2, 2, 3]

    asyncio.run(scenario())


@pytest.mark.parametrize("through_miner", [False, True])
def test_task_switch_discards_inflight_snapshot_and_claims(through_miner):
    async def scenario():
        started, release, refreshed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls, snapshots = [], []

        class Client:
            async def get_task_progress(self, task_ids):
                if task_ids == ["a", "b"]:
                    started.set()
                    await release.wait()
                    return [_progress("a"), _progress("b")]
                assert task_ids == ["new"]
                refreshed.set()
                return [TaskProgress("new", "new", 1, 0, 60)]

            async def receive_all_mission_rewards(self, task_ids):
                calls.append(task_ids)
                return [_reward(task_id) for task_id in task_ids]

        monitor = _monitor(Client(), snapshots.append)
        task = asyncio.create_task(monitor.run())
        try:
            await asyncio.wait_for(started.wait(), 1)
            if through_miner:
                miner = miner_module.BilibiliWatchTimeMiner(monitor.config)
                miner._loop = asyncio.get_running_loop()
                miner._task_monitor = monitor
                assert miner.update_task_ids(["new"])
                await asyncio.sleep(0)
            else:
                monitor.update_task_ids(["new"])
            release.set()
            await asyncio.wait_for(refreshed.wait(), 1)
            await monitor.stop()
            await asyncio.wait_for(task, 1)
            assert calls == []
            assert [[p.task_id for p in s.progresses] for s in snapshots] == [["new"]]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_task_switch_clears_manual_claim_cache():
    calls = []

    class Client:
        async def get_task_progress(self, task_ids):
            assert task_ids == ["new"]
            return [_progress("new")]

        async def receive_all_mission_rewards(self, task_ids):
            calls.append(task_ids)
            return [_reward(task_id) for task_id in task_ids]

    async def scenario():
        monitor = _monitor(Client())
        monitor._latest_progresses = [_progress("a")]
        monitor.update_task_ids(["new"])
        await monitor.claim_rewards()
        assert calls == [["new"]]

    asyncio.run(scenario())


def test_task_switch_cancels_old_claim_batch_without_marking_or_emitting():
    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        snapshots = []

        class Client:
            async def receive_all_mission_rewards(self, task_ids):
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        monitor = _monitor(Client(), snapshots.append)
        old = [_progress("a")]
        task = asyncio.create_task(monitor._auto_claim_new_completions(old))
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert monitor._request_coordinator.is_active(TASK_API_GROUP)
            monitor.update_task_ids(["new"])
            assert await asyncio.wait_for(task, 1) == []
            assert cancelled.is_set()
            assert old[0].status == 2
            assert snapshots == []
            assert not monitor._auto_claimed_completion_ids
            assert not monitor._request_coordinator.is_active(TASK_API_GROUP)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_task_switch_invalidates_claim_waiting_for_lock():
    calls = []

    class Client:
        async def receive_all_mission_rewards(self, task_ids):
            calls.append(task_ids)
            return [_reward(task_id) for task_id in task_ids]

    async def scenario():
        monitor = _monitor(Client())
        async with monitor._claim_lock:
            task = asyncio.create_task(monitor.claim_reward_task_ids(["old-node"]))
            await asyncio.sleep(0)
            monitor.update_task_ids(["new"])
        assert await asyncio.wait_for(task, 1) == []
        assert calls == []

    asyncio.run(scenario())


def test_task_reordering_does_not_cancel_the_same_pending_reward():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class Client:
            async def receive_all_mission_rewards(self, task_ids):
                started.set()
                await release.wait()
                return [_reward("a")]

        monitor = _monitor(Client())
        progress = _progress("a")
        task = asyncio.create_task(monitor._auto_claim_new_completions([progress]))
        try:
            await asyncio.wait_for(started.wait(), 1)
            monitor.update_task_ids(["b", "a"])
            release.set()
            await asyncio.wait_for(task, 1)
            assert progress.status == 3
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_manual_claim_discards_query_error_after_task_switch():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class Client:
            async def get_task_progress(self, task_ids):
                started.set()
                await release.wait()
                raise ValueError("old task is no longer available")

        monitor = _monitor(Client())
        task = asyncio.create_task(monitor.claim_rewards())
        try:
            await asyncio.wait_for(started.wait(), 1)
            monitor.update_task_ids(["new"])
            release.set()
            assert await asyncio.wait_for(task, 1) == []
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_stop_before_async_setup_does_not_start_clients(monkeypatch):
    created = []

    class Client:
        def __init__(self, cookie):
            created.append(cookie)

        async def get_self_info(self):
            return 1, "fixture"

        async def close(self):
            pass

    async def scenario():
        monkeypatch.setattr(miner_module, "BilibiliClient", Client)
        miner = miner_module.BilibiliWatchTimeMiner(MinerConfig("fixture", [1]))
        miner.stop()
        task = asyncio.create_task(miner._run_async())
        try:
            await asyncio.wait_for(task, 0.1)
            assert created == []
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_public_run_preserves_pending_stop_and_cleans_up(monkeypatch):
    miner = miner_module.BilibiliWatchTimeMiner(MinerConfig("fixture", [1]))

    async def unexpected_probe():
        raise AssertionError("a stopped start must not probe the network")

    monkeypatch.setattr(miner, "_probe_login", unexpected_probe)
    miner.stop()
    miner.run()
    assert not miner.is_running
    assert miner.health.state.value == "idle"
    assert not miner._thread_stop_event.is_set()


def test_cancelling_claim_caller_still_propagates_cancellation():
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()

        class Client:
            async def receive_all_mission_rewards(self, task_ids):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        monitor = _monitor(Client())
        task = asyncio.create_task(monitor.claim_reward_task_ids(["a"]))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert cancelled.is_set()
        assert monitor._claim_request_task is None
        assert not monitor._request_coordinator.is_active(TASK_API_GROUP)

    asyncio.run(scenario())


@pytest.mark.parametrize("update_first", [False, True])
def test_miner_claim_submission_preserves_task_selection_order(update_first):
    calls = []

    class Client:
        async def receive_all_mission_rewards(self, task_ids):
            calls.append(task_ids)
            return [_reward(task_id) for task_id in task_ids]

    async def scenario():
        monitor = _monitor(Client())
        miner = miner_module.BilibiliWatchTimeMiner(monitor.config)
        miner._loop = asyncio.get_running_loop()
        miner._task_monitor = monitor
        if update_first:
            miner.update_task_ids(["new"])
        pending = miner.claim_reward_task_ids(
            ["new-node" if update_first else "old-node"]
        )
        if not update_first:
            miner.update_task_ids(["new"])
        results = await asyncio.wait_for(asyncio.wrap_future(pending), 1)
        assert calls == ([["new-node"]] if update_first else [])
        assert len(results) == (1 if update_first else 0)

    asyncio.run(scenario())


@pytest.mark.parametrize("wrapped", [False, True])
def test_cancelling_submitted_miner_claim_cancels_reward_batch(wrapped):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()

        class Client:
            async def receive_all_mission_rewards(self, task_ids):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        monitor = _monitor(Client())
        miner = miner_module.BilibiliWatchTimeMiner(monitor.config)
        miner._loop = asyncio.get_running_loop()
        miner._task_monitor = monitor
        pending = miner.claim_reward_task_ids(["a"])
        cancellable = asyncio.wrap_future(pending) if wrapped else pending
        await asyncio.wait_for(started.wait(), 1)
        assert cancellable.cancel()
        await asyncio.wait_for(cancelled.wait(), 1)
        await asyncio.sleep(0)
        assert monitor._claim_request_task is None
        assert not monitor._request_coordinator.is_active(TASK_API_GROUP)

    asyncio.run(scenario())


@pytest.mark.parametrize("returned_ids", [["a"], ["a", "foreign"], ["a", "a", "b"]])
def test_rewards_settled_requires_complete_current_task_set(returned_ids):
    settled = []
    monitor = _monitor(SimpleNamespace())
    monitor.on_rewards_settled = settled.append
    monitor._notify_rewards_settled(
        [_progress(task_id, status=3) for task_id in returned_ids],
        generation=monitor.task_generation,
    )
    assert settled == []
    monitor._notify_rewards_settled(
        [_progress("b", status=3), _progress("a", status=3)],
        generation=monitor.task_generation,
    )
    assert settled == [("b", "a")]


@pytest.mark.parametrize("claim_path", ["manual", "explicit", "auto"])
def test_task_switch_releases_old_claim_waiting_for_request_permit(claim_path):
    async def scenario():
        coordinator = AccountRequestCoordinator()
        occupied = coordinator.try_begin("other-query", group=TASK_API_GROUP)
        calls = []

        class Client:
            async def receive_all_mission_rewards(self, task_ids):
                calls.append(task_ids)
                return [_reward(task_id) for task_id in task_ids]

        monitor = _monitor(Client())
        monitor._request_coordinator = coordinator
        progresses = [_progress("a"), _progress("b")]
        monitor._latest_progresses = progresses
        if claim_path == "manual":
            claim = monitor.claim_rewards()
        elif claim_path == "explicit":
            claim = monitor.claim_reward_task_ids(["old-node"])
        else:
            claim = monitor._auto_claim_new_completions(progresses)
        task = asyncio.create_task(claim)
        try:
            await asyncio.sleep(0)
            assert monitor._claim_lock.locked()
            monitor.update_task_ids(["new"])
            assert await asyncio.wait_for(task, 0.5) == []
            assert calls == []
            assert coordinator.is_active(TASK_API_GROUP)
            assert not monitor._claim_lock.locked()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            coordinator.finish(occupied)
        assert not coordinator.is_active(TASK_API_GROUP)

    asyncio.run(scenario())


def test_rewards_settled_notifies_once_per_current_task_generation():
    settled = []
    monitor = _monitor(SimpleNamespace())
    monitor.on_rewards_settled = settled.append
    old_generation = monitor.task_generation
    old_progresses = [_progress("a", status=3), _progress("b", status=3)]
    monitor._notify_rewards_settled(old_progresses, generation=old_generation)
    monitor.update_task_ids(["b", "a"])
    monitor._notify_rewards_settled(old_progresses, generation=old_generation)
    assert settled == [("a", "b")]
    monitor.update_task_ids(["new"])
    new_progresses = [_progress("new", status=3)]
    monitor._notify_rewards_settled(new_progresses, generation=old_generation)
    assert settled == [("a", "b")]
    monitor._notify_rewards_settled(
        new_progresses, generation=monitor.task_generation
    )
    assert settled == [("a", "b"), ("new",)]


@pytest.mark.parametrize("action", ["switch", "stop", "cancel"])
def test_obsolete_or_cancelled_completion_notification_cannot_settle_rewards(action):
    async def scenario():
        entered, release, refreshed = (
            asyncio.Event(), asyncio.Event(), asyncio.Event()
        )
        settled = []

        class Client:
            async def get_task_progress(self, task_ids):
                if task_ids == ["new"]:
                    refreshed.set()
                    return [TaskProgress("new", "new", 1, 0, 60)]
                return [_progress(task_id, status=3) for task_id in task_ids]

        monitor = _monitor(Client())
        monitor.on_rewards_settled = settled.append

        async def notify(progresses, claims):
            entered.set()
            await release.wait()

        monitor._notify_new_completions = notify
        task = asyncio.create_task(monitor.run())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            if action == "switch":
                monitor.update_task_ids(["new"])
            elif action == "stop":
                await monitor.stop()
            else:
                task.cancel()
            release.set()
            if action == "switch":
                await asyncio.wait_for(refreshed.wait(), 1)
                await monitor.stop()
            if action == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 1)
            else:
                await asyncio.wait_for(task, 1)
            assert settled == []
            assert not monitor._request_coordinator.is_active(TASK_API_GROUP)
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_cancelling_progress_request_releases_account_request_permit():
    async def scenario():
        started = asyncio.Event()

        class Client:
            async def get_task_progress(self, task_ids):
                started.set()
                await asyncio.Event().wait()

        monitor = _monitor(Client())
        task = asyncio.create_task(monitor.run())
        await asyncio.wait_for(started.wait(), 1)
        assert monitor._request_coordinator.is_active(TASK_API_GROUP)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert not monitor._request_coordinator.is_active(TASK_API_GROUP)

    asyncio.run(scenario())
