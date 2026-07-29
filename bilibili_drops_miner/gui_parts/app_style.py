from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


APP_STYLE_SHEET = """
        QWidget { background: #1a1d23; color: #e6e7eb; }
        QLabel { background: transparent; color: #e6e7eb; }
        QToolTip { background: #2f3440; color: #e6e7eb; border: 1px solid #3a3f4b;
                   padding: 4px 8px; border-radius: 4px; }

        QLineEdit {
            background: #2b2f3a; color: #e6e7eb;
            border: 1px solid #2f3440; border-radius: 6px;
            padding: 6px 10px; min-height: 20px;
            selection-background-color: #4f8cff;
        }
        QLineEdit:focus { border-color: #566071; background: #2e3340; }
        QLineEdit:disabled { color: #6b7280; background: #23262e; }

        QComboBox {
            background: #2b2f3a; color: #e6e7eb;
            border: 1px solid #2f3440; border-radius: 6px;
            padding: 6px 10px; min-height: 20px;
            selection-background-color: #4f8cff;
        }
        QComboBox:focus { border-color: #566071; background: #2e3340; }
        QComboBox::drop-down {
            border: 0; width: 24px; background: transparent;
        }
        QComboBox QAbstractItemView {
            background: #242832; color: #e6e7eb;
            border: 1px solid #2f3440; selection-background-color: #4f8cff;
        }

        QTabWidget::pane {
            background: #1f232b; border: 1px solid #343b48;
            border-radius: 8px; top: -1px;
        }
        QTabBar::tab {
            background: #2b303b; color: #aeb6c5;
            border: 1px solid #343b48; border-bottom: 0;
            padding: 9px 22px; min-width: 96px;
        }
        QTabBar::tab:first { border-top-left-radius: 7px; }
        QTabBar::tab:last { border-top-right-radius: 7px; }
        QTabBar::tab:selected {
            background: #1f232b; color: #ffffff;
            border-top: 2px solid #4f8cff;
        }
        QTabBar::tab:hover { color: #ffffff; background: #343a46; }

        QTableWidget {
            background: #1f222a; alternate-background-color: #242832;
            color: #e6e7eb; border: 1px solid #343b48; border-radius: 6px;
            gridline-color: #343b48; selection-background-color: #1d4ed8;
        }
        QHeaderView::section {
            background: #2b303b; color: #dce1e8; border: 0;
            border-bottom: 1px solid #3a4250; padding: 7px;
        }

        QPlainTextEdit {
            background: #1f222a; color: #d8dae0;
            border: 1px solid #2f3440; border-radius: 6px;
            padding: 6px; selection-background-color: #4f8cff;
        }

        QCheckBox { background: transparent; spacing: 8px; color: #e6e7eb; }
        QCheckBox::indicator {
            width: 16px; height: 16px; border-radius: 4px;
        }
        QCheckBox::indicator:unchecked {
            background: #1f232b; border: 1px solid #64748b;
        }
        QCheckBox::indicator:checked {
            background: #2563eb; border: 2px solid #93c5fd;
        }
        QCheckBox:focus { color: #cbd5e1; border: 0; }

        QProgressBar {
            background: #2b2f3a; border: 0; border-radius: 4px;
            min-height: 6px; max-height: 6px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                        stop:0 #4f8cff, stop:1 #7aa7ff);
            border-radius: 4px;
        }

        QScrollBar:vertical {
            background: transparent; width: 10px; margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #3a3f4b; border-radius: 4px; min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background: #4a5060; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            background: transparent; height: 0; border: 0;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }
        QScrollBar:horizontal {
            background: transparent; height: 10px; margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background: #3a3f4b; border-radius: 4px; min-width: 24px;
        }
        QScrollBar::handle:horizontal:hover { background: #4a5060; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            background: transparent; width: 0; border: 0;
        }

        QMenu {
            background: #242832; color: #e6e7eb;
            border: 1px solid #2f3440; border-radius: 6px; padding: 4px;
        }
        QMenu::item { padding: 6px 18px; border-radius: 4px; }
        QMenu::item:selected { background: #4f8cff; color: #ffffff; }
        """


def configure_qt_app(app: QApplication) -> None:
    app.setStyle("Fusion")
    if sys.platform == "win32":
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    if family not in QFontDatabase.families():
        family = "Segoe UI"
    default_font = QFont(family, 10)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)
    app.setStyleSheet(APP_STYLE_SHEET)
