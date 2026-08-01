from bilibili_drops_miner.adaptive_concurrency import (
    AdaptiveConcurrencyController,
)
from bilibili_drops_miner.client_parts.models import (
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.domain import TaskSnapshot


def _snapshot(minutes: float, task_id: str = "daily") -> TaskSnapshot:
    return TaskSnapshot(
        progresses=(
            TaskProgress(
                task_id,
                "观看直播",
                1,
                minutes,
                300,
                check_points=[
                    TaskCheckpointProgress(
                        "node-300",
                        "观看300分钟",
                        1,
                        minutes,
                        300,
                    )
                ],
            ),
        )
    )


def test_guarded_task_waits_for_initial_progress_before_catchup() -> None:
    controller = AdaptiveConcurrencyController(
        start_in_steady_mode=True
    )
    assert controller.target_sessions == 2
    assert controller.observe(_snapshot(20), observed_at=0) == 16


def test_just_started_task_can_begin_with_two_sessions() -> None:
    controller = AdaptiveConcurrencyController(
        start_in_steady_mode=True
    )
    assert controller.target_sessions == 2


def test_manual_start_drops_to_two_when_three_minute_gain_is_below_16() -> None:
    controller = AdaptiveConcurrencyController(
        sample_window_seconds=180,
        minimum_progress_delta=16,
    )

    assert controller.observe(_snapshot(180), observed_at=0) == 16
    assert controller.observe(_snapshot(195), observed_at=179) == 16
    assert controller.observe(_snapshot(195), observed_at=180) == 2
    assert controller.settled
    assert "不足 16" in controller.status_detail


def test_gain_of_16_keeps_catchup_and_starts_another_three_minute_round() -> None:
    controller = AdaptiveConcurrencyController(
        sample_window_seconds=180,
        minimum_progress_delta=16,
    )

    assert controller.observe(_snapshot(100), observed_at=0) == 16
    assert controller.observe(_snapshot(116), observed_at=180) == 16
    assert not controller.settled
    assert "开始下一轮" in controller.status_detail
    assert controller.observe(_snapshot(131), observed_at=360) == 2


def test_settled_task_stays_at_two_until_task_signature_changes() -> None:
    controller = AdaptiveConcurrencyController(
        sample_window_seconds=180,
    )

    controller.observe(_snapshot(100), observed_at=0)
    assert controller.observe(_snapshot(110), observed_at=180) == 2
    assert controller.observe(_snapshot(200), observed_at=360) == 2

    assert controller.observe(
        _snapshot(20, task_id="next-day"),
        observed_at=540,
    ) == 16
    assert not controller.settled


def test_task_id_change_inside_existing_runtime_gets_catchup_trial() -> None:
    controller = AdaptiveConcurrencyController(sample_window_seconds=180)
    controller.observe(_snapshot(100), observed_at=0)
    controller.observe(_snapshot(110), observed_at=180)

    assert controller.observe(
        _snapshot(0, task_id="next-day"),
        observed_at=360,
    ) == 16
    assert not controller.settled


def test_detected_new_task_with_zero_progress_uses_two_immediately() -> None:
    controller = AdaptiveConcurrencyController(
        start_in_steady_mode=True,
        sample_window_seconds=180,
    )

    assert controller.observe(_snapshot(0), observed_at=0) == 2
    assert controller.settled
    assert "初始进度为 0" in controller.status_detail


def test_manual_new_task_with_zero_progress_still_gets_three_minute_trial() -> None:
    controller = AdaptiveConcurrencyController(
        sample_window_seconds=180,
    )

    assert controller.observe(_snapshot(0), observed_at=0) == 16
    assert controller.observe(_snapshot(0), observed_at=179) == 16
    assert controller.observe(_snapshot(0), observed_at=180) == 2


def test_missing_progress_for_three_minutes_also_drops_to_two() -> None:
    controller = AdaptiveConcurrencyController(
        sample_window_seconds=180,
    )
    empty = TaskSnapshot()

    assert controller.observe(empty, observed_at=0) == 16
    assert controller.observe(empty, observed_at=179) == 16
    assert controller.observe(empty, observed_at=180) == 2
    assert "未取得可比较的观看进度" in controller.status_detail
