from __future__ import annotations


DISABLED_BUTTON_STYLE = (
    "QPushButton:disabled{background:#343a46;color:#7d8796;"
    "border:1px solid #343a46;}"
)


BUTTON_STYLES: dict[str, str] = {
    "green": (
        "QPushButton{background:#15803d;color:#ffffff;border:1px solid #15803d;border-radius:6px;"
        "padding:8px 18px;min-height:20px;font-weight:600;}"
        "QPushButton:hover{background:#16a34a;}"
        "QPushButton:pressed{background:#166534;}"
        "QPushButton:focus{background:#166534;}"
    ),
    "red": (
        "QPushButton{background:#b91c1c;color:#ffffff;border:1px solid #b91c1c;border-radius:6px;"
        "padding:8px 18px;min-height:20px;font-weight:600;}"
        "QPushButton:hover{background:#dc2626;}"
        "QPushButton:pressed{background:#991b1b;}"
        "QPushButton:focus{background:#991b1b;}"
    ),
    "blue": (
        "QPushButton{background:#2563eb;color:#ffffff;border:1px solid #2563eb;border-radius:6px;"
        "padding:8px 18px;min-height:20px;font-weight:600;}"
        "QPushButton:hover{background:#3b73e6;}"
        "QPushButton:pressed{background:#1d4ed8;}"
        "QPushButton:focus{background:#1d4ed8;}"
    ),
    "purple": (
        "QPushButton{background:#7c3aed;color:#ffffff;border:1px solid #7c3aed;border-radius:6px;"
        "padding:8px 18px;min-height:20px;font-weight:600;}"
        "QPushButton:hover{background:#8b6ff0;}"
        "QPushButton:pressed{background:#6d28d9;}"
        "QPushButton:focus{background:#6d28d9;}"
    ),
    "gray": (
        "QPushButton{background:#3a3f4b;color:#e6e7eb;border:0;border-radius:6px;"
        "padding:8px 18px;min-height:20px;font-weight:600;}"
        "QPushButton:hover{background:#454b58;}"
        "QPushButton:pressed{background:#2f343e;}"
        "QPushButton:focus{background:#2f343e;}"
    ),
    "": (
        "QPushButton{background:#2f343e;color:#e6e7eb;border:1px solid #3a3f4b;"
        "border-radius:6px;padding:8px 18px;min-height:20px;font-weight:500;}"
        "QPushButton:hover{background:#363b47;border-color:#4a5060;}"
        "QPushButton:pressed{background:#272b34;}"
        "QPushButton:focus{background:#272b34;border-color:#4a5060;}"
    ),
}


CARD_STYLE = (
    "QFrame#card{background:#242832;border:1px solid #2f3440;border-radius:10px;}"
)
