import os
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QValidator, QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QSpinBox

from bilibili_drops_miner.client_parts.models import (
    TaskCheckpointProgress,
    TaskProgress,
)
from bilibili_drops_miner.automatic_mining import (
    AutomaticAccountCheckResult,
    ScheduledTaskSelection,
)
from bilibili_drops_miner.credential_store import MemoryCredentialStore
from bilibili_drops_miner.domain import ApplicationState, RuntimeHealth, TaskSnapshot
from bilibili_drops_miner.gui_parts import main_window as main_window_module
from bilibili_drops_miner.gui_parts.account_sessions import LoginState
from bilibili_drops_miner.gui_parts.cookie_profiles import (
    CookieProfile,
    CookieProfileState,
)


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def window(monkeypatch, app):
    monkeypatch.setattr(
        main_window_module,
        "load_cookie_profile_state",
        lambda **kwargs: CookieProfileState([]),
    )
    monkeypatch.setattr(
        main_window_module,
        "save_cookie_profiles",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        main_window_module, "JsonCredentialStore", MemoryCredentialStore
    )
    item = main_window_module.MinerGUI()
    yield item
    item._ui_alive = False
    for timer_name in (
        "_log_timer",
        "_stop_poll_timer",
        "_task_refresh_timer",
        "_live_watch_time_timer",
        "_login_validation_timer",
    ):
        getattr(item, timer_name).stop()
    item.settings_dialog.close()
    item.close()
    item.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def _dispose_window(item, app) -> None:
    item._ui_alive = False
    for timer_name in (
        "_log_timer",
        "_stop_poll_timer",
        "_task_refresh_timer",
        "_live_watch_time_timer",
        "_login_validation_timer",
    ):
        getattr(item, timer_name).stop()
    item.settings_dialog.close()
    item.close()
    item.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_initial_gui_is_guided_and_secrets_are_masked(window, app) -> None:
    assert window.runtime_state_label.text() == "未运行"
    assert window.cookie_edit.echoMode() == QLineEdit.Password
    assert window.notify_urls_edit.echoMode() == QLineEdit.Password
    assert not window.settings_dialog.isVisible()
    assert window.settings_button.text() == "设置与日志"
    assert window.threads_spin.value() == 16
    assert window.concurrency_mode_combo.currentData() == "automatic"
    assert window.auto_check_updates_check.isChecked()
    assert "不自动下载" in window.auto_check_updates_check.toolTip()
    assert "Telegram" in window.notify_urls_edit.placeholderText()
    assert "tgram://BotToken/ChatID" in window.notify_urls_edit.placeholderText()
    assert window.claim_rewards_btn.text() == "手动领取"
    assert window.start_btn.text() == "开始"
    assert window.enable_auto_btn.text() == "后台自动挂机"
    assert not window.apply_all_switch.isChecked()
    assert window.apply_all_switch.accessibleName() == "应用到所有账号"
    assert "每次打开程序后需要手动开启" in window.auto_mining_description.text()
    assert not window.watch_time_label.isVisible()
    assert not window._live_watch_time_timer.isActive()
    assert not any(
        button.text() in {"全部开始", "全部停止"}
        for button in window.findChildren(QPushButton)
    )
    assert window.task_table.columnCount() == 5
    assert "临时·关闭即删" in window.cookie_profile_combo.currentText()
    assert not hasattr(window, "account_session_hint")
    assert not any(
        button.text() == "新建临时"
        for button in window.findChildren(QPushButton)
    )
    assert window.cookie_profile_combo.maximumWidth() == 520

    window.show()
    app.processEvents()
    row_y = {
        widget.mapTo(window, QPoint(0, widget.height() // 2)).y()
        for widget in (
            window.cookie_profile_combo,
            window.cookie_remark_edit,
            window.save_cookie_profile_btn,
            window.delete_cookie_profile_btn,
        )
    }
    assert max(row_y) - min(row_y) <= 1
    window.hide()


def test_startup_selects_last_used_saved_profile_and_drops_legacy_temp(
    monkeypatch,
    app,
) -> None:
    store = MemoryCredentialStore()
    store.set("last-cookie", "DedeUserID=99999; SESSDATA=must-not-restore")
    profiles = [
        CookieProfile(
            "主号",
            "DedeUserID=10001; SESSDATA=one",
            credential_id="account-one",
        ),
        CookieProfile(
            "小号",
            "DedeUserID=10002; SESSDATA=two",
            credential_id="account-two",
        ),
    ]
    monkeypatch.setattr(main_window_module, "JsonCredentialStore", lambda: store)
    monkeypatch.setattr(
        main_window_module,
        "load_cookie_profile_state",
        lambda **kwargs: CookieProfileState(profiles, "account-two"),
    )
    monkeypatch.setattr(
        main_window_module,
        "save_cookie_profiles",
        lambda *args, **kwargs: None,
    )

    item = main_window_module.MinerGUI()
    try:
        assert item.cookie_edit.text() == profiles[1].cookie
        assert "小号" in item.cookie_profile_combo.currentText()
        assert "已保存" in item.cookie_profile_combo.currentText()
        assert store.get("last-cookie") == ""
    finally:
        _dispose_window(item, app)


def test_startup_settings_do_not_erase_saved_account_identity(
    monkeypatch,
    app,
) -> None:
    store = MemoryCredentialStore()
    profiles = [
        CookieProfile(
            "主号",
            "DedeUserID=10001; SESSDATA=one",
            credential_id="account-one",
        ),
        CookieProfile(
            "小号",
            "DedeUserID=10002; SESSDATA=two",
            credential_id="account-two",
        ),
    ]
    monkeypatch.setattr(main_window_module, "JsonCredentialStore", lambda: store)
    monkeypatch.setattr(
        main_window_module,
        "load_cookie_profile_state",
        lambda **kwargs: CookieProfileState(profiles, "account-two"),
    )
    monkeypatch.setattr(
        main_window_module,
        "load_stored_config_data",
        lambda *_args, **_kwargs: {
            "room_ids": [23612045],
            "thread_count": 16,
            "task_query_interval_seconds": 30,
            "automatic_mining_enabled": True,
        },
    )
    monkeypatch.setattr(
        main_window_module,
        "save_cookie_profiles",
        lambda *args, **kwargs: None,
    )

    item = main_window_module.MinerGUI()
    try:
        sessions = tuple(item._account_sessions.values())
        assert [session.remark for session in sessions] == ["主号", "小号"]
        assert [session.uid for session in sessions] == ["10001", "10002"]
        assert item.cookie_edit.text() == profiles[1].cookie
        assert "小号" in item.cookie_profile_combo.currentText()
        assert "UID 10002" in item.cookie_profile_combo.currentText()
        assert item.rooms_edit.text() == "23612045"
        assert item._automatic_mining_session_ids == set()
        assert item.enable_auto_btn.text() == "后台自动挂机"
    finally:
        _dispose_window(item, app)


def test_settings_button_opens_dedicated_window(window, app) -> None:
    window.open_settings_log()
    app.processEvents()

    assert window.settings_dialog.isVisible()
    assert window.settings_tabs.count() == 2
    assert window.settings_tabs.tabText(0) == "高级设置"
    assert window.settings_tabs.tabText(1) == "运行日志"
    window.settings_tabs.setCurrentIndex(1)
    app.processEvents()
    assert window.log_text.isVisible()

    window.settings_dialog.close()


def test_disabled_update_check_does_not_contact_release_api(
    window,
    monkeypatch,
) -> None:
    window.auto_check_updates_check.setChecked(False)
    monkeypatch.setattr(
        main_window_module,
        "check_latest_release",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("关闭更新检查后不得请求 Release API")
        ),
    )

    window._check_update_silent()


def test_background_automatic_mining_controls_are_mutually_exclusive(
    window,
) -> None:
    window.enable_background_auto()
    assert window.enable_auto_btn.text() == "停止后台自动"
    assert "已开启" in window.auto_mining_description.text()

    window.disable_background_auto()
    assert window.enable_auto_btn.text() == "后台自动挂机"


def test_stopping_background_auto_stops_only_auto_started_runtime(window) -> None:
    auto_session = window._active_session
    auto_session.controller = _FakeWorkerController()
    auto_session.controller.is_running = True
    auto_session.auto_started_runtime = True
    window._automatic_mining_session_ids.add(auto_session.session_id)

    window.disable_background_auto()

    assert auto_session.controller.stop_requests == 1
    assert not auto_session.controller.is_running

    auto_session.controller = _FakeWorkerController()
    auto_session.controller.is_running = True
    auto_session.auto_started_runtime = False
    window._automatic_mining_session_ids.add(auto_session.session_id)

    window.disable_background_auto()

    assert auto_session.controller.stop_requests == 0
    assert auto_session.controller.is_running


def test_settings_save_and_load_use_combined_store_without_file_picker(
    window,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("settings save must not open a file picker")
        ),
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("settings load must not open a file picker")
        ),
    )
    window.rooms_edit.setText("23612045")
    window.threads_spin.setValue(32)
    window.task_ids_edit.setText("daily-a,daily-b")
    window.auto_check_updates_check.setChecked(False)
    window._automatic_mining_session_ids.add(window._active_session_id)

    window.save_config()
    saved = main_window_module.load_stored_config_data(
        window._credential_store
    )
    assert saved["automatic_mining_enabled"] is False
    assert saved["auto_check_updates"] is False
    window.rooms_edit.clear()
    window.task_ids_edit.clear()
    window.auto_check_updates_check.setChecked(True)
    window.load_config()

    assert window.rooms_edit.text() == "23612045"
    assert window.task_ids_edit.text() == "daily-a,daily-b"
    assert not window.auto_check_updates_check.isChecked()


def test_runtime_table_shows_each_reward_checkpoint(window) -> None:
    window._set_application_state(ApplicationState.RUNNING)
    window._render_task_snapshot(
        TaskSnapshot(
            progresses=(
                TaskProgress(
                    "daily",
                    "观看直播",
                    0,
                    120,
                    240,
                    check_points=[
                            TaskCheckpointProgress(
                                "60",
                                "观看60分钟",
                                3,
                            120,
                            60,
                            "头像框",
                            1,
                        ),
                            TaskCheckpointProgress(
                                "120",
                                "观看120分钟",
                                2,
                            120,
                            120,
                            "喷漆",
                            1,
                        ),
                    ],
                ),
            )
        )
    )

    assert window.task_table.rowCount() == 2
    assert "观看60分钟" in window.task_table.item(0, 0).text()
    assert window.task_table.item(0, 4).text() == "已领取"
    assert "观看120分钟" in window.task_table.item(1, 0).text()
    assert window.task_table.item(1, 4).text() == "待领取"
    assert window.claim_rewards_btn.isEnabled()


def test_running_state_locks_account_and_room_fields(window) -> None:
    window.cookie_edit.setText("DedeUserID=1; SESSDATA=fixture")
    window._set_application_state(ApplicationState.RUNNING)
    assert not window.cookie_edit.isEnabled()
    assert not window.rooms_edit.isEnabled()
    assert not window.threads_spin.isEnabled()
    window._active_session.controller = _FakeWorkerController()
    window._active_session.controller.is_running = True
    window._update_global_run_controls()
    assert window.start_btn.text() == "停止"
    assert window.start_btn.isEnabled()
    assert window.cookie_profile_combo.isEnabled()


def test_runtime_health_explains_automatic_concurrency_stage(window) -> None:
    window._render_runtime_health(
        RuntimeHealth(
            state=ApplicationState.RUNNING,
            active_sessions=20,
            target_sessions=16,
            concurrency_mode="automatic",
            concurrency_phase="catchup",
            concurrency_detail="进度约为现实时间的 2.40 倍，继续使用追赶并发",
        )
    )

    assert "会话 当前 20 / 目标 16" in window.runtime_detail_label.text()
    assert "自动追赶" in window.runtime_detail_label.text()
    assert "2.40 倍" in window.runtime_detail_label.text()


@pytest.mark.parametrize(
    (
        "state",
        "label",
        "fields_enabled",
        "discover_enabled",
    ),
    (
        (ApplicationState.IDLE, "未运行", True, True),
        (ApplicationState.DISCOVERING, "识别中", False, True),
        (ApplicationState.STARTING, "启动中", False, False),
        (ApplicationState.RUNNING, "运行中", False, False),
        (ApplicationState.STOPPING, "停止中", False, False),
        (ApplicationState.ERROR, "异常", True, True),
    ),
)
def test_application_states_control_actions_and_fields(
    window,
    state,
    label,
    fields_enabled,
    discover_enabled,
) -> None:
    window.cookie_edit.setText("DedeUserID=1; SESSDATA=fixture")
    window._set_application_state(state)
    assert window.runtime_state_label.text() == label
    assert window.cookie_edit.isEnabled() is fields_enabled
    assert window.rooms_edit.isEnabled() is fields_enabled
    assert window.discover_btn.isEnabled() is discover_enabled
    assert window.cookie_profile_combo.isEnabled() is (
        state != ApplicationState.DISCOVERING
    )


def test_structured_task_snapshot_populates_table(window) -> None:
    window._set_application_state(ApplicationState.RUNNING)
    window._apply_task_snapshot(
        TaskSnapshot(
            progresses=(
                TaskProgress("task-a", "观看直播", 2, 10, 10),
                TaskProgress("task-b", "发送弹幕", 0, 0, 1),
            )
        )
    )
    assert window.task_table.rowCount() == 2
    assert window.task_table.item(0, 0).text() == "观看直播"
    assert window.task_table.item(0, 2).text() == "已完成"
    assert window.claim_rewards_btn.isEnabled()


def test_empty_task_snapshot_has_actionable_message(window) -> None:
    window._apply_task_snapshot(TaskSnapshot(progresses=()))
    assert window.task_table.rowCount() == 1
    assert "识别当前任务" in window.task_table.item(0, 0).text()
    assert not window.claim_rewards_btn.isEnabled()


def test_numeric_settings_are_plain_validated_text_fields(window) -> None:
    for field in (
        window.threads_spin,
        window.reconnect_spin,
        window.task_interval_spin,
    ):
        assert isinstance(field, QLineEdit)
        assert not isinstance(field, QSpinBox)
        validator = field.validator()
        assert validator is not None
        state, _, _ = validator.validate("not-a-number", 12)
        assert state == QValidator.Invalid

    window.threads_spin.setText("17")
    assert window.threads_spin.value() == 17


def test_numeric_settings_ignore_mouse_wheel(window, app) -> None:
    window.reconnect_spin.setText("8")
    event = QWheelEvent(
        QPointF(4, 4),
        QPointF(4, 4),
        QPoint(),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    QApplication.sendEvent(window.reconnect_spin, event)

    assert window.reconnect_spin.text() == "8"


def test_overwatch_preset_sets_room_and_starts_discovery(window, monkeypatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(window, "auto_fetch_task_ids", lambda: called.append(True))

    window.auto_fetch_overwatch_esports()

    assert window.rooms_edit.text() == "23612045"
    assert called == [True]


def test_recognized_task_ids_trigger_immediate_structured_refresh(
    window,
    monkeypatch,
) -> None:
    refreshes: list[bool] = []
    monkeypatch.setattr(
        window.task_controller,
        "refresh",
        lambda *, manual: refreshes.append(manual),
    )

    window._apply_auto_task_ids("daily-a,daily-b")

    assert window.task_ids_edit.text() == "daily-a,daily-b"
    assert refreshes == [False]


def test_recognized_tasks_only_update_current_account_when_scope_is_off(
    window,
    monkeypatch,
) -> None:
    first = window._active_session
    first.task_ids_text = "first-old"
    window._restore_active_session()
    window.new_temporary_account()
    second = window._active_session
    second.task_ids_text = "second-old"
    window._restore_active_session()
    refreshes: list[str] = []
    monkeypatch.setattr(
        first.task_controller,
        "refresh",
        lambda *, manual: refreshes.append(first.session_id),
    )
    monkeypatch.setattr(
        second.task_controller,
        "refresh",
        lambda *, manual: refreshes.append(second.session_id),
    )
    window.apply_all_switch.setChecked(False)

    window._apply_auto_task_ids("daily-a,daily-b")

    assert first.task_ids_text == "first-old"
    assert second.task_ids_text == "daily-a,daily-b"
    assert refreshes == [second.session_id]


def test_recognized_tasks_sync_all_accounts_and_refresh_independently(
    window,
    monkeypatch,
) -> None:
    first = window._active_session
    first.cookie = "DedeUserID=10001; SESSDATA=one"
    first.controller = _FakeWorkerController()
    first_snapshot = TaskSnapshot(
        progresses=(TaskProgress("first-old", "账号一旧进度", 0, 1, 10),)
    )
    first.latest_task_snapshot = first_snapshot
    first.task_ids_text = "first-old"
    window._restore_active_session()
    window.new_temporary_account()
    first.controller.is_running = True
    second = window._active_session
    second.cookie = "DedeUserID=10002; SESSDATA=two"
    second.controller = _FakeWorkerController()
    second_snapshot = TaskSnapshot(
        progresses=(TaskProgress("second-old", "账号二旧进度", 0, 2, 10),)
    )
    second.latest_task_snapshot = second_snapshot
    window._restore_active_session()
    refreshes: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        first.task_controller,
        "refresh",
        lambda *, manual: refreshes.append((first.session_id, manual)),
    )
    monkeypatch.setattr(
        second.task_controller,
        "refresh",
        lambda *, manual: refreshes.append((second.session_id, manual)),
    )
    window.apply_all_switch.setChecked(True)

    window._apply_auto_task_ids("daily-a,daily-b")

    assert first.task_ids_text == "daily-a,daily-b"
    assert second.task_ids_text == "daily-a,daily-b"
    assert window.task_ids_edit.text() == "daily-a,daily-b"
    assert first.controller.task_id_updates == [["daily-a", "daily-b"]]
    assert second.controller.task_id_updates == []
    assert refreshes == [
        (first.session_id, False),
        (second.session_id, False),
    ]
    assert first.latest_task_snapshot is not first_snapshot
    assert second.latest_task_snapshot is not second_snapshot
    assert not first.latest_task_snapshot.progresses
    assert not second.latest_task_snapshot.progresses
    assert first.controller.starts == 0
    assert second.controller.starts == 0


def test_discovery_button_becomes_cancel_action(window, monkeypatch) -> None:
    cancelled: list[bool] = []
    monkeypatch.setattr(
        window.browser_actions,
        "cancel_discovery",
        lambda: cancelled.append(True),
    )
    window._set_application_state(ApplicationState.DISCOVERING)

    window.auto_fetch_task_ids()

    assert cancelled == [True]
    assert window.discover_btn.text() == "正在取消…"
    assert not window.discover_btn.isEnabled()


def test_temporary_cookie_has_uid_and_clear_lifetime_state(window, monkeypatch) -> None:
    cookie = "DedeUserID=10003; SESSDATA=fixture"
    monkeypatch.setattr(window, "_confirm_save_new_cookie", lambda _name: False)
    window.cookie_edit.setText(cookie)

    window._prompt_save_new_cookie(cookie)

    assert "UID 10003" in window.cookie_profile_combo.currentText()
    assert "临时·关闭即删" in window.cookie_profile_combo.currentText()
    tooltip = window.cookie_profile_combo.itemData(
        window.cookie_profile_combo.currentIndex(),
        Qt.ToolTipRole,
    )
    assert "关闭程序后删除" in tooltip
    assert window._credential_store.get("last-cookie") == ""


def test_new_cookie_prompt_uses_uid_when_remark_is_empty(window, monkeypatch) -> None:
    cookie = "DedeUserID=10003; SESSDATA=fixture"
    names: list[str] = []
    monkeypatch.setattr(
        window,
        "_confirm_save_new_cookie",
        lambda profile_name: names.append(profile_name) or True,
    )
    window.cookie_remark_edit.clear()
    window.cookie_edit.setText(cookie)

    window._prompt_save_new_cookie(cookie)

    assert names == ["UID 10003"]
    assert window._cookie_profiles[0].remark == "UID 10003"
    assert "已保存" in window.cookie_profile_combo.currentText()
    assert not window._active_session.temporary


def test_new_cookie_prompt_preserves_entered_remark(window, monkeypatch) -> None:
    cookie = "DedeUserID=10003; SESSDATA=fixture"
    names: list[str] = []
    monkeypatch.setattr(
        window,
        "_confirm_save_new_cookie",
        lambda profile_name: names.append(profile_name) or True,
    )
    window.cookie_remark_edit.setText("守望先锋主号")
    window.cookie_edit.setText(cookie)

    window._prompt_save_new_cookie(cookie)

    assert names == ["守望先锋主号"]
    assert window._cookie_profiles[0].remark == "守望先锋主号"


def test_declined_cookie_stays_in_memory_only(window, monkeypatch) -> None:
    cookie = "DedeUserID=10001; SESSDATA=temporary"
    monkeypatch.setattr(window, "_confirm_save_new_cookie", lambda _name: False)

    window.cookie_edit.setText(cookie)
    window._prompt_save_new_cookie(cookie)

    assert window._active_session.temporary
    assert window._active_session.uid == "10001"
    assert window._cookie_profiles == []
    assert window._credential_store.get("last-cookie") == ""


def test_multiple_temporary_accounts_keep_independent_fields(window) -> None:
    first_id = window._active_session_id
    window.cookie_edit.setText("DedeUserID=10001; SESSDATA=one")
    window.rooms_edit.setText("111")
    window.task_ids_edit.setText("task-one")
    window._capture_active_session()

    window.new_temporary_account()
    second_id = window._active_session_id
    window.cookie_edit.setText("DedeUserID=10002; SESSDATA=two")
    window.rooms_edit.setText("222")
    window.task_ids_edit.setText("task-two")
    window._capture_active_session()

    assert first_id != second_id
    window._activate_account_session(first_id, remember_saved=False)
    assert window.rooms_edit.text() == "111"
    assert window.task_ids_edit.text() == "task-one"
    window._activate_account_session(second_id, remember_saved=False)
    assert window.rooms_edit.text() == "222"
    assert window.task_ids_edit.text() == "task-two"


def test_switching_accounts_restores_each_task_snapshot(window) -> None:
    first_id = window._active_session_id
    window._apply_task_snapshot(
        TaskSnapshot(
            progresses=(TaskProgress("task-one", "账号一任务", 1, 2, 4),)
        )
    )

    window.new_temporary_account()
    second_id = window._active_session_id
    window._apply_task_snapshot(
        TaskSnapshot(
            progresses=(TaskProgress("task-two", "账号二任务", 0, 1, 4),)
        )
    )

    window._activate_account_session(first_id, remember_saved=False)
    assert window.task_table.item(0, 0).text() == "账号一任务"
    window._activate_account_session(second_id, remember_saved=False)
    assert window.task_table.item(0, 0).text() == "账号二任务"


class _FakeWorkerController:
    def __init__(self) -> None:
        self.is_running = False
        self.stop_signal_set = False
        self.stopping_in_progress = False
        self.miner = None
        self.starts = 0
        self.configs = []
        self.stop_requests = 0
        self.on_health = None
        self.task_id_updates = []

    def start(self, _config, *, logger, on_health, on_task_snapshot) -> bool:
        self.starts += 1
        self.configs.append(_config)
        self.is_running = True
        self.on_health = on_health
        return True

    def request_stop(self, *, logger):
        self.stop_requests += 1
        self.is_running = False
        self.stop_signal_set = True
        return "not_running"

    def poll_shutdown(self, *, logger):
        return "stopped"

    def update_task_ids(self, _task_ids):
        self.task_id_updates.append(list(_task_ids))
        return True


def test_profile_selector_displays_invalid_login_state(window) -> None:
    session = window._active_session
    session.cookie = "DedeUserID=10001; SESSDATA=expired"
    session.remark = "主号"
    session.credential_id = "account-one"
    session.temporary = False
    session.login_state = LoginState.INVALID

    window._refresh_cookie_profile_combo(selected_session_id=session.session_id)

    assert "登录失效" in window.cookie_profile_combo.currentText()


def test_login_validation_updates_profile_and_rejects_uid_mismatch(window) -> None:
    session = window._active_session
    session.cookie = "DedeUserID=10001; SESSDATA=fixture"
    session.login_check_generation = 7
    session.login_state = LoginState.CHECKING

    window._apply_account_login_state(
        session.session_id,
        7,
        LoginState.VALID,
        "10001",
    )
    assert session.login_state == LoginState.VALID

    session.login_check_generation = 8
    window._apply_account_login_state(
        session.session_id,
        8,
        LoginState.VALID,
        "99999",
    )
    assert session.login_state == LoginState.INVALID


def test_invalid_saved_profile_cannot_start(window, monkeypatch) -> None:
    warnings: list[tuple[str, str]] = []
    session = window._active_session
    session.controller = _FakeWorkerController()
    session.cookie = "DedeUserID=10001; SESSDATA=expired"
    session.remark = "主号"
    session.credential_id = "account-one"
    session.temporary = False
    session.login_state = LoginState.INVALID
    window.cookie_edit.setText(session.cookie)
    window.rooms_edit.setText("23612045")
    monkeypatch.setattr(
        window,
        "_show_warning",
        lambda title, message: warnings.append((title, message)),
    )

    window.start()

    assert session.controller.starts == 0
    assert warnings[0][0] == "登录已失效"
    assert "扫码登录" in warnings[0][1]


def test_qr_same_uid_refreshes_profile_without_overwriting_remark(
    window,
    monkeypatch,
) -> None:
    session = window._active_session
    session.cookie = "DedeUserID=10001; SESSDATA=old"
    session.remark = "不要覆盖的备注"
    session.credential_id = "account-one"
    session.temporary = False
    session.login_state = LoginState.INVALID
    window.cookie_edit.setText(session.cookie)
    window.cookie_remark_edit.setText(session.remark)
    window._cookie_profiles = [
        CookieProfile(
            session.remark,
            session.cookie,
            credential_id=session.credential_id,
        )
    ]
    prompted: list[bool] = []
    monkeypatch.setattr(
        window,
        "_prompt_save_new_cookie",
        lambda *_args: prompted.append(True),
    )

    window._apply_qr_login_cookie("DedeUserID=10001; SESSDATA=new")

    assert len(window._cookie_profiles) == 1
    assert window._cookie_profiles[0].cookie.endswith("SESSDATA=new")
    assert window._cookie_profiles[0].remark == "不要覆盖的备注"
    assert session.cookie.endswith("SESSDATA=new")
    assert session.remark == "不要覆盖的备注"
    assert session.login_state == LoginState.VALID
    assert prompted == []


def test_qr_login_adds_account_without_overwriting_existing_temp(
    window,
    monkeypatch,
) -> None:
    first = window._active_session
    first.cookie = "DedeUserID=10001; SESSDATA=one"
    window.cookie_edit.setText(first.cookie)
    monkeypatch.setattr(window, "_confirm_save_new_cookie", lambda _name: False)

    window._apply_qr_login_cookie("DedeUserID=10002; SESSDATA=two")

    assert len(window._account_sessions) == 2
    assert window._active_session.uid == "10002"
    assert first.cookie == "DedeUserID=10001; SESSDATA=one"


def test_qr_login_can_open_while_current_account_is_running(
    window,
    monkeypatch,
) -> None:
    opened: list[bool] = []

    class FakeQrDialog:
        def __init__(self, parent, *, on_success) -> None:
            opened.append(parent is window and callable(on_success))

        def exec(self) -> None:
            opened.append(True)

    window._active_session.controller = _FakeWorkerController()
    window._active_session.controller.is_running = True
    monkeypatch.setattr(main_window_module, "QrLoginDialog", FakeQrDialog)

    window.auto_fetch_cookie()

    assert opened == [True, True]


def test_two_accounts_can_start_and_show_running_state(window, monkeypatch) -> None:
    monkeypatch.setattr(window, "_schedule_live_watch_time_refresh", lambda: None)
    monkeypatch.setattr(window, "_schedule_task_refresh", lambda: None)

    first = window._active_session
    first.controller = _FakeWorkerController()
    window.cookie_edit.setText("DedeUserID=10001; SESSDATA=one")
    window.rooms_edit.setText("111")
    window.task_ids_edit.setText("task-one")
    window.start()
    window._apply_session_runtime_health(
        first.session_id,
        RuntimeHealth(state=ApplicationState.RUNNING),
    )

    window.new_temporary_account()
    second = window._active_session
    second.controller = _FakeWorkerController()
    window.cookie_edit.setText("DedeUserID=10002; SESSDATA=two")
    window.rooms_edit.setText("222")
    window.task_ids_edit.setText("task-two")
    window.start()
    window._apply_session_runtime_health(
        second.session_id,
        RuntimeHealth(state=ApplicationState.RUNNING),
    )

    assert first.controller.starts == 1
    assert second.controller.starts == 1
    assert first.controller.is_running
    assert second.controller.is_running
    labels = [
        window.cookie_profile_combo.itemText(index)
        for index in range(window.cookie_profile_combo.count())
    ]
    assert any("UID 10001" in label and "挂机中" in label for label in labels)
    assert any("UID 10002" in label and "挂机中" in label for label in labels)


def test_room_and_cookie_can_start_without_task_ids(window, monkeypatch) -> None:
    monkeypatch.setattr(window, "_schedule_live_watch_time_refresh", lambda: None)
    monkeypatch.setattr(window, "_schedule_task_refresh", lambda: None)
    discovery_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "auto_fetch_task_ids",
        lambda: discovery_calls.append(True),
    )

    controller = _FakeWorkerController()
    window._active_session.controller = controller
    window.cookie_edit.setText("DedeUserID=10001; SESSDATA=fixture")
    window.rooms_edit.setText("23612045")
    window.task_ids_edit.clear()

    window.start()

    assert controller.starts == 1
    assert controller.configs[0].room_ids == [23612045]
    assert controller.configs[0].task_ids == []
    assert discovery_calls == []
    assert "已直接开始挂机" in window.discovery_status_label.text()
    assert "任务进度和自动领奖暂不可用" in window.task_table.item(0, 0).text()


def test_stop_all_accounts_targets_every_workspace(window) -> None:
    first = window._active_session
    first.controller = _FakeWorkerController()
    first.controller.is_running = True
    window.new_temporary_account()
    second = window._active_session
    second.controller = _FakeWorkerController()
    second.controller.is_running = True

    window._stop_all_account_sessions()

    assert first.controller.stop_requests == 1
    assert second.controller.stop_requests == 1


def test_scope_switch_applies_run_toggle_to_current_or_all_accounts(
    window,
    monkeypatch,
) -> None:
    first = window._active_session
    first.controller = _FakeWorkerController()
    first.cookie = "DedeUserID=10001; SESSDATA=one"
    first.rooms_text = "111"
    window.cookie_edit.setText(first.cookie)
    window.rooms_edit.setText(first.rooms_text)
    window.new_temporary_account()
    second = window._active_session
    second.controller = _FakeWorkerController()
    second.cookie = "DedeUserID=10002; SESSDATA=two"
    second.rooms_text = "222"
    window._restore_active_session()
    monkeypatch.setattr(window, "_schedule_task_refresh", lambda: None)

    window.apply_all_switch.setChecked(False)
    window.toggle_run_scope()
    assert not first.controller.is_running
    assert second.controller.is_running
    assert window.start_btn.text() == "停止"

    window.toggle_run_scope()
    assert not second.controller.is_running

    window.apply_all_switch.setChecked(True)
    window.toggle_run_scope()
    assert first.controller.is_running
    assert second.controller.is_running
    assert window.start_btn.text() == "停止"

    window.toggle_run_scope()
    assert not first.controller.is_running
    assert not second.controller.is_running


def test_scope_switch_applies_background_auto_to_current_or_all_accounts(
    window,
    monkeypatch,
) -> None:
    first = window._active_session
    first.cookie = "DedeUserID=10001; SESSDATA=one"
    window.cookie_edit.setText(first.cookie)
    window.new_temporary_account()
    second = window._active_session
    ticks: list[bool] = []
    monkeypatch.setattr(
        window,
        "_automatic_mining_tick",
        lambda: ticks.append(True),
    )

    window.apply_all_switch.setChecked(False)
    window.toggle_background_auto_scope()
    assert window._automatic_mining_session_ids == {second.session_id}
    assert window.enable_auto_btn.text() == "停止后台自动"

    window.toggle_background_auto_scope()
    assert not window._automatic_mining_session_ids

    window.apply_all_switch.setChecked(True)
    window.toggle_background_auto_scope()
    assert window._automatic_mining_session_ids == {
        first.session_id,
        second.session_id,
    }
    assert window.enable_auto_btn.text() == "停止后台自动"


def test_runtime_input_change_immediately_wakes_enabled_background_auto(
    window,
    monkeypatch,
) -> None:
    session = window._active_session
    session.next_automatic_check_at = 99_999_999_999.0
    window._automatic_mining_session_ids.add(session.session_id)
    ticks: list[bool] = []
    monkeypatch.setattr(
        window,
        "_automatic_mining_tick",
        lambda: ticks.append(True),
    )

    window.rooms_edit.setText("23612045")
    window.task_ids_edit.setText("task-a")
    window._on_runtime_inputs_changed()

    assert session.rooms_text == "23612045"
    assert session.task_ids_text == "task-a"
    assert session.next_automatic_check_at == 0.0


def test_expired_automatic_task_clears_stale_progress_and_stops_auto_runtime(
    window,
    monkeypatch,
) -> None:
    session = window._active_session
    session.controller = _FakeWorkerController()
    session.controller.is_running = True
    session.auto_started_runtime = True
    session.task_ids_text = "old-task"
    session.task_started_at = datetime(
        2026, 7, 29, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    session.task_ends_at = datetime(
        2026, 7, 30, 17, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    session.latest_task_snapshot = TaskSnapshot(
        progresses=(TaskProgress("old-task", "昨日任务", 3, 300, 300),)
    )
    window._automatic_mining_session_ids.add(session.session_id)
    stopped: list[str] = []

    def stop_account(target) -> None:
        stopped.append(target.session_id)
        target.controller.is_running = False

    monkeypatch.setattr(window, "_stop_account_session", stop_account)

    window._apply_automatic_account_check(
        AutomaticAccountCheckResult(
            session_id=session.session_id,
            selection=ScheduledTaskSelection(
                None,
                "expired",
                15 * 60,
            ),
            error="仅发现已结束任务",
        )
    )

    assert stopped == [session.session_id]
    assert session.task_ids_text == ""
    assert session.task_started_at is None
    assert session.task_ends_at is None
    assert not session.latest_task_snapshot.progresses
    assert "旧任务已结束" in session.discovery_status_text
