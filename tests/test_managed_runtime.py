import asyncio
import threading
import time

from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner import miner as miner_module


class FakeClient:
    async def get_self_info(self):
        return 1, "tester"

    async def close(self):
        return None


class FakeMonitor:
    def __init__(self, **_kwargs) -> None:
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        await self.stop_event.wait()

    async def stop(self) -> None:
        self.stop_event.set()

    def request_refresh(self) -> None:
        return None


class FakeWorker:
    loop_ids: set[int] = set()
    started = 0

    def __init__(self, *, stop_event, **_kwargs) -> None:
        self.stop_event = stop_event

    async def run_forever(self) -> None:
        type(self).loop_ids.add(id(asyncio.get_running_loop()))
        type(self).started += 1
        await self.stop_event.wait()

    async def stop(self) -> None:
        self.stop_event.set()


def test_all_sessions_share_one_event_loop(monkeypatch) -> None:
    FakeWorker.loop_ids.clear()
    FakeWorker.started = 0
    monkeypatch.setattr(miner_module, "BilibiliClient", lambda _cookie: FakeClient())
    monkeypatch.setattr(miner_module, "AccountTaskMonitor", FakeMonitor)
    monkeypatch.setattr(miner_module, "X25KnWorker", FakeWorker)
    miner = miner_module.BilibiliWatchTimeMiner(
        MinerConfig("cookie", [1], thread_count=3)
    )
    thread = threading.Thread(target=miner.run)
    thread.start()
    deadline = time.monotonic() + 3
    while FakeWorker.started < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    miner.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert FakeWorker.started == 3
    assert len(FakeWorker.loop_ids) == 1


def test_cookie_change_is_rejected_while_running() -> None:
    miner = miner_module.BilibiliWatchTimeMiner(MinerConfig("old", [1]))
    miner._running = True
    try:
        miner.update_cookie("new")
    except RuntimeError as exc:
        assert "先停止" in str(exc)
    else:
        raise AssertionError("running cookie update must fail")


def test_runtime_can_resize_managed_sessions(monkeypatch) -> None:
    FakeWorker.loop_ids.clear()
    FakeWorker.started = 0
    monkeypatch.setattr(
        miner_module, "BilibiliClient", lambda _cookie: FakeClient()
    )
    monkeypatch.setattr(miner_module, "AccountTaskMonitor", FakeMonitor)
    monkeypatch.setattr(miner_module, "X25KnWorker", FakeWorker)
    miner = miner_module.BilibiliWatchTimeMiner(
        MinerConfig("cookie", [1], thread_count=3)
    )
    thread = threading.Thread(target=miner.run)
    thread.start()
    deadline = time.monotonic() + 3
    while FakeWorker.started < 3 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert miner.set_target_sessions_per_room(2)
    deadline = time.monotonic() + 3
    while miner.health.target_sessions != 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert miner.health.target_sessions == 2

    assert miner.force_fixed_sessions_per_room(4)
    deadline = time.monotonic() + 3
    while FakeWorker.started < 5 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert miner.health.concurrency_mode == "fixed"
    assert miner.health.concurrency_phase == "fixed"
    assert "手动加速" in miner.health.concurrency_detail

    miner.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert FakeWorker.started == 5


def test_automatic_runtime_uses_configured_32_session_catchup(
    monkeypatch,
) -> None:
    FakeWorker.loop_ids.clear()
    FakeWorker.started = 0
    monkeypatch.setattr(
        miner_module,
        "BilibiliClient",
        lambda _cookie: FakeClient(),
    )
    monkeypatch.setattr(miner_module, "AccountTaskMonitor", FakeMonitor)
    monkeypatch.setattr(miner_module, "X25KnWorker", FakeWorker)
    miner = miner_module.BilibiliWatchTimeMiner(
        MinerConfig(
            "cookie",
            [1],
            thread_count=32,
            concurrency_mode="automatic",
        )
    )
    thread = threading.Thread(target=miner.run)
    thread.start()
    deadline = time.monotonic() + 3
    while miner.health.target_sessions != 32 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert miner.health.target_sessions == 32
    assert "32" in miner.health.concurrency_detail

    miner.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()


def test_guarded_automatic_runtime_still_starts_with_two_sessions(
    monkeypatch,
) -> None:
    FakeWorker.loop_ids.clear()
    FakeWorker.started = 0
    monkeypatch.setattr(
        miner_module,
        "BilibiliClient",
        lambda _cookie: FakeClient(),
    )
    monkeypatch.setattr(miner_module, "AccountTaskMonitor", FakeMonitor)
    monkeypatch.setattr(miner_module, "X25KnWorker", FakeWorker)
    miner = miner_module.BilibiliWatchTimeMiner(
        MinerConfig(
            "cookie",
            [1],
            thread_count=32,
            concurrency_mode="automatic",
            automatic_start_in_steady_mode=True,
        )
    )
    thread = threading.Thread(target=miner.run)
    thread.start()
    deadline = time.monotonic() + 3
    while miner.health.target_sessions != 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert miner.health.target_sessions == 2
    assert "2" in miner.health.concurrency_detail

    miner.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()


def test_runtime_failure_is_preserved_in_health(monkeypatch) -> None:
    class FailingClient(FakeClient):
        async def get_self_info(self):
            raise RuntimeError("probe failed")

    monkeypatch.setattr(miner_module, "BilibiliClient", lambda _cookie: FailingClient())
    miner = miner_module.BilibiliWatchTimeMiner(MinerConfig("cookie", [1]))

    try:
        miner.run()
    except RuntimeError as exc:
        assert str(exc) == "probe failed"
    else:
        raise AssertionError("runtime failure must propagate")

    assert miner.health.state.value == "error"
    assert miner.health.last_error == "probe failed"
