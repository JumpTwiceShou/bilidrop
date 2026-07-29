from bilibili_drops_miner import notifier as notifier_module


class FakeResponse:
    is_success = True
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_native_telegram_bot_notification(monkeypatch) -> None:
    request: dict = {}

    def fake_post(url, *, json, timeout):
        request.update(url=url, json=json, timeout=timeout)
        return FakeResponse({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(notifier_module.httpx, "post", fake_post)
    notifier = notifier_module.MultiPlatformNotifier(
        ["tgram://123456:TEST_TOKEN/-100123456"]
    )

    assert notifier.enabled
    assert notifier.notify("任务完成", "账号：测试账号")
    assert request == {
        "url": "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage",
        "json": {
            "chat_id": "-100123456",
            "text": "任务完成\n\n账号：测试账号",
        },
        "timeout": 10.0,
    }


def test_telegram_topic_and_failed_api_response(monkeypatch) -> None:
    request: dict = {}

    def fake_post(url, *, json, timeout):
        request.update(url=url, json=json, timeout=timeout)
        return FakeResponse({"ok": False, "description": "fixture failure"})

    monkeypatch.setattr(notifier_module.httpx, "post", fake_post)
    notifier = notifier_module.MultiPlatformNotifier(
        ["telegram://123456:TEST_TOKEN/-100123456?thread=88"]
    )

    assert not notifier.notify("标题", "正文")
    assert request["json"]["message_thread_id"] == 88
