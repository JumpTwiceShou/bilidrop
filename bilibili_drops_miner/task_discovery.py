from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime

import httpx

from bilibili_drops_miner.domain import (
    DiscoveredTaskGroup,
    DiscoveryStatus,
    TaskDiscoveryResult,
)
from bilibili_drops_miner.gui_parts.browser_utils import browser_label, browser_try_order
from bilibili_drops_miner.utils import extract_bili_live_task_groups, parse_cookie

LOGGER = logging.getLogger(__name__)

FastPath = Callable[[int], Iterable[DiscoveredTaskGroup] | None]
DriverFactory = Callable[[str, bool], object]
DirectFetcher = Callable[[int, str, float], str]
RoomStatusFetcher = Callable[[int, float], int | None]


class TaskDiscoveryService:
    """Discover a room's rendered task groups without touching Qt widgets."""

    def __init__(
        self,
        *,
        cache_ttl_seconds: float = 300.0,
        fast_path: FastPath | None = None,
        driver_factory: DriverFactory | None = None,
        direct_fetcher: DirectFetcher | None = None,
        room_status_fetcher: RoomStatusFetcher | None = None,
        browser_provider: Callable[[str | None], tuple[str, ...]] = browser_try_order,
    ) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self.fast_path = fast_path
        self.driver_factory = driver_factory or self._create_driver
        self.direct_fetcher = direct_fetcher or self._fetch_room_html
        self.room_status_fetcher = room_status_fetcher or self._fetch_room_live_status
        self.browser_provider = browser_provider
        self._cache: dict[int, tuple[float, TaskDiscoveryResult]] = {}
        self._cache_lock = threading.Lock()

    def invalidate(self, room_id: int | None = None) -> None:
        with self._cache_lock:
            if room_id is None:
                self._cache.clear()
            else:
                self._cache.pop(room_id, None)

    def discover(
        self,
        room_id: int,
        *,
        browser_preference: str | None = None,
        timeout_seconds: float = 30.0,
        headless: bool = True,
        cookie: str = "",
        cancel_event: threading.Event | None = None,
        force_refresh: bool = False,
    ) -> TaskDiscoveryResult:
        if room_id <= 0:
            return TaskDiscoveryResult(
                room_id=room_id,
                status=DiscoveryStatus.ERROR,
                message="房间号必须大于 0",
            )
        cancel_event = cancel_event or threading.Event()
        if cancel_event.is_set():
            return self._cancelled(room_id)

        if not force_refresh:
            cached = self._get_cached(room_id)
            if cached is not None:
                return cached

        deadline = time.monotonic() + max(2.0, timeout_seconds)

        if self.fast_path is not None:
            try:
                groups = tuple(self.fast_path(room_id) or ())
                if groups:
                    return self._remember(self._result_from_groups(room_id, groups))
            except Exception:
                LOGGER.debug("任务发现快速路径失败 room=%s", room_id, exc_info=True)

        try:
            page_html = self.direct_fetcher(
                room_id,
                cookie,
                max(2.0, min(6.0, timeout_seconds / 4)),
            )
            if cancel_event.is_set():
                return self._cancelled(room_id)
            groups = self._parse_groups(page_html)
            if groups:
                result = self._result_from_groups(room_id, groups, browser="direct")
                LOGGER.info("无需启动浏览器，已从房间任务数据中完成识别")
                return self._remember(result)
        except Exception as exc:
            LOGGER.info("直接任务数据识别未命中（%s），继续后台兜底", type(exc).__name__)

        try:
            live_status = self.room_status_fetcher(
                room_id,
                max(1.0, min(3.0, timeout_seconds / 6)),
            )
            if cancel_event.is_set():
                return self._cancelled(room_id)
            if live_status == 0:
                return TaskDiscoveryResult(
                    room_id=room_id,
                    status=DiscoveryStatus.OFFLINE,
                    message="房间当前未开播，且页面未发现活动任务；仍可直接开始挂机",
                )
        except Exception as exc:
            LOGGER.info("直播状态识别未命中（%s），继续后台兜底", type(exc).__name__)

        browsers = self.browser_provider(browser_preference)
        if not browsers:
            return TaskDiscoveryResult(
                room_id=room_id,
                status=DiscoveryStatus.NO_BROWSER,
                message="未检测到 Chrome 或 Edge",
            )

        attempts: list[str] = []
        timeout_seen = False
        last_browser = ""
        for index, browser in enumerate(browsers):
            remaining_total = deadline - time.monotonic()
            if remaining_total <= 0:
                break
            browsers_left = len(browsers) - index
            browser_deadline = min(
                deadline,
                time.monotonic() + max(1.0, remaining_total / browsers_left),
            )
            driver = None
            last_browser = browser
            try:
                if cancel_event.is_set():
                    return self._cancelled(room_id)
                driver = self.driver_factory(browser, headless)
                remaining = max(1, min(10, int(browser_deadline - time.monotonic())))
                if hasattr(driver, "set_page_load_timeout"):
                    driver.set_page_load_timeout(remaining)
                if hasattr(driver, "set_script_timeout"):
                    driver.set_script_timeout(min(5, remaining))
                self._inject_cookie(driver, cookie)
                driver.get(f"https://live.bilibili.com/{room_id}")

                while time.monotonic() < browser_deadline:
                    if cancel_event.is_set():
                        return self._cancelled(room_id)
                    html = str(getattr(driver, "page_source", "") or "")
                    groups = self._parse_groups(html)
                    if groups:
                        result = self._result_from_groups(
                            room_id, groups, browser=browser
                        )
                        return self._remember(result)
                    time.sleep(0.5)
                timeout_seen = True
                summary = f"{browser_label(browser)} 等待任务面板超时"
                attempts.append(summary)
                LOGGER.warning("后台任务发现未完成: %s", summary)
            except Exception as exc:
                summary, timed_out = self._summarize_browser_error(browser, exc)
                timeout_seen = timeout_seen or timed_out
                attempts.append(summary)
                LOGGER.warning("后台任务发现失败: %s", summary)
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        if not attempts:
            attempts.append("任务识别总等待时间已用完")
            timeout_seen = True
        status = DiscoveryStatus.TIMEOUT if timeout_seen else DiscoveryStatus.NO_TASKS
        return TaskDiscoveryResult(
            room_id=room_id,
            status=status,
            browser=last_browser,
            message="；".join(attempts) + "。可改用可见浏览器继续识别。",
        )

    @staticmethod
    def _inject_cookie(driver: object, cookie: str) -> None:
        cookie_map = parse_cookie(cookie)
        if not cookie_map:
            return
        execute_cdp = getattr(driver, "execute_cdp_cmd", None)
        if not callable(execute_cdp):
            raise RuntimeError("临时浏览器不支持安全写入登录 Cookie")
        try:
            execute_cdp("Network.enable", {})
            for name, value in cookie_map.items():
                if not name or not value:
                    continue
                result = execute_cdp(
                    "Network.setCookie",
                    {
                        "name": name,
                        "value": value,
                        "domain": ".bilibili.com",
                        "path": "/",
                        "secure": True,
                    },
                )
                if isinstance(result, dict) and result.get("success") is False:
                    raise RuntimeError("Cookie 写入被浏览器拒绝")
        except Exception:
            raise RuntimeError("无法向临时浏览器写入登录 Cookie") from None

    @staticmethod
    def _summarize_browser_error(browser: str, exc: Exception) -> tuple[str, bool]:
        label = browser_label(browser)
        raw = str(exc).lower()
        if "timed out receiving message from renderer" in raw:
            return f"{label} 页面渲染超时", True
        if "timeout" in raw or "timed out" in raw:
            return f"{label} 页面加载超时", True
        if "cookie" in raw:
            return f"{label} 无法载入当前登录状态", False
        if "session not created" in raw:
            return f"{label} 无法创建浏览器会话", False
        return f"{label} 启动或加载失败（{type(exc).__name__}）", False

    @staticmethod
    def _parse_groups(page_html: str) -> tuple[DiscoveredTaskGroup, ...]:
        return tuple(
            DiscoveredTaskGroup(
                label=str(group.get("label") or "任务组"),
                task_ids=tuple(str(item) for item in group.get("task_ids") or ()),
                active=bool(group.get("active")),
                start_at=TaskDiscoveryService._parse_datetime(
                    group.get("start_at")
                ),
                end_at=TaskDiscoveryService._parse_datetime(
                    group.get("end_at")
                ),
            )
            for group in extract_bili_live_task_groups(page_html)
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def get_room_live_status(
        self,
        room_id: int,
        *,
        timeout_seconds: float = 5.0,
    ) -> int | None:
        return self.room_status_fetcher(room_id, timeout_seconds)

    @staticmethod
    def _result_from_groups(
        room_id: int,
        groups: Iterable[DiscoveredTaskGroup],
        *,
        browser: str = "",
    ) -> TaskDiscoveryResult:
        group_tuple = tuple(groups)
        active = [group for group in group_tuple if group.active]
        if len(active) == 1:
            selected = active[0]
        elif len(group_tuple) == 1:
            selected = group_tuple[0]
        else:
            selected = None
        status = DiscoveryStatus.SUCCESS if selected else DiscoveryStatus.AMBIGUOUS
        return TaskDiscoveryResult(
            room_id=room_id,
            status=status,
            groups=group_tuple,
            selected_group=selected,
            browser=browser,
            message=(
                f"已识别 {len(selected.task_ids)} 个任务"
                if selected is not None
                else f"检测到 {len(group_tuple)} 个任务组，需要选择"
            ),
        )

    def _get_cached(self, room_id: int) -> TaskDiscoveryResult | None:
        with self._cache_lock:
            cached = self._cache.get(room_id)
            if cached is None:
                return None
            stored_at, result = cached
            if time.monotonic() - stored_at > self.cache_ttl_seconds:
                self._cache.pop(room_id, None)
                return None
            return result

    def _remember(self, result: TaskDiscoveryResult) -> TaskDiscoveryResult:
        with self._cache_lock:
            self._cache[result.room_id] = (time.monotonic(), result)
        return result

    @staticmethod
    def _cancelled(room_id: int) -> TaskDiscoveryResult:
        return TaskDiscoveryResult(
            room_id=room_id,
            status=DiscoveryStatus.CANCELLED,
            message="任务识别已取消",
        )

    @staticmethod
    def _create_driver(browser: str, headless: bool):
        from selenium import webdriver

        def configure(options) -> None:
            options.page_load_strategy = "none"
            options.add_argument("--window-size=1440,1000")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            if headless:
                options.add_argument("--headless=new")
                options.add_argument("--window-position=-32000,-32000")

        def configure_service(service) -> None:
            if sys.platform == "win32":
                service.creation_flags = subprocess.CREATE_NO_WINDOW

        if browser == "edge":
            options = webdriver.EdgeOptions()
            configure(options)
            service = webdriver.EdgeService(log_output=subprocess.DEVNULL)
            configure_service(service)
            return webdriver.Edge(options=options, service=service)

        options = webdriver.ChromeOptions()
        configure(options)
        options.add_argument("--remote-allow-origins=*")
        service = webdriver.ChromeService(log_output=subprocess.DEVNULL)
        configure_service(service)
        return webdriver.Chrome(options=options, service=service)

    @staticmethod
    def _fetch_room_html(room_id: int, cookie: str, timeout_seconds: float) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        if cookie:
            headers["Cookie"] = cookie
        response = httpx.get(
            f"https://live.bilibili.com/{room_id}",
            headers=headers,
            follow_redirects=True,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return response.content.decode("utf-8", errors="replace")

    @staticmethod
    def _fetch_room_live_status(room_id: int, timeout_seconds: float) -> int | None:
        response = httpx.get(
            "https://api.live.bilibili.com/room/v1/Room/get_info",
            params={"room_id": room_id},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Referer": f"https://live.bilibili.com/{room_id}",
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0:
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        value = data.get("live_status")
        return int(value) if value is not None else None
