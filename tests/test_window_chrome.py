import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bilibili_drops_miner.gui_parts.window_chrome import (
    bundled_resource_path,
    install_window_chrome,
    tray_icon,
)


def test_application_icon_is_loaded_from_bundled_assets() -> None:
    app = QApplication.instance() or QApplication([])
    install_window_chrome(app)

    assert bundled_resource_path("assets/bilibili.png").is_file()
    assert not app.windowIcon().isNull()


def test_high_contrast_tray_icon_is_bundled_separately() -> None:
    assert bundled_resource_path("assets/bilibili-tray.png").is_file()
    assert bundled_resource_path("assets/bilibili-tray.ico").is_file()

    icon = tray_icon()

    assert not icon.isNull()
    assert not icon.pixmap(16, 16).isNull()
    assert not icon.pixmap(24, 24).isNull()
