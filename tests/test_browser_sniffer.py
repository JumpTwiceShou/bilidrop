import threading
import io
import json
from types import SimpleNamespace

import pytest
from selenium import webdriver

from bilibili_drops_miner.gui_parts import browser_sniffer as module


@pytest.mark.parametrize(
    "cancel_at", ["before_start", "navigation", "navigation_error"]
)
def test_cancelled_sniffer_releases_driver_and_suppresses_errors(
    monkeypatch, cancel_at
):
    cancel = threading.Event()
    events = []
    errors = []

    class Server:
        server_address = ("127.0.0.1", 12345)

        def __init__(self, *args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            events.append("shutdown")

        def server_close(self):
            events.append("server_close")

    class Driver:
        def set_page_load_timeout(self, value):
            pass

        def get(self, url):
            events.append(url)
            cancel.set()
            if cancel_at == "navigation_error":
                raise RuntimeError("cancelled while navigating")

        def quit(self):
            events.append("quit")

    monkeypatch.setattr(module, "HTTPServer", Server)
    monkeypatch.setattr(module, "browser_try_order", lambda _: ("edge",))
    monkeypatch.setattr(module, "find_browser", lambda _: True)
    monkeypatch.setattr(module, "write_edge_extension", lambda *args, **kw: None)
    monkeypatch.setattr(webdriver, "Edge", lambda **kw: Driver())
    if cancel_at == "before_start":
        cancel.set()
    thread = module.start_browser_sniff(
        None,
        "test",
        on_error=lambda *args: errors.append(args),
        cancel_event=cancel,
        initial_url="https://live.bilibili.com/111",
        on_page_html=lambda *_: (_ for _ in ()).throw(AssertionError("stale callback")),
    )
    thread.join(3)
    assert not thread.is_alive()
    assert not errors
    if cancel_at == "before_start":
        assert events == []
    else:
        assert events == [
            "https://live.bilibili.com/111",
            "shutdown",
            "server_close",
            "quit",
        ]


def test_successful_html_is_not_overwritten_by_simultaneous_network_payload(
    monkeypatch,
):
    events = []
    handlers = []

    class Server:
        server_address = ("127.0.0.1", 12345)

        def __init__(self, address, handler):
            handlers.append(handler)

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    def send(payload):
        data = json.dumps(payload).encode()
        request = SimpleNamespace(
            headers={"Content-Length": str(len(data))},
            rfile=io.BytesIO(data),
            send_response=lambda *_: None,
            send_header=lambda *_: None,
            end_headers=lambda: None,
        )
        handlers[0].do_POST(request)

    class Driver:
        def set_page_load_timeout(self, value):
            pass

        def get(self, url):
            send(
                {
                    "type": "__bili_page__",
                    "url": "https://live.bilibili.com/111",
                    "html": "current dated page",
                }
            )
            send({"url": "https://api.bilibili.com/x/task/totalv2", "data": {}})

        def quit(self):
            events.append("quit")

    monkeypatch.setattr(module, "HTTPServer", Server)
    monkeypatch.setattr(module, "browser_try_order", lambda _: ("edge",))
    monkeypatch.setattr(module, "find_browser", lambda _: True)
    monkeypatch.setattr(module, "write_edge_extension", lambda *a, **kw: None)
    monkeypatch.setattr(webdriver, "Edge", lambda **kw: Driver())
    thread = module.start_browser_sniff(
        "/x/task/totalv2",
        "test",
        on_error=lambda *a: events.append("error"),
        on_page_html=lambda *a: events.append("html") or True,
        on_network_match=lambda *a: events.append("network"),
        finish_on_any=True,
    )
    thread.join(3)
    assert not thread.is_alive()
    assert events == ["html", "quit"]
