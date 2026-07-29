from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def default_instance_name() -> str:
    identity = f"{os.environ.get('USERNAME', '')}:{os.path.expanduser('~')}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"bilidrop-desktop-{suffix}"


class SingleInstanceGuard(QObject):
    """Own one local IPC endpoint and ask the first process to show itself."""

    activation_requested = Signal()

    def __init__(self, name: str | None = None) -> None:
        super().__init__()
        self.name = name or default_instance_name()
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)

    def acquire(self, *, timeout_ms: int = 800) -> bool:
        if self._notify_existing(timeout_ms=timeout_ms):
            return False

        QLocalServer.removeServer(self.name)
        if self.server.listen(self.name):
            return True

        # A process may have won the startup race between the first connect and
        # listen. Notify it instead of creating a second application instance.
        if self._notify_existing(timeout_ms=timeout_ms):
            return False
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def _notify_existing(self, *, timeout_ms: int) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is not None:
                socket.readAll()
                socket.disconnectFromServer()
                socket.deleteLater()
        self.activation_requested.emit()
