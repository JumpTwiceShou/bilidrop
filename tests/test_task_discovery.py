import json
import threading

from bilibili_drops_miner.domain import DiscoveryStatus
from bilibili_drops_miner.task_discovery import TaskDiscoveryService


def _html(groups, panels, active="") -> str:
    state = {
        "EraTasklistPc": groups,
        "EvaPositionBox": [{"left": 0, "top": index * 20} for index in range(len(groups))],
        "EvaTabs.Panel": panels,
        "EvaTabs": [{"activatedTabPanelId": active}],
    }
    return f"<script>window.__initialState = {json.dumps(state)}</script>"


class FakeDriver:
    def __init__(self, page_source: str) -> None:
        self.page_source = page_source
        self.url = ""
        self.quit_called = False
        self.cdp_calls: list[tuple[str, dict]] = []

    def set_page_load_timeout(self, _timeout) -> None:
        return None

    def set_script_timeout(self, _timeout) -> None:
        return None

    def execute_cdp_cmd(self, command: str, params: dict):
        self.cdp_calls.append((command, params))
        return {"success": True}

    def get(self, url: str) -> None:
        self.url = url

    def quit(self) -> None:
        self.quit_called = True


def test_headless_discovery_navigates_to_room_and_selects_active_group() -> None:
    driver = FakeDriver(
        _html(
            [
                {"tasklist": [{"taskId": "a"}]},
                {"tasklist": [{"taskId": "b"}]},
            ],
            [
                {"id": "old", "tabItem": {"tabItemProps": {"textContent": {"content": "昨日"}}}},
                {"id": "now", "tabItem": {"tabItemProps": {"textContent": {"content": "今日"}}}},
            ],
            active="now",
        )
    )
    service = TaskDiscoveryService(
        driver_factory=lambda _browser, _headless: driver,
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("chrome",),
    )
    result = service.discover(23612045, timeout_seconds=1)
    assert driver.url == "https://live.bilibili.com/23612045"
    assert driver.quit_called
    assert result.status == DiscoveryStatus.SUCCESS
    assert result.selected_group is not None
    assert result.selected_group.label == "今日"


def test_ambiguous_groups_are_not_silently_selected() -> None:
    driver = FakeDriver(
        _html(
            [{"tasklist": [{"taskId": "a"}]}, {"tasklist": [{"taskId": "b"}]}],
            [{"id": "one"}, {"id": "two"}],
        )
    )
    service = TaskDiscoveryService(
        driver_factory=lambda _browser, _headless: driver,
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("chrome",),
    )
    result = service.discover(1, timeout_seconds=1)
    assert result.status == DiscoveryStatus.AMBIGUOUS
    assert result.selected_group is None


def test_cancelled_discovery_does_not_start_browser() -> None:
    cancel = threading.Event()
    cancel.set()
    service = TaskDiscoveryService(
        driver_factory=lambda *_args: (_ for _ in ()).throw(AssertionError()),
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("chrome",),
    )
    assert service.discover(1, cancel_event=cancel).status == DiscoveryStatus.CANCELLED


def test_discovery_injects_cookie_before_room_navigation() -> None:
    driver = FakeDriver(_html([{"tasklist": [{"taskId": "a"}]}], [{"id": "one"}]))
    service = TaskDiscoveryService(
        driver_factory=lambda _browser, _headless: driver,
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("chrome",),
    )

    result = service.discover(
        1,
        timeout_seconds=1,
        cookie="SESSDATA=test-session; bili_jct=test-csrf",
    )

    assert result.status == DiscoveryStatus.SUCCESS
    cookie_calls = [
        params for command, params in driver.cdp_calls if command == "Network.setCookie"
    ]
    assert {item["name"] for item in cookie_calls} == {"SESSDATA", "bili_jct"}
    assert all(item["domain"] == ".bilibili.com" for item in cookie_calls)


class FailingDriver(FakeDriver):
    def get(self, url: str) -> None:
        self.url = url
        raise RuntimeError(
            "timeout: Timed out receiving message from renderer: 0.207\nStacktrace:\nprivate driver frames"
        )


def test_renderer_timeout_falls_back_without_exposing_stacktrace(caplog) -> None:
    edge = FailingDriver("")
    chrome = FakeDriver(
        _html([{"tasklist": [{"taskId": "fallback"}]}], [{"id": "one"}])
    )
    drivers = {"edge": edge, "chrome": chrome}
    service = TaskDiscoveryService(
        driver_factory=lambda browser, _headless: drivers[browser],
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("edge", "chrome"),
    )

    result = service.discover(1, timeout_seconds=2)

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "chrome"
    assert edge.quit_called and chrome.quit_called
    assert "Stacktrace" not in caplog.text


def test_renderer_timeout_result_is_concise(caplog) -> None:
    drivers: list[FailingDriver] = []

    def factory(_browser, _headless):
        driver = FailingDriver("")
        drivers.append(driver)
        return driver

    service = TaskDiscoveryService(
        driver_factory=factory,
        direct_fetcher=lambda *_args: "",
        room_status_fetcher=lambda *_args: 1,
        browser_provider=lambda _preferred: ("edge", "chrome"),
    )

    result = service.discover(1, timeout_seconds=2)

    assert result.status == DiscoveryStatus.TIMEOUT
    assert "页面渲染超时" in result.message
    assert "Stacktrace" not in result.message
    assert "Stacktrace" not in caplog.text
    assert all(driver.quit_called for driver in drivers)


def test_direct_discovery_does_not_depend_on_live_browser_state() -> None:
    service = TaskDiscoveryService(
        direct_fetcher=lambda room_id, cookie, _timeout: _html(
            [{"tasklist": [{"taskId": f"offline-{room_id}"}]}],
            [{"id": "current"}],
        ),
        driver_factory=lambda *_args: (_ for _ in ()).throw(
            AssertionError("direct discovery must not start a browser")
        ),
        room_status_fetcher=lambda *_args: 0,
        browser_provider=lambda _preferred: ("chrome",),
    )

    result = service.discover(23612045, cookie="SESSDATA=fixture")

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert result.selected_group is not None
    assert result.selected_group.task_ids == ("offline-23612045",)


def test_offline_room_checks_task_page_before_skipping_browser_wait() -> None:
    page_checked: list[int] = []

    def direct_fetcher(room_id, *_args):
        page_checked.append(room_id)
        return ""

    service = TaskDiscoveryService(
        room_status_fetcher=lambda room_id, _timeout: 0 if room_id == 23612045 else 1,
        direct_fetcher=direct_fetcher,
        driver_factory=lambda *_args: (_ for _ in ()).throw(
            AssertionError("offline room must not start a browser")
        ),
        browser_provider=lambda _preferred: ("chrome",),
    )

    result = service.discover(23612045, timeout_seconds=30)

    assert result.status == DiscoveryStatus.OFFLINE
    assert page_checked == [23612045]
    assert "未开播" in result.message
    assert "仍可直接开始挂机" in result.message
