import json

from bilibili_drops_miner.utils import extract_bili_live_task_groups


def test_existing_initial_state_task_group_fixture() -> None:
    state = {
        "EraTasklistPc": [{"tasklist": [{"taskId": "a"}, {"taskId": "b"}]}],
        "EvaPositionBox": [{"left": 0, "top": 0}],
        "EvaTabs.Panel": [
            {
                "id": "today",
                "tabItem": {"tabItemProps": {"textContent": {"content": "今日"}}},
            }
        ],
        "EvaTabs": [{"activatedTabPanelId": "today"}],
    }
    html = f"<script>window.__initialState = {json.dumps(state)}</script>"
    assert extract_bili_live_task_groups(html) == [
        {"label": "今日", "task_ids": ["a", "b"], "active": True}
    ]


def test_current_nested_eva_activity_task_groups() -> None:
    state = {
        "layerTree": [
            {
                "name": "EvaLayoutContainer",
                "slots": [
                    {
                        "children": [
                            {
                                "name": "EvaTabs",
                                "props": {"activatedTabPanelId": "day-one"},
                                "slots": [
                                    {
                                        "children": [
                                            {
                                                "name": "EvaTabs.Panel",
                                                "props": {
                                                    "id": "day-one",
                                                    "tabItem": {
                                                        "tabItemProps": {
                                                            "textContent": {
                                                                "content": "DAY1观赛奖励"
                                                            }
                                                        }
                                                    },
                                                },
                                                "slots": [
                                                    {
                                                        "children": [
                                                            {
                                                                "name": "EraTasklistPc",
                                                                "props": {
                                                                    "tasklist": [
                                                                        {
                                                                            "taskId": "day-one-task"
                                                                        }
                                                                    ]
                                                                },
                                                                "slots": [],
                                                            }
                                                        ]
                                                    }
                                                ],
                                            },
                                            {
                                                "name": "EvaTabs.Panel",
                                                "props": {
                                                    "id": "day-two",
                                                    "tabItem": {
                                                        "activatedTabItemProps": {
                                                            "textContent": {
                                                                "content": "DAY2观赛奖励"
                                                            }
                                                        }
                                                    },
                                                },
                                                "slots": [
                                                    {
                                                        "children": [
                                                            {
                                                                "name": "EraTasklistPc",
                                                                "props": {
                                                                    "tasklist": [
                                                                        {
                                                                            "taskId": "day-two-task"
                                                                        }
                                                                    ]
                                                                },
                                                                "slots": [],
                                                            }
                                                        ]
                                                    }
                                                ],
                                            },
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    html = (
        "<script>window.__initialState={\"BaseInfo\":{}};"
        f"window.__BILIACT_EVAPAGEDATA__={json.dumps(state)};</script>"
    )

    assert extract_bili_live_task_groups(html) == [
        {
            "label": "DAY1观赛奖励",
            "task_ids": ["day-one-task"],
            "active": True,
        },
        {
            "label": "DAY2观赛奖励",
            "task_ids": ["day-two-task"],
            "active": False,
        },
    ]


def test_nested_activity_group_keeps_shanghai_schedule() -> None:
    state = {
        "layerTree": [
            {
                "name": "EvaTabs",
                "props": {"activatedTabPanelId": "day-one"},
                "slots": [
                    {
                        "children": [
                            {
                                "name": "EvaTabs.Panel",
                                "props": {
                                    "id": "day-one",
                                    "tabItem": {
                                        "tabItemProps": {
                                            "textContent": {
                                                "content": "DAY1观赛奖励"
                                            }
                                        }
                                    },
                                },
                                "slots": [
                                    {
                                        "children": [
                                            {
                                                "name": "EvaText",
                                                "props": {
                                                    "content": (
                                                        "活动任务有效统计时间："
                                                        "2026年7月29日 17:30-"
                                                        "2026年7月30日 17:00"
                                                    )
                                                },
                                            },
                                            {
                                                "name": "EraTasklistPc",
                                                "props": {
                                                    "tasklist": [
                                                        {"taskId": "daily"}
                                                    ]
                                                },
                                            },
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    html = (
        "<script>window.__BILIACT_EVAPAGEDATA__ = "
        f"{json.dumps(state, ensure_ascii=False)}</script>"
    )

    group = extract_bili_live_task_groups(html)[0]

    assert group["start_at"] == "2026-07-29T17:30:00+08:00"
    assert group["end_at"] == "2026-07-30T17:00:00+08:00"


def test_active_day_collects_every_task_from_all_nested_task_lists() -> None:
    state = {
        "layerTree": [
            {
                "name": "EvaTabs",
                "props": {"activatedTabPanelId": "today"},
                "slots": [
                    {
                        "children": [
                            {
                                "name": "EvaTabs.Panel",
                                "props": {"id": "today"},
                                "slots": [
                                    {
                                        "children": [
                                            {
                                                "name": "EraTasklistPc",
                                                "props": {
                                                    "tasklist": [
                                                        {"taskId": "watch"},
                                                        {"taskId": "share"},
                                                    ]
                                                },
                                                "slots": [],
                                            },
                                            {
                                                "name": "EraTasklistPc",
                                                "props": {
                                                    "tasklist": [
                                                        {"taskId": "login"},
                                                        {"taskId": "watch"},
                                                    ]
                                                },
                                                "slots": [],
                                            },
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    html = (
        "<script>window.__BILIACT_EVAPAGEDATA__ = "
        f"{json.dumps(state)}</script>"
    )

    assert extract_bili_live_task_groups(html)[0]["task_ids"] == [
        "watch",
        "share",
        "login",
    ]


def test_current_nested_eva_activity_without_tabs() -> None:
    state = {
        "layerTree": [
            {
                "name": "EraTasklistPc",
                "props": {"tasklist": [{"taskId": "standalone-task"}]},
                "slots": [],
            }
        ]
    }
    html = (
        "<script>window.__BILIACT_EVAPAGEDATA__ = "
        f"{json.dumps(state)}</script>"
    )

    assert extract_bili_live_task_groups(html) == [
        {
            "label": "当前任务",
            "task_ids": ["standalone-task"],
            "active": True,
        }
    ]


def test_current_activity_repairs_bilibili_mojibake_label() -> None:
    state = {
        "layerTree": [
            {
                "name": "EvaTabs",
                "props": {"activatedTabPanelId": "today"},
                "slots": [
                    {
                        "children": [
                            {
                                "name": "EvaTabs.Panel",
                                "props": {
                                    "id": "today",
                                    "tabItem": {
                                        "tabItemProps": {
                                            "textContent": {
                                                "content": "DAY1밖힙쉽쟨"
                                            }
                                        }
                                    },
                                },
                                "slots": [
                                    {
                                        "children": [
                                            {
                                                "name": "EraTasklistPc",
                                                "props": {
                                                    "tasklist": [
                                                        {"taskId": "today-task"}
                                                    ]
                                                },
                                                "slots": [],
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    html = (
        "<script>window.__BILIACT_EVAPAGEDATA__ = "
        f"{json.dumps(state, ensure_ascii=False)}</script>"
    )

    assert extract_bili_live_task_groups(html)[0]["label"] == "DAY1观赛奖励"
