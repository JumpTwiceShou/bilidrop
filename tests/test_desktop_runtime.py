import os
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from bilibili_drops_miner.desktop_runtime import SingleInstanceGuard


def test_second_instance_notifies_first_instance() -> None:
    app = QApplication.instance() or QApplication([])
    name = f"bilidrop-test-{uuid.uuid4().hex}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)
    activated: list[bool] = []
    first.activation_requested.connect(lambda: activated.append(True))
    try:
        assert first.acquire(timeout_ms=200)
        assert not second.acquire(timeout_ms=200)

        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()

        assert activated == [True]
    finally:
        first.server.close()
        second.server.close()
