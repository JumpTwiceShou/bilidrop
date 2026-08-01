from bilibili_drops_miner.request_coordinator import (
    TASK_API_GROUP,
    AccountRequestCoordinator,
    looks_rate_limited,
)


def test_same_account_task_requests_are_serialized() -> None:
    coordinator = AccountRequestCoordinator()
    first = coordinator.try_begin("task-refresh", group=TASK_API_GROUP, now=10)

    assert first is not None
    assert coordinator.try_begin(
        "reward-claim",
        group=TASK_API_GROUP,
        now=10,
    ) is None

    coordinator.finish(first, now=10)
    assert coordinator.try_begin(
        "reward-claim",
        group=TASK_API_GROUP,
        now=10,
    ) is not None


def test_rate_limit_cooldown_is_account_group_scoped() -> None:
    coordinator = AccountRequestCoordinator()
    permit = coordinator.try_begin("reward-claim", group=TASK_API_GROUP, now=20)
    assert permit is not None

    coordinator.finish(permit, cooldown_seconds=30, now=20)

    assert coordinator.try_begin(
        "task-refresh",
        group=TASK_API_GROUP,
        now=49,
    ) is None
    assert coordinator.try_begin(
        "login-validation",
        group="auth-api",
        now=49,
    ) is not None
    assert coordinator.try_begin(
        "task-refresh",
        group=TASK_API_GROUP,
        now=50,
    ) is not None


def test_rate_limit_detection_accepts_chinese_and_english_messages() -> None:
    assert looks_rate_limited("查询领奖信息触发限频")
    assert looks_rate_limited("Too Many Requests")
    assert not looks_rate_limited("network timeout")
