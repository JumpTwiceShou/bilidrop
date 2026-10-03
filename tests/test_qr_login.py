import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtWidgets import QApplication

from bilibili_drops_miner.gui_parts.qr_login_dialog import QrLoginDialog, render_qr_pixmap
from bilibili_drops_miner.qr_login import (
    BilibiliQrLoginService,
    QrLoginState,
    QrLoginPollResult,
    QrLoginSession,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_qr_login_generate_and_pending_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generate"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "url": "https://example.invalid/qr",
                        "qrcode_key": "fixture-key",
                    },
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {"code": 86101}})

    service = BilibiliQrLoginService(transport=httpx.MockTransport(handler))
    session = service.create_session()
    result = service.poll(session)

    assert session.key == "fixture-key"
    assert result.state == QrLoginState.PENDING
    assert "等待" in result.message


def test_qr_login_extracts_cookie_from_success_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=[
                ("set-cookie", "SESSDATA=test-session; Path=/; Secure"),
                ("set-cookie", "bili_jct=test-csrf; Path=/; Secure"),
                ("set-cookie", "DedeUserID=123; Path=/; Secure"),
            ],
            json={"code": 0, "data": {"code": 0, "url": ""}},
        )

    service = BilibiliQrLoginService(transport=httpx.MockTransport(handler))
    result = service.poll(type("Session", (), {"key": "fixture-key"})())

    assert result.state == QrLoginState.SUCCESS
    assert "SESSDATA=test-session" in result.cookie
    assert "bili_jct=test-csrf" in result.cookie
    assert "DedeUserID=123" in result.cookie


def test_qr_login_url_fallback_preserves_encoded_cookie_values() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "code": 0,
                    "url": (
                        "https://passport.bilibili.com/callback?"
                        "SESSDATA=v%2Cx&bili_jct=csrf&DedeUserID=123"
                    ),
                },
            },
        )

    service = BilibiliQrLoginService(transport=httpx.MockTransport(handler))
    result = service.poll(type("Session", (), {"key": "fixture-key"})())

    assert result.state == QrLoginState.SUCCESS
    assert "SESSDATA=v%2Cx" in result.cookie


def test_qr_pixmap_is_rendered_without_pillow(app) -> None:
    pixmap = render_qr_pixmap("https://example.invalid/qr", target_size=240)

    assert not pixmap.isNull()
    assert 150 <= pixmap.width() <= 240
    assert pixmap.width() == pixmap.height()


def test_cancelled_qr_dialog_discards_queued_results(app, monkeypatch):
    monkeypatch.setattr(QrLoginDialog, "_create_session", lambda self: None)
    success = []
    dialog = QrLoginDialog(None, on_success=success.append)
    dialog._timer.start()
    dialog.reject()
    previous = dialog.status_label.text()
    dialog._on_poll_ready(QrLoginPollResult(QrLoginState.SUCCESS, "logged in", "synthetic-cookie"))
    dialog._on_request_failed("late failure")
    dialog._on_session_ready(QrLoginSession("https://example.invalid/qr", "fixture-key"))
    assert success == []
    assert dialog.status_label.text() == previous
    assert not dialog._timer.isActive()
    dialog.deleteLater()
