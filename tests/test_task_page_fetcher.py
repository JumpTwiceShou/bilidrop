import json
import time

import httpx
import pytest

from bilibili_drops_miner.domain import DiscoveryStatus
from bilibili_drops_miner.task_discovery import TaskDiscoveryService


ROOM_URL = "https://live.bilibili.com/23612045"
ACTIVITY_URL = "https://www.bilibili.com/blackboard/era/fixture-drops.html"
TASK_HTML = '<script>window.__initialState=' + json.dumps(
    {
        "EraTasklistPc": [{"tasklist": [{"taskId": "fixture-current-task"}]}],
        "EvaTabs.Panel": [{"id": "today"}],
        "EvaTabs": [{"activatedTabPanelId": "today"}],
    }
) + ";</script>"


@pytest.fixture
def serve_pages(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        requests = []

        def record(request):
            requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(record)

        def client_factory(*args, **kwargs):
            return real_client(*args, transport=transport, **kwargs)

        def get(url, **kwargs):
            with client_factory() as client:
                return client.get(url, **kwargs)

        monkeypatch.setattr(httpx, "Client", client_factory)
        monkeypatch.setattr(httpx, "get", get)
        return requests

    return install


def discover_without_browser(cookie=""):
    service = TaskDiscoveryService(
        browser_provider=lambda _preferred: (),
        room_status_fetcher=lambda *_args: 1,
    )
    return service.discover(23612045, cookie=cookie, force_refresh=True)


@pytest.mark.parametrize("failure", ["unavailable", "read-timeout"])
def test_transient_web_failure_is_retried_before_browser_fallback(serve_pages, failure):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure == "read-timeout":
                raise httpx.ReadTimeout("temporary failure", request=request)
            return httpx.Response(503)
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert result.selected_group.task_ids == ("fixture-current-task",)
    assert len(requests) == 2


def test_linked_activity_page_is_read_without_starting_a_browser(serve_pages):
    def handler(request):
        if str(request.url) == ROOM_URL:
            return httpx.Response(
                200,
                text='<iframe src="//www.bilibili.com/blackboard/era/fixture-drops.html'
                '?room=23612045&amp;source=live"></iframe>',
            )
        assert str(request.url) == ACTIVITY_URL + "?room=23612045&source=live"
        assert request.headers["Referer"] == ROOM_URL
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser(cookie="SESSDATA=fixture")

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert result.selected_group.task_ids == ("fixture-current-task",)
    assert len(requests) == 2
    assert all(request.headers.get("Cookie") == "SESSDATA=fixture" for request in requests)


def test_embedded_room_activity_url_is_used_but_advertisements_are_ignored(serve_pages):
    state = {
        "roomInfoRes": {
            "data": {
                "ad_banner_info": {
                    "data": [{"link": "https://www.bilibili.com/blackboard/era/advert.html"}]
                },
                "activity_banner_info": {"url": ACTIVITY_URL},
            }
        }
    }
    room_html = '<script>window.__NEPTUNE_IS_MY_WAIFU__=' + json.dumps(state).replace(
        "/", r"\u002F"
    ) + ";</script>"

    def handler(request):
        if str(request.url) == ROOM_URL:
            return httpx.Response(200, text=room_html)
        assert str(request.url) == ACTIVITY_URL
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.status == DiscoveryStatus.SUCCESS
    assert [str(request.url) for request in requests] == [ROOM_URL, ACTIVITY_URL]


def test_recommended_room_activity_is_not_used_for_the_requested_room(serve_pages):
    wrong_url = "https://www.bilibili.com/blackboard/era/other-room.html?room=999"
    state = {
        "relatedRooms": [{"room_id": 999, "activity_banner_info": {"url": wrong_url}}],
        "roomInfoRes": {
            "data": {
                "room_info": {"room_id": 23612045},
                "activity_banner_info": {"url": ACTIVITY_URL},
            }
        },
    }

    def handler(request):
        if str(request.url) == ROOM_URL:
            return httpx.Response(
                200, text="<script>window.__NEPTUNE_IS_MY_WAIFU__=" + json.dumps(state) + ";</script>"
            )
        task_html = TASK_HTML.replace("fixture-current-task", "wrong-room-task") if str(request.url) == wrong_url else TASK_HTML
        return httpx.Response(200, text=task_html)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.selected_group.task_ids == ("fixture-current-task",)
    assert [str(request.url) for request in requests] == [ROOM_URL, ACTIVITY_URL]


def test_iframe_activity_with_conflicting_room_id_is_ignored(serve_pages):
    wrong_url = ACTIVITY_URL + "?room_id=999"
    right_url = ACTIVITY_URL + "?room_id=23612045"

    def handler(request):
        if str(request.url) == ROOM_URL:
            return httpx.Response(200, text=f'<iframe src="{wrong_url}"></iframe><iframe src="{right_url}"></iframe>')
        task_html = TASK_HTML.replace("fixture-current-task", "wrong-room-task") if str(request.url) == wrong_url else TASK_HTML
        return httpx.Response(200, text=task_html)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.selected_group.task_ids == ("fixture-current-task",)
    assert [str(request.url) for request in requests] == [ROOM_URL, right_url]


@pytest.mark.parametrize("requested_room, linked_room", [(1, 5440), (5440, 1)])
def test_confirmed_room_aliases_accept_each_others_activity(serve_pages, requested_room, linked_room):
    canonical_url = ACTIVITY_URL + f"?room_id={linked_room}"
    state = {
        "roomInitRes": {"data": {"room_id": 5440, "short_id": 1}},
        "roomInfoRes": {
            "data": {"room_info": {"room_id": 5440}, "activity_banner_info": {"url": canonical_url}}
        },
    }

    def handler(request):
        if str(request.url) == f"https://live.bilibili.com/{requested_room}":
            return httpx.Response(200, text="<script>window.__NEPTUNE_IS_MY_WAIFU__=" + json.dumps(state) + ";</script>")
        assert str(request.url) == canonical_url
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    service = TaskDiscoveryService(
        browser_provider=lambda _preferred: (), room_status_fetcher=lambda *_args: 1
    )
    result = service.discover(requested_room)

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert len(requests) == 2


def test_public_task_page_can_retry_without_rejected_login_cookie(serve_pages, caplog):
    def handler(request):
        if request.headers.get("Cookie"):
            return httpx.Response(403)
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser(cookie="SESSDATA=fixture-private-session")

    assert result.status == DiscoveryStatus.SUCCESS
    assert len(requests) == 2
    assert "Cookie" in requests[0].headers
    assert "Cookie" not in requests[1].headers
    assert "fixture-private-session" not in caplog.text


@pytest.mark.parametrize("statuses", [(503, 403), (403, 503)])
def test_anonymous_and_transient_recovery_have_separate_retry_limits(serve_pages, statuses):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts <= len(statuses):
            return httpx.Response(statuses[attempts - 1])
        assert "Cookie" not in request.headers
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser(cookie="SESSDATA=fixture")

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert len(requests) == 3
    assert "Cookie" not in requests[-1].headers


def test_browser_fallback_runs_only_after_linked_pages_are_exhausted(serve_pages):
    events = []

    def handler(request):
        events.append(str(request.url))
        if str(request.url) == ROOM_URL:
            return httpx.Response(200, text=f'<iframe src="{ACTIVITY_URL}"></iframe>')
        return httpx.Response(200, text="<html>No published tasks</html>")

    serve_pages(handler)

    class RenderedDriver:
        page_source = TASK_HTML
        closed = False

        def get(self, _url):
            pass

        def quit(self):
            self.closed = True

    driver = RenderedDriver()

    def start_browser(_browser, _headless):
        events.append("browser")
        return driver

    service = TaskDiscoveryService(
        driver_factory=start_browser,
        browser_provider=lambda _preferred: ("edge",),
        room_status_fetcher=lambda *_args: 1,
    )
    result = service.discover(23612045)

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "edge"
    assert events == [ROOM_URL, ACTIVITY_URL, "browser"]
    assert driver.closed


def test_activity_link_cycles_and_many_links_have_a_page_limit(serve_pages):
    def handler(_request):
        links = [ROOM_URL, ACTIVITY_URL] + [
            f"https://www.bilibili.com/blackboard/era/task-{index}.html" for index in range(10)
        ]
        return httpx.Response(200, text="".join(f'<iframe src="{url}"></iframe>' for url in links))

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.status == DiscoveryStatus.NO_BROWSER
    assert len(requests) == 3
    assert len({str(request.url) for request in requests}) == 3


def test_room_redirect_does_not_use_up_the_linked_page_budget(serve_pages):
    landing_url = "https://www.bilibili.com/blackboard/era/fixture-room.html"
    next_url = "https://www.bilibili.com/blackboard/era/fixture-next.html"

    def handler(request):
        url = str(request.url)
        if url == ROOM_URL:
            return httpx.Response(302, headers={"Location": landing_url})
        if url == landing_url:
            return httpx.Response(200, text=f'<iframe src="{ACTIVITY_URL}"></iframe>')
        if url == ACTIVITY_URL:
            return httpx.Response(200, text=f'<iframe src="{next_url}"></iframe>')
        assert url == next_url
        return httpx.Response(200, text=TASK_HTML)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.browser == "direct"
    assert [str(request.url) for request in requests] == [ROOM_URL, landing_url, ACTIVITY_URL, next_url]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/blackboard/era/task.html",
        "https://www.bilibili.com.example.invalid/blackboard/era/task.html",
        "https://www.bilibili.com:9443/blackboard/era/task.html",
        "https://user:password@www.bilibili.com/blackboard/era/task.html",
    ],
)
def test_untrusted_activity_links_are_not_requested(serve_pages, url):
    requests = serve_pages(
        lambda _request: httpx.Response(200, text=f'<iframe src="{url}"></iframe>')
    )

    result = discover_without_browser(cookie="SESSDATA=fixture")

    assert result.status == DiscoveryStatus.NO_BROWSER
    assert [str(request.url) for request in requests] == [ROOM_URL]


def test_external_redirect_is_not_followed_or_sent_login_cookies(serve_pages):
    requests = serve_pages(
        lambda _request: httpx.Response(
            302, headers={"Location": "https://example.invalid/blackboard/era/task.html"}
        )
    )

    result = discover_without_browser(cookie="SESSDATA=fixture")

    assert result.status == DiscoveryStatus.NO_BROWSER
    assert [str(request.url) for request in requests] == [ROOM_URL]


def test_activity_redirect_to_another_room_is_not_followed(serve_pages):
    current_url = ACTIVITY_URL + "?room=23612045"
    wrong_url = ACTIVITY_URL + "?room=999"

    def handler(request):
        url = str(request.url)
        if url == ROOM_URL:
            return httpx.Response(200, text=f'<iframe src="{current_url}"></iframe>')
        if url == current_url:
            return httpx.Response(302, headers={"Location": wrong_url})
        return httpx.Response(200, text=TASK_HTML.replace("fixture-current-task", "wrong-room-task"))

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert not result.succeeded
    assert [str(request.url) for request in requests] == [ROOM_URL, current_url]


def test_retries_stop_when_direct_request_time_budget_is_used(serve_pages, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def handler(_request):
        now[0] = 10.0
        return httpx.Response(503)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert not result.succeeded
    assert len(requests) == 1


@pytest.mark.parametrize("slow_part", ["headers", "body"])
def test_delayed_success_cannot_outlive_the_direct_request_deadline(
    serve_pages, monkeypatch, slow_part
):
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    class SlowStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            data = TASK_HTML.encode()
            for start in range(0, len(data), 40):
                now[0] += 2.0
                yield data[start : start + 40]

        def close(self):
            self.closed = True

    stream = SlowStream()

    def handler(_request):
        if slow_part == "headers":
            now[0] = 10.0
            return httpx.Response(200, text=TASK_HTML)
        return httpx.Response(200, stream=stream)

    requests = serve_pages(handler)
    result = discover_without_browser()

    assert not result.succeeded
    assert len(requests) == 1
    if slow_part == "body":
        assert now[0] == 6.0
        assert stream.closed


def test_not_found_response_is_not_retried(serve_pages):
    requests = serve_pages(lambda _request: httpx.Response(404))

    result = discover_without_browser()

    assert not result.succeeded
    assert len(requests) == 1
