from bilibili_drops_miner.client_parts.models import (
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.gui_parts.task_presenter import (
    format_task_progress,
    task_progress_table_rows,
)


def test_task_progress_fixture_remains_human_readable() -> None:
    output = format_task_progress(
        [
            TaskProgress(
                task_id="task-001",
                task_name="观看直播10分钟",
                status=0,
                cur_value=5,
                limit_value=10,
            )
        ]
    )
    assert "观看直播" in output
    assert "5/10" in output
    assert "50%" in output


def test_table_rows_expand_all_tasks_and_reward_checkpoints() -> None:
    rows = task_progress_table_rows(
        [
            TaskProgress(
                "daily",
                "观看直播",
                0,
                120,
                240,
                check_points=[
                    TaskCheckpointProgress(
                        "60",
                        "观看60分钟",
                        3,
                        120,
                        60,
                        "头像框",
                        1,
                    ),
                    TaskCheckpointProgress(
                        "120",
                        "观看120分钟",
                        2,
                        120,
                        120,
                        "喷漆",
                        2,
                    ),
                ],
            ),
            TaskProgress("share", "分享直播间", 0, 0, 1),
        ]
    )

    assert [row.progress_id for row in rows] == ["60", "120", "share"]
    assert rows[0].is_claimed
    assert rows[1].is_completed
    assert rows[1].is_claimable
    assert not rows[1].is_claimed
    assert rows[1].reward_text == "喷漆 × 2"
    assert rows[2].label == "分享直播间"
