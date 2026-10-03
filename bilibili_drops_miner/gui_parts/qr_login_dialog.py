from __future__ import annotations

import threading
import time
from collections.abc import Callable

import qrcode
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCloseEvent, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from bilibili_drops_miner.qr_login import (
    BilibiliQrLoginService,
    QrLoginPollResult,
    QrLoginSession,
    QrLoginState,
)


def render_qr_pixmap(data: str, *, target_size: int = 280) -> QPixmap:
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    code.add_data(data)
    code.make(fit=True)
    matrix = code.get_matrix()
    module_count = len(matrix)
    scale = max(1, target_size // module_count)
    image_size = module_count * scale
    image = QImage(image_size, image_size, QImage.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, enabled in enumerate(row):
            if enabled:
                painter.drawRect(x * scale, y * scale, scale, scale)
    painter.end()
    return QPixmap.fromImage(image)


class QrLoginDialog(QDialog):
    session_ready = Signal(object)
    request_failed = Signal(str)
    poll_ready = Signal(object)

    def __init__(
        self,
        parent,
        *,
        service: BilibiliQrLoginService | None = None,
        on_success: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._service = service or BilibiliQrLoginService()
        self._on_success = on_success
        self._session: QrLoginSession | None = None
        self._poll_inflight = False
        self._closed = threading.Event()
        self._started_at = time.monotonic()

        self.setWindowTitle("扫码登录 Bilibili")
        self.setModal(True)
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel("使用 Bilibili App 扫码登录")
        title.setStyleSheet("font-size:17px;font-weight:700;color:#f3f4f6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("二维码只用于本次登录，成功后会自动关闭")
        subtitle.setStyleSheet("color:#aeb6c5;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        self.qr_label = QLabel("正在获取二维码…")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet(
            "background:#ffffff;color:#4b5563;border-radius:12px;padding:10px;"
        )
        layout.addWidget(self.qr_label, alignment=Qt.AlignCenter)

        self.status_label = QLabel("正在连接 Bilibili 登录服务")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#bfdbfe;font-weight:600;")
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton("取消")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._poll_once)
        self.session_ready.connect(self._on_session_ready)
        self.request_failed.connect(self._on_request_failed)
        self.poll_ready.connect(self._on_poll_ready)
        self.finished.connect(self._on_finished)

        threading.Thread(
            target=self._create_session,
            daemon=True,
            name="bili-qr-create",
        ).start()

    def _create_session(self) -> None:
        try:
            session = self._service.create_session()
        except Exception as exc:
            if not self._closed.is_set():
                self.request_failed.emit(str(exc) or type(exc).__name__)
            return
        if not self._closed.is_set():
            self.session_ready.emit(session)

    def _on_session_ready(self, session: QrLoginSession) -> None:
        if self._closed.is_set():
            return
        self._session = session
        pixmap = render_qr_pixmap(session.url)
        self.qr_label.setPixmap(pixmap)
        self.qr_label.setMinimumSize(pixmap.size())
        self.status_label.setText("等待手机扫描二维码")
        self._timer.start()
        self._poll_once()

    def _poll_once(self) -> None:
        if self._session is None or self._poll_inflight or self._closed.is_set():
            return
        if time.monotonic() - self._started_at > 180:
            self._timer.stop()
            self.status_label.setText("二维码已过期，请关闭后重新登录")
            return
        self._poll_inflight = True
        threading.Thread(
            target=self._poll,
            daemon=True,
            name="bili-qr-poll",
        ).start()

    def _poll(self) -> None:
        try:
            result = self._service.poll(self._session)  # type: ignore[arg-type]
        except Exception as exc:
            result = QrLoginPollResult(
                QrLoginState.ERROR,
                str(exc) or "二维码状态查询失败",
            )
        if not self._closed.is_set():
            self.poll_ready.emit(result)

    def _on_poll_ready(self, result: QrLoginPollResult) -> None:
        if self._closed.is_set():
            return
        self._poll_inflight = False
        self.status_label.setText(result.message)
        if result.state == QrLoginState.EXPIRED:
            self._timer.stop()
        elif result.state == QrLoginState.SUCCESS:
            self._timer.stop()
            self.accept()
            self._on_success(result.cookie)

    def _on_request_failed(self, message: str) -> None:
        if self._closed.is_set():
            return
        self.status_label.setText(message)
        self.qr_label.setText("二维码获取失败")

    def _on_finished(self, _result: int) -> None:
        self._closed.set()
        self._timer.stop()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closed.set()
        self._timer.stop()
        super().closeEvent(event)
