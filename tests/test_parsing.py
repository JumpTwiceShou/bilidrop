from bilibili_drops_miner.utils import (
    parse_notification_urls,
    parse_room_ids,
    parse_task_ids,
)


def test_room_ids_accept_urls_and_deduplicate() -> None:
    assert parse_room_ids(
        "23612045,https://live.bilibili.com/23612045,1017"
    ) == [23612045, 1017]


def test_task_ids_decode_url_and_deduplicate() -> None:
    assert parse_task_ids(
        "https://api.bilibili.com/x/task/totalv2?task_ids=a%2Cb%2Ca&csrf=x"
    ) == ["a", "b"]


def test_notification_urls_have_dedicated_parser() -> None:
    assert parse_notification_urls("gotifys://host/token\ngotifys://host/token,schan://key") == [
        "gotifys://host/token",
        "schan://key",
    ]
