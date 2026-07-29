from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

from bilibili_drops_miner.client import BilibiliClient, LiveTraceSession
from bilibili_drops_miner.config import MinerConfig

LOGGER = logging.getLogger(__name__)


class X25KnWorker:
    def __init__(
        self,
        client: BilibiliClient,
        config: MinerConfig,
        room_id: int,
        session_id: str = "",
        stop_event: asyncio.Event | None = None,
        on_heartbeat: Callable[[int], None] | None = None,
        on_reconnect: Callable[[int, str], None] | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.room_id = room_id
        self.session_id = session_id
        self._stop_event = stop_event or asyncio.Event()
        self._on_heartbeat = on_heartbeat
        self._on_reconnect = on_reconnect

    @property
    def _ctx(self) -> str:
        if self.session_id:
            return f"room={self.room_id} session={self.session_id}"
        return f"room={self.room_id}"

    def _log_info(self, message: str, *args: Any) -> None:
        LOGGER.info(message, *args)

    def _log_warning(
        self, message: str, *args: Any
    ) -> None:
        LOGGER.warning(message, *args)

    async def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log_warning(
                    "直播间 %s x25Kn 运行异常: %s",
                    self.room_id,
                    exc,
                )
            if not self._stop_event.is_set():
                delay = self.config.reconnect_delay_seconds * random.uniform(0.85, 1.25)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    pass
                if self._stop_event.is_set():
                    return

    async def _run_once(self) -> None:
        trace_heartbeat_task = asyncio.create_task(self._trace_heartbeat_loop())
        stop_wait_task = asyncio.create_task(self._stop_event.wait())

        tasks: list[asyncio.Task[Any]] = [trace_heartbeat_task, stop_wait_task]

        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            if stop_wait_task in done:
                return

            for task in done:
                if task is stop_wait_task:
                    continue
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is not None:
                    raise exc

            raise RuntimeError("x25Kn 子任务意外退出")

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _trace_heartbeat_loop(self) -> None:
        session: LiveTraceSession | None = None
        wait_seconds = 60
        while not self._stop_event.is_set():
            if not self.config.enable_web_heartbeat:
                session = None
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5)
                    return
                except asyncio.TimeoutError:
                    continue
            try:
                if session is None:
                    await self.client.room_entry_action(self.room_id)
                    session = await self.client.live_trace_enter(self.room_id)
                    wait_seconds = max(5, int(session.heartbeat_interval))
                    self._log_info(
                        "直播间 %s 观看时长上报已启动",
                        self.room_id,
                    )
                    self._heartbeat_succeeded()
                else:
                    session = await self.client.live_trace_heartbeat(session)
                    wait_seconds = max(5, int(session.heartbeat_interval))
                    LOGGER.debug(
                        "%s x25Kn heartbeat success seq=%s ets=%s interval=%s",
                        self._ctx,
                        session.seq_id,
                        session.ets,
                        wait_seconds,
                    )
                    self._heartbeat_succeeded()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                detail = str(exc).strip() or repr(exc)
                self._log_warning(
                    "直播间 %s 观看时长上报失败[%s]: %s",
                    self.room_id,
                    type(exc).__name__,
                    detail,
                )
                if self._on_reconnect is not None:
                    self._on_reconnect(self.room_id, detail)
                session = None
                wait_seconds = max(5, self.config.reconnect_delay_seconds)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
                return
            except asyncio.TimeoutError:
                pass

    def _heartbeat_succeeded(self) -> None:
        if self._on_heartbeat is not None:
            self._on_heartbeat(self.room_id)
