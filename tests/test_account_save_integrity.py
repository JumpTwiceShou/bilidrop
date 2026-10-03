import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from bilibili_drops_miner.credential_store import MemoryCredentialStore
from bilibili_drops_miner.gui_parts import main_window as main_window_module
from bilibili_drops_miner.gui_parts.cookie_profiles import COOKIE_PROFILE_METADATA_KEY


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def account_window(monkeypatch, tmp_path, app):
    monkeypatch.chdir(tmp_path)
    store = MemoryCredentialStore()
    monkeypatch.setattr(main_window_module, "JsonCredentialStore", lambda: store)
    monkeypatch.setattr(main_window_module.MinerGUI, "_setup_system_tray", lambda self: None)
    monkeypatch.setattr(main_window_module.MinerGUI, "_check_update_silent", lambda self: None)
    monkeypatch.setattr(main_window_module.MinerGUI, "_validate_saved_account_logins", lambda self: None)
    window = main_window_module.MinerGUI()
    errors = []
    monkeypatch.setattr(window, "_show_error", lambda *args: errors.append(args))
    window.cookie_edit.setText("DedeUserID=10001; SESSDATA=synthetic")
    window.cookie_remark_edit.setText("Synthetic account")
    yield window, store, errors
    window._ui_alive = False
    window._exit_requested = True
    for timer_name in (
        "_log_timer", "_stop_poll_timer", "_task_refresh_timer",
        "_live_watch_time_timer", "_login_validation_timer", "_automatic_mining_timer",
    ):
        getattr(window, timer_name).stop()
    window.settings_dialog.close()
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_new_account_save_includes_recent_selection_in_first_commit(account_window, monkeypatch):
    window, store, errors = account_window
    original_set_batch = store.set_batch
    commits = []

    def accept_one_commit(credentials, metadata):
        if commits:
            raise OSError("synthetic second commit unavailable")
        commits.append(metadata)
        original_set_batch(credentials, metadata)

    with monkeypatch.context() as failure:
        failure.setattr(store, "set_batch", accept_one_commit)
        window.save_cookie_profile()

    assert errors == []
    assert not window._active_session.temporary
    assert len(window._cookie_profiles) == 1
    saved = store.get_metadata(COOKIE_PROFILE_METADATA_KEY)
    assert saved["last_selected_credential_id"] == window._active_session.credential_id
    assert saved["accounts"][0]["credential_id"] == window._active_session.credential_id
    assert store.get(window._active_session.credential_id) == "DedeUserID=10001; SESSDATA=synthetic"


def test_failed_save_preserves_temporary_identity_and_previous_selection(account_window, monkeypatch):
    window, store, errors = account_window
    window._last_selected_credential_id = "previously-selected-account"
    original_metadata = store.get_metadata(COOKIE_PROFILE_METADATA_KEY)

    def fail_metadata(credentials, metadata):
        raise OSError("synthetic storage unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(store, "set_batch", fail_metadata)
        window.save_cookie_profile()

    assert errors
    assert window._active_session.temporary
    assert window._active_session.credential_id == ""
    assert window._cookie_profiles == []
    assert window._last_selected_credential_id == "previously-selected-account"
    assert store.get_metadata(COOKIE_PROFILE_METADATA_KEY) == original_metadata


def test_overwriting_saved_account_persists_replacement_account_settings(account_window, monkeypatch):
    window, store, errors = account_window
    window.rooms_edit.setText("111")
    window.threads_spin.setValue(64)
    window.save_cookie_profile()
    first = window._active_session
    original_credential_id = first.credential_id

    window.new_temporary_account()
    replacement = window._active_session
    window.cookie_edit.setText("DedeUserID=10002; SESSDATA=replacement-synthetic")
    window.cookie_remark_edit.setText("Synthetic account")
    window.rooms_edit.setText("222")
    window.threads_spin.setValue(8)
    window.reconnect_spin.setValue(12)
    window.task_interval_spin.setValue(45)
    window.disable_task_notify_check.setChecked(True)
    window.concurrency_mode_combo.setCurrentIndex(
        window.concurrency_mode_combo.findData("fixed")
    )
    monkeypatch.setattr(window, "_ask_cookie_profile_save_action", lambda _: "overwrite")

    window.save_cookie_profile()

    expected_settings = {
        "version": 1,
        "rooms_text": "222",
        "thread_count": 8,
        "reconnect_delay_seconds": 12,
        "task_query_interval_seconds": 45,
        "notify_on_task_complete": False,
        "concurrency_mode": "fixed",
    }
    assert errors == []
    assert len(window._cookie_profiles) == 1
    assert window._cookie_profiles[0].settings == expected_settings
    persisted = store.get_metadata(COOKIE_PROFILE_METADATA_KEY)
    assert persisted["accounts"][0]["settings"] == expected_settings
    assert persisted["accounts"][0]["credential_id"] == original_credential_id
    assert store.get(original_credential_id) == "DedeUserID=10002; SESSDATA=replacement-synthetic"
    assert replacement.credential_id == original_credential_id
    assert replacement.account_settings_saved
    assert not replacement.temporary
    assert first.session_id not in window._account_sessions


def test_failed_new_account_save_preserves_other_profile_settings(account_window, monkeypatch):
    window, store, errors = account_window
    window.rooms_edit.setText("111")
    window.threads_spin.setValue(64)
    window.save_cookie_profile()
    first = window._active_session
    original_profile = window._cookie_profiles[0]
    original_settings = dict(original_profile.settings)
    original_metadata = store.get_metadata(COOKIE_PROFILE_METADATA_KEY)

    # Unsaved edits stay in A's workspace when opening a temporary account B.
    window.rooms_edit.setText("333")
    window.new_temporary_account()
    second = window._active_session
    window.cookie_edit.setText("DedeUserID=10002; SESSDATA=second-synthetic")
    window.cookie_remark_edit.setText("Second account")
    window.rooms_edit.setText("222")

    def fail_commit(credentials, metadata):
        raise OSError("synthetic storage unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(store, "set_batch", fail_commit)
        window.save_cookie_profile()

    assert errors
    assert first.rooms_text == "333"
    assert original_profile.settings == original_settings
    assert len(window._cookie_profiles) == 1
    assert window._cookie_profiles[0].settings == original_settings
    assert store.get_metadata(COOKIE_PROFILE_METADATA_KEY) == original_metadata
    assert second.temporary
    assert second.credential_id == ""
