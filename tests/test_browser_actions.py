import threading
from datetime import datetime, timedelta, timezone

import pytest

from bilibili_drops_miner.domain import (
    DiscoveredTaskGroup,
    DiscoveryStatus,
    TaskDiscoveryResult,
)
from bilibili_drops_miner.gui_parts import browser_actions as browser_actions_module


def test_selected_browser_and_cookie_are_reused_for_background_discovery(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        browser_actions_module, "available_browsers", lambda: ["chrome"]
    )
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
        lambda room_id=None, *, confirm=True: fallbacks.append((room_id, confirm)),
    )

    actions._handle_background_discovery(
        TaskDiscoveryResult(
            room_id=23612045,
            status=DiscoveryStatus.OFFLINE,
            message="房间当前未开播，已停止等待任务面板",
        )
    )

    assert statuses == [("正在启动可见浏览器兜底，继续识别任务…", False)]
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


def _actions(monkeypatch, *, queued=False):
    values = {"rooms": [], "tasks": [], "statuses": [], "queue": [], "sniff": {}}

    def post(callback, *args):
        if queued:
            values["queue"].append((callback, args))
        else:
            callback(*args)

    actions = browser_actions_module.BrowserActions(
        parent=None,
        show_warning=lambda *_: None,
        show_error=lambda *_: None,
        post_ui_task=post,
        set_room_id=values["rooms"].append,
        set_task_ids=values["tasks"].append,
        set_cookie=lambda *_: None,
        get_room_ids=lambda: [111],
        set_discovery_status=lambda *args: values["statuses"].append(args),
    )
    monkeypatch.setattr(actions, "pick_browser", lambda: "chrome")
    monkeypatch.setattr(
        actions, "browser_sniff", lambda *args, **kw: values["sniff"].update(kw)
    )
    monkeypatch.setattr(
        browser_actions_module,
        "extract_bili_live_task_groups",
        lambda _: [{"task_ids": ["task"], "active": True}],
    )
    return actions, values


def test_visible_html_rejects_another_room(monkeypatch):
    actions, values = _actions(monkeypatch)
    actions._visible_auto_fetch_task_ids(111, confirm=False)
    assert not values["sniff"]["on_page_html"]("html", "https://live.bilibili.com/222")
    assert values["rooms"] == values["tasks"] == []


@pytest.mark.parametrize("cancel_after_post", [False, True])
def test_visible_html_cannot_apply_after_cancellation(monkeypatch, cancel_after_post):
    actions, values = _actions(monkeypatch, queued=True)
    actions._visible_auto_fetch_task_ids(111, confirm=False)
    callback = values["sniff"]["on_page_html"]
    if cancel_after_post:
        assert callback("html", "https://live.bilibili.com/111")
    actions.cancel_discovery()
    if not cancel_after_post:
        assert not callback("html", "https://live.bilibili.com/111")
    for callback, args in values["queue"]:
        callback(*args)
    assert values["rooms"] == values["tasks"] == []


def test_background_queued_success_cannot_apply_after_cancellation(monkeypatch):
    actions, values = _actions(monkeypatch)
    actions.cancel_discovery()
    actions._handle_background_discovery(
        TaskDiscoveryResult(
            room_id=111,
            status=DiscoveryStatus.SUCCESS,
            groups=(DiscoveredTaskGroup("today", ("task",), True),),
        )
    )
    assert values["tasks"] == []


def test_visible_selection_uses_schedule_instead_of_active_tab(monkeypatch):
    actions, values = _actions(monkeypatch)
    now = datetime.now(timezone.utc)
    actions.apply_selected_task_group(
        111,
        [
            {
                "task_ids": ["expired"],
                "active": True,
                "start_at": now - timedelta(days=2),
                "end_at": now - timedelta(days=1),
            },
            {
                "task_ids": ["current"],
                "active": False,
                "start_at": now - timedelta(hours=1),
                "end_at": now + timedelta(hours=1),
            },
        ],
    )
    assert values["tasks"] == ["current"]


def test_visible_html_accepts_verified_room_alias(monkeypatch):
    actions, values = _actions(monkeypatch)
    actions._visible_auto_fetch_task_ids(111, confirm=False)
    html = '<script>window.__NEPTUNE_IS_MY_WAIFU__ = {"roomInitRes":{"data":{"room_id":222,"short_id":111}}}</script>'
    assert values["sniff"]["on_page_html"](html, "https://live.bilibili.com/222")
    assert values["rooms"] == [222]
    assert values["tasks"] == ["task"]


def test_new_discovery_does_not_revive_old_queued_success(monkeypatch):
    actions, values = _actions(monkeypatch, queued=True)
    actions._visible_auto_fetch_task_ids(111, confirm=False)
    assert values["sniff"]["on_page_html"]("html", "https://live.bilibili.com/111")
    actions.cancel_discovery()
    called = threading.Event()

    class Service:
        def discover(self, room_id, **kw):
            called.set()
            return TaskDiscoveryResult(room_id, DiscoveryStatus.CANCELLED)

    actions._discovery_service = Service()
    actions.auto_fetch_task_ids()
    assert called.wait(2)
    # This callback belongs to the old attempt even though the new event is clear.
    callback, args = values["queue"][0]
    callback(*args)
    assert values["tasks"] == []


def test_cancelling_ambiguous_group_choice_releases_discovery_state(monkeypatch):
    actions, values = _actions(monkeypatch)
    monkeypatch.setattr(
        browser_actions_module.QInputDialog, "getItem", lambda *a, **kw: ("", False)
    )
    actions._handle_background_discovery(
        TaskDiscoveryResult(
            room_id=111,
            status=DiscoveryStatus.AMBIGUOUS,
            groups=(
                DiscoveredTaskGroup("one", ("a",)),
                DiscoveredTaskGroup("two", ("b",)),
            ),
        )
    )
    assert values["tasks"] == []
    assert values["statuses"][-1] == ("任务识别已取消", False)
