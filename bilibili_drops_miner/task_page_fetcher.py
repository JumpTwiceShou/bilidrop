from __future__ import annotations

import logging
import time
from collections import deque
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx

from bilibili_drops_miner.utils import (
    _extract_json_object_for_variable,
    extract_bili_live_task_groups,
    parse_cookie,
)

LOGGER = logging.getLogger(__name__)
MAX_PAGES = 3
MAX_REQUESTS = 6
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _trusted_url(value: str, base_url: str) -> str | None:
    try:
        parts = urlsplit(urljoin(base_url, value.strip()))
        host = parts.hostname or ""
        if (
            parts.scheme not in {"http", "https"}
            or not (host == "bilibili.com" or host.endswith(".bilibili.com"))
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 443}
        ):
            return None
        return urlunsplit(("https", host, parts.path, parts.query, ""))
    except ValueError:
        return None


class _IframeLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "iframe":
            self.links.extend(
                value for key, value in attrs if key in {"src", "data-src"} and value
            )


def _room_identifier(value) -> int | None:
    try:
        room_id = int(value)
        return room_id if room_id > 0 else None
    except (ValueError, TypeError):
        return None


def _matches_room(url: str, room_ids: set[int]) -> bool:
    linked_room_ids = {
        room_id
        for key, value in parse_qsl(urlsplit(url).query)
        if key.lower() in {"room", "room_id", "roomid", "live_room_id"}
        and (room_id := _room_identifier(value)) is not None
    }
    return not (linked_room_ids - room_ids)


def _add_room_aliases(state: dict, room_ids: set[int]) -> None:
    init = state.get("roomInitRes")
    if isinstance(init, dict) and isinstance(init.get("data"), dict):
        canonical_id = _room_identifier(init["data"].get("room_id"))
        short_id = _room_identifier(init["data"].get("short_id"))
        if canonical_id is not None and (
            canonical_id in room_ids or short_id in room_ids
        ):
            room_ids.add(canonical_id)
            if short_id is not None:
                room_ids.add(short_id)


def extract_room_aliases(page_html: str, room_id: int) -> set[int]:
    """Accept a short/canonical alias only when room initialization maps it."""
    room_ids = {room_id}
    try:
        state = _extract_json_object_for_variable(
            page_html, "window.__NEPTUNE_IS_MY_WAIFU__"
        )
    except ValueError:
        return room_ids
    _add_room_aliases(state, room_ids)
    return room_ids


def _activity_links(page_html: str, base_url: str, room_ids: set[int]) -> list[str]:
    candidates: list[str] = []

    def walk(value, activity_context: bool = False) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, activity_context)
        elif isinstance(value, dict):
            for room_info in (value, value.get("room_info"), value.get("roomInfo")):
                if isinstance(room_info, dict):
                    reported_id = _room_identifier(
                        room_info.get("room_id")
                        or room_info.get("roomid")
                        or room_info.get("roomId")
                    )
                    if reported_id is not None and reported_id not in room_ids:
                        return
            for key, child in value.items():
                key = key.lower()
                if key.startswith(
                    ("ad_", "advert", "recommend", "relatedroom", "related_room")
                ):
                    continue
                context = activity_context or key.startswith(
                    ("activity", "task", "widget")
                )
                if (
                    isinstance(child, str)
                    and context
                    and (
                        key in {"url", "href", "src", "link", "weburl"}
                        or key.endswith(("_url", "_link"))
                    )
                ):
                    candidates.append(child)
                else:
                    walk(child, context)

    for variable in ("window.__NEPTUNE_IS_MY_WAIFU__", "window.__initialState"):
        try:
            state = _extract_json_object_for_variable(page_html, variable)
        except ValueError:
            continue
        if variable == "window.__NEPTUNE_IS_MY_WAIFU__":
            _add_room_aliases(state, room_ids)
            info = state.get("roomInfoRes")
            if not isinstance(info, dict) or not isinstance(info.get("data"), dict):
                continue
            state = info["data"]
        walk(state)
    parser = _IframeLinks()
    parser.feed(page_html)
    candidates.extend(parser.links)

    links: list[str] = []
    for candidate in candidates:
        url = _trusted_url(candidate, base_url)
        if url and urlsplit(url).path.startswith(
            ("/blackboard/", "/activity/", "/p/html/")
        ):
            if not _matches_room(url, room_ids):
                continue
            if url not in links:
                links.append(url)
    return links


def fetch_task_page(room_id: int, cookie: str, timeout_seconds: float) -> str:
    """Read published task data, including linked activity pages, before rendering.

    A session reuses connections, retries a transient failure once per URL, and
    stays within a shared request/time budget. Cookies are scoped to Bilibili;
    redirects are checked before a request is sent.
    """
    room_url = f"https://live.bilibili.com/{room_id}"
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    request_count = 0
    room_ids = {room_id}
    cookies = httpx.Cookies()
    for name, value in parse_cookie(cookie).items():
        cookies.set(name, value, domain=".bilibili.com", path="/")

    with httpx.Client(
        headers={
            "User-Agent": WEB_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        cookies=cookies,
        follow_redirects=False,
    ) as client:

        def get_page(url: str, referer: str) -> httpx.Response | None:
            nonlocal request_count
            retries = 0
            retried_anonymously = False
            redirects = {url}
            while request_count < MAX_REQUESTS:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                request_count += 1
                retry_delay = 0.15
                try:
                    with client.stream(
                        "GET",
                        url,
                        headers={"Referer": referer},
                        timeout=min(3.0, remaining),
                    ) as response:
                        if time.monotonic() >= deadline:
                            return None
                        if response.status_code == 200:
                            if response.is_stream_consumed:
                                return response
                            content = bytearray()
                            for chunk in response.iter_raw():
                                if time.monotonic() >= deadline:
                                    return None
                                content.extend(chunk)
                            if time.monotonic() >= deadline:
                                return None
                            return httpx.Response(
                                200,
                                headers=response.headers,
                                content=bytes(content),
                                request=response.request,
                            )
                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ) as exc:
                    LOGGER.info("直接任务页面请求暂未完成（%s）", type(exc).__name__)
                except httpx.HTTPError as exc:
                    LOGGER.info("直接任务页面请求失败（%s）", type(exc).__name__)
                    return None
                else:
                    if response.is_redirect:
                        target = _trusted_url(response.headers.get("Location", ""), url)
                        if (
                            target is None
                            or target in redirects
                            or not _matches_room(target, room_ids)
                        ):
                            return None
                        redirects.add(target)
                        url = target
                        retries = 0
                        continue
                    if (
                        response.status_code in {401, 403, 412}
                        and client.cookies
                        and not retried_anonymously
                    ):
                        # Published activity data can still be available anonymously.
                        client.cookies.clear()
                        retried_anonymously = True
                        continue
                    elif response.status_code not in RETRYABLE_STATUSES:
                        return None
                    elif response.status_code == 429:
                        try:
                            retry_delay = max(
                                retry_delay,
                                float(response.headers.get("Retry-After", "0")),
                            )
                        except ValueError:
                            return None
                    LOGGER.info(
                        "直接任务页面请求未完成（HTTP %s）", response.status_code
                    )
                if retries >= 1 or deadline - time.monotonic() <= retry_delay:
                    return None
                retries += 1
                time.sleep(retry_delay)
            return None

        pending = deque([(room_url, room_url)])
        visited: set[str] = set()
        page_count = 0
        while pending and page_count < MAX_PAGES and request_count < MAX_REQUESTS:
            url, referer = pending.popleft()
            if url in visited:
                continue
            visited.add(url)
            page_count += 1
            response = get_page(url, referer)
            if response is None:
                continue
            visited.add(str(response.url))
            page_html = response.content.decode("utf-8", errors="replace")
            groups = extract_bili_live_task_groups(page_html)
            if time.monotonic() >= deadline:
                break
            if groups:
                return page_html
            pending.extend(
                (link, str(response.url))
                for link in _activity_links(page_html, str(response.url), room_ids)
                if link not in visited
            )
    return ""
