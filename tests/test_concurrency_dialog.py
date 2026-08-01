from bilibili_drops_miner.gui_parts import concurrency_dialog


class _FakeMessageBox:
    Warning = object()
    ActionRole = object()
    AcceptRole = object()
    RejectRole = object()
    latest = None

    def __init__(self, _parent) -> None:
        type(self).latest = self
        self.buttons: list[tuple[object, str]] = []
        self.informative_text = ""
        self._clicked = None

    def setIcon(self, _icon) -> None:
        return None

    def setWindowTitle(self, _title: str) -> None:
        return None

    def setText(self, _text: str) -> None:
        return None

    def setInformativeText(self, text: str) -> None:
        self.informative_text = text

    def addButton(self, label: str, _role):
        button = object()
        self.buttons.append((button, label))
        return button

    def exec(self) -> None:
        self._clicked = self.buttons[0][0]

    def clickedButton(self):
        return self._clicked


def test_single_account_once_warning_mentions_no_progress_risk(
    monkeypatch,
) -> None:
    monkeypatch.setattr(concurrency_dialog, "QMessageBox", _FakeMessageBox)

    choice = concurrency_dialog.choose_concurrency_boost_mode(None, 1)

    box = _FakeMessageBox.latest
    assert choice == "once"
    assert "不计时" in box.informative_text
    assert "持续固定 32" in [label for _button, label in box.buttons]


def test_existing_fixed_high_hides_persistent_32_and_points_to_settings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(concurrency_dialog, "QMessageBox", _FakeMessageBox)

    choice = concurrency_dialog.choose_concurrency_boost_mode(
        None,
        1,
        existing_fixed_high=True,
    )

    box = _FakeMessageBox.latest
    assert choice == "once"
    labels = [label for _button, label in box.buttons]
    assert "持续固定 32" not in labels
    assert "高级设置" in box.informative_text
