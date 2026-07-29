import asyncio

from bilibili_drops_miner.client_parts.models import (
    MissionRewardClaimResult,
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.domain import TaskSnapshot
from bilibili_drops_miner.task_monitor import AccountTaskMonitor


class FakeClient:
    def __init__(self) -> None:
        self.poll_count = 0
        self.reward_calls: list[list[str]] = []

    async def get_task_progress(self, task_ids):
        self.poll_count += 1
        return [
            TaskProgress(task_id, "任务", 2, 1, 1)
            for task_id in task_ids
        ]

    async def receive_all_mission_rewards(self, task_ids):
        self.reward_calls.append(list(task_ids))
        return [
            MissionRewardClaimResult(
                task_id=task_id,
                task_name="任务",
                reward_name="奖励",
                status=6,
                message="领取成功",
                success=True,
                skipped=False,
            )
            for task_id in task_ids
        ]


class FakeNotifier:
    enabled = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, *, title: str, body: str) -> bool:
        assert "Bilibili" in title
        assert "进度" in body
        self.messages.append((title, body))
        return True

    @property
    def calls(self) -> int:
        return len(self.messages)


def test_account_monitor_polls_and_notifies_once() -> None:
    async def scenario() -> None:
        client = FakeClient()
        notifier = FakeNotifier()
        snapshots = []
        monitor = AccountTaskMonitor(
            client=client,
            notifier=notifier,
            config=MinerConfig("cookie", [1], task_ids=["a"]),
            account_label="测试账号（UID 10001）",
            on_snapshot=snapshots.append,
        )
        task = asyncio.create_task(monitor.run())
        while not snapshots:
            await asyncio.sleep(0)
        monitor.request_refresh()
        while client.poll_count < 2:
            await asyncio.sleep(0)
        await monitor.stop()
        await task
        assert notifier.calls == 1
        title, body = notifier.messages[0]
        assert title == "Bilibili 掉宝任务已完成"
        assert "账号：测试账号（UID 10001）" in body
        assert "直播间：1" in body
        assert "任务：任务（a）" in body
        assert "状态：任务已完成；奖励已自动领取" in body
        assert "奖励：奖励" in body
        assert snapshots[-1].completed_count == 1
        assert client.reward_calls == [["a"]]

    asyncio.run(scenario())


def test_successful_claim_retry_sends_follow_up_status() -> None:
    class RetryClient(FakeClient):
        async def receive_all_mission_rewards(self, task_ids):
            self.reward_calls.append(list(task_ids))
            success = len(self.reward_calls) >= 2
            return [
                MissionRewardClaimResult(
                    task_id=task_id,
                    task_name="任务",
                    reward_name="奖励",
                    status=6 if success else 0,
                    message="领取成功" if success else "稍后重试",
                    success=success,
                    skipped=False,
                )
                for task_id in task_ids
            ]

    async def scenario() -> None:
        client = RetryClient()
        notifier = FakeNotifier()
        monitor = AccountTaskMonitor(
            client=client,
            notifier=notifier,
            config=MinerConfig("cookie", [23612045], task_ids=["a"]),
            account_label="守望账号（UID 42）",
        )
        task = asyncio.create_task(monitor.run())
        while notifier.calls < 1:
            await asyncio.sleep(0)
        monitor.request_refresh()
        monitor._claim_retry_after.clear()
        while notifier.calls < 2:
            await asyncio.sleep(0)
        await monitor.stop()
        await task

        assert len(client.reward_calls) == 2
        assert "奖励领取失败，将自动重试" in notifier.messages[0][1]
        assert notifier.messages[1][0] == "Bilibili 掉宝奖励已领取"
        assert "奖励重试领取成功" in notifier.messages[1][1]
        assert "直播间：23612045" in notifier.messages[1][1]

    asyncio.run(scenario())


def test_reward_claims_are_routed_through_account_monitor() -> None:
    async def scenario() -> None:
        monitor = AccountTaskMonitor(
            client=FakeClient(),
            notifier=FakeNotifier(),
            config=MinerConfig("cookie", [1], task_ids=["a", "b"]),
        )
        results = await monitor.claim_rewards()
        assert [result.task_id for result in results] == ["a", "b"]
        assert monitor.client.reward_calls == [["a", "b"]]

    asyncio.run(scenario())


def test_completed_checkpoints_claim_separately_under_same_outer_task() -> None:
    async def scenario() -> None:
        client = FakeClient()
        monitor = AccountTaskMonitor(
            client=client,
            notifier=FakeNotifier(),
            config=MinerConfig("cookie", [23612045], task_ids=["daily-task"]),
        )
        progresses = [
            TaskProgress(
                task_id="daily-task",
                task_name="观看直播",
                status=0,
                cur_value=120,
                limit_value=240,
                check_points=[
                    TaskCheckpointProgress("60", "观看60分钟", 3, 120, 60),
                    TaskCheckpointProgress("120", "观看120分钟", 2, 120, 120),
                    TaskCheckpointProgress("180", "观看180分钟", 1, 120, 180),
                ],
            )
        ]

        first_attempts = await monitor._auto_claim_new_completions(progresses)
        second_attempts = await monitor._auto_claim_new_completions(progresses)

        assert client.reward_calls == [["120"]]
        assert [attempt.unit.marker_id for attempt in first_attempts] == [
            "daily-task:checkpoint:120",
        ]
        assert second_attempts == []
        assert TaskSnapshot(progresses=tuple(progresses)).completed_count == 2

    asyncio.run(scenario())


def test_later_checkpoint_is_not_suppressed_by_earlier_success() -> None:
    async def scenario() -> None:
        client = FakeClient()
        monitor = AccountTaskMonitor(
            client=client,
            notifier=FakeNotifier(),
            config=MinerConfig("cookie", [1], task_ids=["daily-task"]),
        )
        sixty = TaskCheckpointProgress("60", "观看60分钟", 2, 60, 60)
        later = TaskCheckpointProgress("120", "观看120分钟", 1, 60, 120)
        task = TaskProgress(
            "daily-task",
            "观看直播",
            0,
            60,
            240,
            check_points=[sixty, later],
        )

        await monitor._auto_claim_new_completions([task])
        later.cur_value = 120
        later.status = 2
        await monitor._auto_claim_new_completions([task])

        assert client.reward_calls == [["60"], ["120"]]

    asyncio.run(scenario())


def test_failed_auto_claim_enters_cooldown_instead_of_retrying_each_poll() -> None:
    class FailingClient(FakeClient):
        async def receive_all_mission_rewards(self, task_ids):
            self.reward_calls.append(list(task_ids))
            return [
                MissionRewardClaimResult(
                    task_id=task_id,
                    task_name="任务",
                    reward_name="奖励",
                    status=0,
                    message="触发限频",
                    success=False,
                    skipped=False,
                )
                for task_id in task_ids
            ]

    async def scenario() -> None:
        client = FailingClient()
        monitor = AccountTaskMonitor(
            client=client,
            notifier=FakeNotifier(),
            config=MinerConfig("cookie", [1], task_ids=["daily-task"]),
        )
        checkpoint = TaskCheckpointProgress(
            "node-180", "观看180分钟", 2, 181, 180
        )
        progress = TaskProgress(
            "daily-task",
            "观看直播",
            1,
            181,
            300,
            check_points=[checkpoint],
        )

        await monitor._auto_claim_new_completions([progress])
        await monitor._auto_claim_new_completions([progress])

        assert client.reward_calls == [["node-180"]]
        assert monitor._claim_failure_counts[
            "daily-task:checkpoint:node-180"
        ] == 1

    asyncio.run(scenario())
