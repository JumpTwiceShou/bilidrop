import threading

from bilibili_drops_miner.domain import DiscoveryStatus, TaskDiscoveryResult
from bilibili_drops_miner.gui_parts import browser_actions as browser_actions_module


def test_selected_browser_and_cookie_are_reused_for_background_discovery(
    monkeypatch,
) -> None:
    monkeypatch.setattr(browser_actions_module, "available_browsers", lambda: ["chrome"])
    captured: dict = {}
    called = threading.Event()

    class DiscoveryService:
        def discover(self, room_id, **kwargs):
            captured.update(room_id=room_id, **kwargs)
            called.set()
            return TaskDiscoveryResult(
                room_id=room_id,
                status=DiscoveryStatus.CANCELLED,
                message="任务识别已取消",
            )

    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_args: None,
        show_error=lambda *_args: None,
        post_ui_task=lambda *_args: None,
        set_room_id=lambda _room_id: None,
        set_cookie=lambda _cookie: None,
        set_task_ids=lambda _task_ids: None,
        get_room_ids=lambda: [23612045],
        get_cookie=lambda: "SESSDATA=fixture",
    )
    actions._discovery_service = DiscoveryService()

    assert actions.pick_browser() == "chrome"
    actions.auto_fetch_task_ids()
    assert called.wait(2)
    assert captured["room_id"] == 23612045
    assert captured["browser_preference"] == "chrome"
    assert captured["cookie"] == "SESSDATA=fixture"


def test_offline_result_automatically_starts_visible_browser_fallback(
    monkeypatch,
) -> None:
    statuses: list[tuple[str, bool]] = []
    fallbacks: list[tuple[int | None, bool]] = []
    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_args: None,
        show_error=lambda *_args: None,
        post_ui_task=lambda *_args: None,
        set_room_id=lambda _room_id: None,
        set_cookie=lambda _cookie: None,
        set_task_ids=lambda _task_ids: None,
        set_discovery_status=lambda text, error=False: statuses.append((text, error)),
    )
    monkeypatch.setattr(
        actions,
        "_visible_auto_fetch_task_ids",
        lambda room_id=None, *, confirm=True: fallbacks.append(
            (room_id, confirm)
        ),
    )

    actions._handle_background_discovery(
        TaskDiscoveryResult(
            room_id=23612045,
            status=DiscoveryStatus.OFFLINE,
            message="房间当前未开播，已停止等待任务面板",
        )
    )

    assert statuses == [("后台识别未完成，正在启动可见浏览器兜底…", False)]
    assert fallbacks == [(23612045, False)]


def test_cancelled_background_result_does_not_start_visible_fallback(
    monkeypatch,
) -> None:
    statuses: list[tuple[str, bool]] = []
    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_args: None,
        show_error=lambda *_args: None,
        post_ui_task=lambda *_args: None,
        set_room_id=lambda _room_id: None,
        set_cookie=lambda _cookie: None,
        set_task_ids=lambda _task_ids: None,
        set_discovery_status=lambda text, error=False: statuses.append((text, error)),
    )
    monkeypatch.setattr(
        actions,
        "_visible_auto_fetch_task_ids",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cancelled discovery must not start fallback")
        ),
    )

    actions._handle_background_discovery(
        TaskDiscoveryResult(
            room_id=23612045,
            status=DiscoveryStatus.CANCELLED,
            message="任务识别已取消",
        )
    )

    assert statuses == [("任务识别已取消", False)]


def test_visible_fallback_keeps_totalv2_network_compatibility(monkeypatch) -> None:
    captured: dict = {}
    task_values: list[str] = []
    room_values: list[int] = []
    monkeypatch.setattr(
        browser_actions_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: browser_actions_module.QMessageBox.Ok,
    )
    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_args: None,
        show_error=lambda *_args: None,
        post_ui_task=lambda callback, *args: callback(*args),
        set_room_id=room_values.append,
        set_cookie=lambda _cookie: None,
        set_task_ids=task_values.append,
    )
    monkeypatch.setattr(actions, "pick_browser", lambda: "chrome")

    def capture_sniffer(url_keyword, hint, **kwargs):
        captured.update(url_keyword=url_keyword, hint=hint, **kwargs)

    monkeypatch.setattr(actions, "browser_sniff", capture_sniffer)

    actions._visible_auto_fetch_task_ids(23612045)

    assert captured["url_keyword"] == "/x/task/totalv2"
    assert callable(captured["on_failure"])
    captured["on_network_match"](
        {
            "url": "https://api.bilibili.com/x/task/totalv2",
            "page_url": "https://live.bilibili.com/23612045",
            "data": {
                "code": 0,
                "data": {
                    "list": [
                        {"task_id": "network-task-a"},
                        {"task_id": "network-task-b"},
                    ]
                },
            },
        }
    )

    assert room_values == [23612045]
    assert task_values == ["network-task-a,network-task-b"]


def test_visible_fallback_ignores_totalv2_before_entering_live_room(
    monkeypatch,
) -> None:
    captured: dict = {}
    task_values: list[str] = []
    monkeypatch.setattr(
        browser_actions_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: browser_actions_module.QMessageBox.Ok,
    )
    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_args: None,
        show_error=lambda *_args: None,
        post_ui_task=lambda callback, *args: callback(*args),
        set_room_id=lambda _room_id: None,
        set_cookie=lambda _cookie: None,
        set_task_ids=task_values.append,
    )
    monkeypatch.setattr(actions, "pick_browser", lambda: "chrome")
    monkeypatch.setattr(
        actions,
        "browser_sniff",
        lambda url_keyword, hint, **kwargs: captured.update(kwargs),
    )

    actions._visible_auto_fetch_task_ids(23612045)

    try:
        captured["on_network_match"](
            {
                "url": "https://api.bilibili.com/x/task/totalv2",
                "page_url": "https://www.bilibili.com/",
                "data": {
                    "code": 0,
                    "data": {"list": [{"task_id": "unrelated-task"}]},
                },
            }
        )
    except ValueError as exc:
        assert str(exc) == "尚未进入 Bilibili 直播间"
    else:
        raise AssertionError("主页请求不得提前结束直播间任务识别")

    assert task_values == []
