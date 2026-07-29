from bilibili_drops_miner.client_parts.tasks import parse_task_progress_payload


def test_progress_parser_keeps_every_task_and_nested_reward_node() -> None:
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "task_id": "daily",
                    "task_name": "观看直播",
                    "cur_value": 120,
                    "limit": 240,
                    "check_points": [
                        {
                            "ztasksid": "node-60",
                            "task_desc": "观看60分钟",
                            "status": 6,
                            "cur_value": 120,
                            "limit": 60,
                            "award": {"name": "头像框", "count": 1},
                        },
                        {
                            "ztasksid": "node-120",
                            "task_desc": "观看120分钟",
                            "status": 3,
                            "cur_value": 120,
                            "limit": 120,
                            "reward_info": {"award_name": "喷漆", "num": 2},
                        },
                    ],
                },
                {
                    "task_id": "share",
                    "task_name": "分享直播间",
                    "cur_value": 0,
                    "limit": 1,
                },
            ]
        },
    }

    progresses = parse_task_progress_payload(payload)

    assert [task.task_id for task in progresses] == ["daily", "share"]
    assert [point.sid for point in progresses[0].check_points] == [
        "node-60",
        "node-120",
    ]
    assert progresses[0].check_points[0].award_name == "头像框"
    assert progresses[0].check_points[1].award_count == 2
