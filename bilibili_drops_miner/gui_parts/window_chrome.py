from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget


APP_BACKGROUND_COLORREF = 0x00231D1A  # #1a1d23 in Win32 COLORREF order
APP_TEXT_COLORREF = 0x00EBE7E6  # #e6e7eb in Win32 COLORREF order


def bundled_resource_path(relative_path: str) -> Path:
    base = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])
    )
    return base / relative_path


def tray_icon(fallback: QIcon | None = None) -> QIcon:
    """Load the high-contrast tray-only icon without changing window branding."""

    for relative_path in (
        "assets/bilibili-tray.ico",
        "assets/bilibili-tray.png",
    ):
        icon_path = bundled_resource_path(relative_path)
        if not icon_path.is_file():
            continue
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    return fallback or QIcon()


def install_window_chrome(app: QApplication) -> None:
    icon_path = bundled_resource_path("assets/bilibili.png")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    if sys.platform != "win32":
        return
    event_filter = _WindowsChromeEventFilter(app)
    app.installEventFilter(event_filter)
    # Keep the Python wrapper alive for the lifetime of QApplication.
    app._bilidrop_window_chrome_filter = event_filter  # type: ignore[attr-defined]


class _WindowsChromeEventFilter(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if (
            event.type() == QEvent.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            apply_windows_dark_caption(watched)
        return super().eventFilter(watched, event)


def apply_windows_dark_caption(window: QWidget) -> bool:
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(window.winId())
        dwm = ctypes.WinDLL("dwmapi")
        setter = dwm.DwmSetWindowAttribute
        setter.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        setter.restype = ctypes.c_long

        dark_mode = ctypes.c_int(1)
        dark_result = setter(
            hwnd,
            20,  # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.byref(dark_mode),
            ctypes.sizeof(dark_mode),
        )
        if dark_result != 0:
            # Compatibility fallback used by older Windows 10 builds.
            setter(
                hwnd,
                19,
                ctypes.byref(dark_mode),
                ctypes.sizeof(dark_mode),
            )

        caption_color = ctypes.c_uint32(APP_BACKGROUND_COLORREF)
        text_color = ctypes.c_uint32(APP_TEXT_COLORREF)
        setter(
            hwnd,
            35,  # DWMWA_CAPTION_COLOR
            ctypes.byref(caption_color),
            ctypes.sizeof(caption_color),
        )
        setter(
            hwnd,
            36,  # DWMWA_TEXT_COLOR
            ctypes.byref(text_color),
            ctypes.sizeof(text_color),
        )
        setter(
            hwnd,
            34,  # DWMWA_BORDER_COLOR
            ctypes.byref(caption_color),
            ctypes.sizeof(caption_color),
        )
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False
