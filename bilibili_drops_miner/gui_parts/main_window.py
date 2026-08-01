from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import webbrowser
from dataclasses import replace
from datetime import datetime
from time import monotonic, time
from zoneinfo import ZoneInfo

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QLineEdit,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
    QTableWidgetItem,
)

from bilibili_drops_miner.client import BilibiliClient
from bilibili_drops_miner.account_settings import AccountSettings
from bilibili_drops_miner.automatic_mining import (
    AutomaticAccountCheckResult,
    ScheduledTaskSelection,
    all_task_rewards_claimed,
    all_tasks_completed,
    claimable_reward_task_ids,
    select_scheduled_task_group,
)
from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.credential_store import JsonCredentialStore
from bilibili_drops_miner.desktop_runtime import SingleInstanceGuard
from bilibili_drops_miner.domain import ApplicationState, RuntimeHealth, TaskSnapshot
from bilibili_drops_miner.gui_parts.app_style import configure_qt_app
from bilibili_drops_miner.gui_parts.account_sessions import (
    DEFAULT_DISCOVERY_HINT,
    AccountWorkspace,
    LoginState,
)
from bilibili_drops_miner.gui_parts.browser_actions import BrowserActions
from bilibili_drops_miner.gui_parts.config_io import (
    build_config_payload,
    load_stored_config_data,
    save_config_data,
    save_stored_config_data,
    values_from_config_data,
)
from bilibili_drops_miner.gui_parts.cookie_profiles import (
    CookieProfile,
    cookie_store_path,
    default_cookie_remark,
    extract_cookie_uid,
    load_cookie_profile_state,
    now_text,
    save_cookie_profiles,
)
from bilibili_drops_miner.gui_parts.concurrency_dialog import (
    ONE_TIME_BOOST_SESSIONS,
    PERSISTENT_HIGH_SESSIONS,
    choose_concurrency_boost_mode,
)
from bilibili_drops_miner.gui_parts.log_handler import QueueLogHandler
from bilibili_drops_miner.gui_parts.main_layout import (
    MainWindowCallbacks,
    build_main_window_layout,
)
from bilibili_drops_miner.gui_parts.qr_login_dialog import QrLoginDialog
from bilibili_drops_miner.gui_parts.styles import (
    BUTTON_STYLES,
    DISABLED_BUTTON_STYLE,
)
from bilibili_drops_miner.gui_parts.task_controller import TaskController
from bilibili_drops_miner.gui_parts.task_presenter import task_progress_table_rows
from bilibili_drops_miner.gui_parts.update_checker import (
    check_latest_release,
    normalize_version,
    should_check_update,
)
from bilibili_drops_miner.gui_parts.update_dialog import show_update_available_dialog
from bilibili_drops_miner.gui_parts.window_chrome import (
    install_window_chrome,
    tray_icon,
)
from bilibili_drops_miner.logging_utils import redact_sensitive_text, setup_logging
from bilibili_drops_miner.notifier import MultiPlatformNotifier
from bilibili_drops_miner.request_coordinator import (
    TASK_API_GROUP,
    looks_rate_limited,
)
from bilibili_drops_miner.runtime_state import (
    AutomationState,
    RunOwner,
    TaskPhase,
)
from bilibili_drops_miner.task_discovery import TaskDiscoveryService
from bilibili_drops_miner.utils import (
    parse_notification_urls,
    parse_room_ids,
    parse_task_ids,
)

try:
    from bilibili_drops_miner._version import (
        APP_VERSION,
        LATEST_RELEASE_API,
        RELEASES_URL,
        UPDATE_CHANNEL,
    )
except Exception:
    APP_VERSION = "0.0.0+dev"
    UPDATE_CHANNEL = "dev"
    LATEST_RELEASE_API = (
        "https://api.github.com/repos/JumpTwiceShou/bilidrop/releases/latest"
    )
    RELEASES_URL = "https://github.com/JumpTwiceShou/bilidrop/releases/latest"

OVERWATCH_ESPORTS_ROOM_ID = 23612045
AUTOMATIC_STEADY_GUARD_SECONDS = 15 * 60


def _normalize_version(value: str) -> str:
    return normalize_version(value)


class MinerGUI(QMainWindow):
    # Cross-thread UI dispatcher. Any background thread may emit this signal;
    # Qt auto-queues the call onto the GUI thread (sender lives in non-Qt thread).
    ui_call = Signal(object, tuple, dict)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Bilibili 直播掉宝助手 {APP_VERSION}")
        self.resize(1080, 820)
        self.setMinimumSize(760, 640)

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._ui_alive = True

        self._last_verbose: bool | None = None
        self._task_progress_result: str = ""
        self._live_watch_time_result: str = ""
        self._task_progress_pending: bool = False
        self._task_refresh_trigger_pending: bool = False
        self._cookie_profiles: list[CookieProfile] = []
        self._cookie_profile_loading = False
        self._account_switching = False
        self._account_sessions: dict[str, AccountWorkspace] = {}
        self._active_session_id = ""
        self._last_selected_credential_id = ""
        self._last_prompted_cookie = ""
        self._application_state = ApplicationState.IDLE
        self._latest_task_snapshot = TaskSnapshot()
        self._pending_start_after_discovery = False
        self._rediscovery_attempted_for_run = False
        self._automatic_mining_session_ids: set[str] = set()
        self._global_account_defaults = AccountSettings()
        self._exit_requested = False
        self._tray_icon: QSystemTrayIcon | None = None
        self.ui_call.connect(self._on_ui_call, Qt.QueuedConnection)

        self._build_layout()
        self._credential_store = JsonCredentialStore()
        self.browser_actions = BrowserActions(
            parent=self,
            show_warning=self._show_warning,
            show_error=self._show_error,
            post_ui_task=self._post_ui_task,
            set_room_id=self._apply_auto_room_id,
            set_cookie=self._apply_auto_cookie,
            set_task_ids=self._apply_auto_task_ids,
            get_room_ids=lambda: parse_room_ids(self.rooms_edit.text().strip()),
            get_cookie=lambda: self.cookie_edit.text().strip(),
            set_discovery_status=self._set_discovery_status,
            logger=logging.getLogger(__name__),
        )
        self._automatic_discovery_service = TaskDiscoveryService(
            cache_ttl_seconds=0
        )
        self._install_logging()
        self._load_stored_secrets()
        self._load_cookie_profiles()
        self._load_stored_settings_silent()
        self._setup_system_tray()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(120)
        self._log_timer.timeout.connect(self._flush_log_queue)
        self._log_timer.start()

        self._stop_poll_timer = QTimer(self)
        self._stop_poll_timer.setInterval(120)
        self._stop_poll_timer.timeout.connect(self._poll_worker_shutdown)

        self._task_refresh_timer = QTimer(self)
        self._task_refresh_timer.setSingleShot(True)
        self._task_refresh_timer.timeout.connect(self._schedule_task_refresh)

        self._live_watch_time_timer = QTimer(self)
        self._live_watch_time_timer.setSingleShot(True)
        # 保留空闲定时器仅用于兼容旧测试/关闭流程。主界面不再展示估算观看
        # 时长，也不再启动每 3 秒一次的额外查询。

        self._login_validation_timer = QTimer(self)
        self._login_validation_timer.setSingleShot(True)
        self._login_validation_timer.setInterval(400)
        self._login_validation_timer.timeout.connect(
            self._validate_saved_account_logins
        )
        self._login_validation_timer.start()

        self._automatic_mining_timer = QTimer(self)
        self._automatic_mining_timer.setInterval(30_000)
        self._automatic_mining_timer.timeout.connect(
            self._automatic_mining_tick
        )
        self._automatic_mining_timer.start()
        if self._automatic_mining_session_ids:
            QTimer.singleShot(1000, self._automatic_mining_tick)

        QTimer.singleShot(3000, self._check_update_silent)
        self._restore_active_session()
        self._update_global_run_controls()

    # ---------- layout ----------

    def _build_layout(self) -> None:
        widgets = build_main_window_layout(
            self,
            MainWindowCallbacks(
                auto_fetch_cookie=self.auto_fetch_cookie,
                auto_fetch_room_id=self.auto_fetch_room_id,
                auto_fetch_task_ids=self.auto_fetch_task_ids,
                auto_fetch_overwatch_esports=self.auto_fetch_overwatch_esports,
                toggle_run=self.toggle_run_scope,
                boost_concurrency=self.boost_concurrency_scope,
                load_config=self.load_config,
                save_config=self.save_config,
                select_cookie_profile=self._on_cookie_profile_selected,
                save_cookie_profile=self.save_cookie_profile,
                delete_cookie_profile=self.delete_cookie_profile,
                clear_logs=self.clear_logs,
                claim_rewards=self.claim_rewards,
                refresh_tasks=self.refresh_tasks,
                open_settings_log=self.open_settings_log,
                toggle_cookie_visibility=self._toggle_cookie_visibility,
                toggle_notify_visibility=self._toggle_notify_visibility,
                test_notification=self.test_notification,
                export_diagnostics=self.export_diagnostics,
            ),
        )
        self.cookie_edit = widgets.cookie_edit
        self.rooms_edit = widgets.rooms_edit
        self.task_ids_edit = widgets.task_ids_edit
        self.notify_urls_edit = widgets.notify_urls_edit
        self.cookie_profile_combo = widgets.cookie_profile_combo
        self.cookie_remark_edit = widgets.cookie_remark_edit
        self.threads_spin = widgets.threads_spin
        self.reconnect_spin = widgets.reconnect_spin
        self.task_interval_spin = widgets.task_interval_spin
        self.verbose_check = widgets.verbose_check
        self.disable_task_notify_check = widgets.disable_task_notify_check
        self.progress_bar = widgets.progress_bar
        self.task_table = widgets.task_table
        self.log_text = widgets.log_text
        self.settings_dialog = widgets.settings_dialog
        self.settings_tabs = widgets.settings_tabs
        self.settings_button = widgets.settings_button
        self.claim_rewards_btn = widgets.claim_rewards_btn
        self.start_btn = widgets.start_btn
        self.boost_concurrency_btn = widgets.boost_concurrency_btn
        self.apply_all_switch = widgets.apply_all_switch
        self.auto_mining_description = widgets.auto_mining_description
        self.concurrency_mode_combo = widgets.concurrency_mode_combo
        self.minimize_to_tray_check = widgets.minimize_to_tray_check
        self.close_to_tray_check = widgets.close_to_tray_check
        self.auto_check_updates_check = widgets.auto_check_updates_check
        self.discover_btn = widgets.discover_btn
        self.overwatch_esports_btn = widgets.overwatch_esports_btn
        self.cookie_reveal_btn = widgets.cookie_reveal_btn
        self.save_cookie_profile_btn = widgets.save_cookie_profile_btn
        self.delete_cookie_profile_btn = widgets.delete_cookie_profile_btn
        self.notify_reveal_btn = widgets.notify_reveal_btn
        self.runtime_state_label = widgets.runtime_state_label
        self.runtime_detail_label = widgets.runtime_detail_label
        self.discovery_status_label = widgets.discovery_status_label
        self.watch_time_label = widgets.watch_time_label
        self.cookie_edit.editingFinished.connect(self._prompt_save_new_cookie)
        self.rooms_edit.editingFinished.connect(
            self._on_runtime_inputs_changed
        )
        self.task_ids_edit.editingFinished.connect(
            self._on_runtime_inputs_changed
        )
        self.apply_all_switch.toggled.connect(
            self._on_apply_all_scope_changed
        )

    @property
    def _active_session(self) -> AccountWorkspace:
        session = self._account_sessions.get(self._active_session_id)
        if session is None:
            raise RuntimeError("当前没有可用的账号工作区")
        return session

    @property
    def worker_controller(self):
        return self._active_session.controller

    @property
    def task_controller(self) -> TaskController:
        controller = self._active_session.task_controller
        if controller is None:
            raise RuntimeError("账号任务控制器尚未初始化")
        return controller

    def _register_account_session(self, session: AccountWorkspace) -> AccountWorkspace:
        self._account_sessions[session.session_id] = session
        session_id = session.session_id

        def _get_session() -> AccountWorkspace | None:
            return self._account_sessions.get(session_id)

        def _get_rooms() -> list[int]:
            current = _get_session()
            if current is None:
                return []
            try:
                return parse_room_ids(current.rooms_text)
            except ValueError:
                return []

        def _get_tasks() -> list[str]:
            current = _get_session()
            return parse_task_ids(current.task_ids_text) if current else []

        session.task_controller = TaskController(
            get_cookie=lambda: (_get_session().cookie if _get_session() else ""),
            get_room_ids=_get_rooms,
            get_task_ids=_get_tasks,
            show_warning=lambda title, message: self._show_session_warning(
                session_id, title, message
            ),
            set_task_progress_text=lambda text: self._set_session_task_progress_text(
                session_id, text
            ),
            set_task_snapshot=lambda snapshot: self._apply_session_task_snapshot(
                session_id, snapshot
            ),
            set_live_watch_time_text=lambda text: self._set_session_live_watch_time_text(
                session_id, text
            ),
            complete_task_refresh=lambda text, rerun: self._complete_session_task_refresh(
                session_id, text, rerun
            ),
            post_ui_task=self._post_ui_task,
            runtime_is_running=lambda: session.controller.is_running,
            request_runtime_refresh=session.controller.request_task_refresh,
            claim_runtime_rewards=session.controller.claim_rewards,
            request_coordinator=session.request_coordinator,
        )
        if (
            hasattr(self, "apply_all_switch")
            and self.apply_all_switch.isChecked()
            and self._automatic_mining_session_ids
        ):
            self._automatic_mining_session_ids.add(session.session_id)
            session.automation_state = AutomationState.ARMED
            session.automatic_guard_started_at = monotonic()
            session.next_automatic_check_at = 0.0
        return session

    def _show_session_warning(self, session_id: str, title: str, message: str) -> None:
        if session_id == self._active_session_id:
            self._show_warning(title, message)
        else:
            logging.getLogger(__name__).warning(
                "账号 %s: %s", self._account_sessions[session_id].uid, message
            )

    def _capture_active_session(
        self,
        *,
        preserve_account_fields: bool = False,
    ) -> None:
        if self._account_switching:
            return
        session = self._account_sessions.get(self._active_session_id)
        if session is None:
            return
        previous_cookie = session.cookie
        previous_rooms = session.rooms_text
        previous_task_ids = session.task_ids_text
        if not preserve_account_fields:
            cookie = self.cookie_edit.text().strip()
            if cookie != session.cookie:
                session.login_check_generation += 1
                session.login_state = LoginState.UNKNOWN
                self._update_account_selector_label(session)
            session.cookie = cookie
            session.remark = self.cookie_remark_edit.text().strip()
        session.rooms_text = self.rooms_edit.text().strip()
        session.task_ids_text = self.task_ids_edit.text().strip()
        session.thread_count = self.threads_spin.value()
        session.reconnect_delay_seconds = self.reconnect_spin.value()
        session.task_query_interval_seconds = self.task_interval_spin.value()
        session.notify_on_task_complete = not self.disable_task_notify_check.isChecked()
        session.concurrency_mode = str(
            self.concurrency_mode_combo.currentData() or "fixed"
        )
        session.application_state = self._application_state
        session.latest_task_snapshot = self._latest_task_snapshot
        session.task_progress_result = self._task_progress_result
        session.live_watch_time_result = self._live_watch_time_result
        session.pending_start_after_discovery = self._pending_start_after_discovery
        session.rediscovery_attempted_for_run = self._rediscovery_attempted_for_run
        session.discovery_status_text = self.discovery_status_label.text()
        if (
            previous_cookie != session.cookie
            or previous_rooms != session.rooms_text
            or previous_task_ids != session.task_ids_text
        ):
            session.bump_configuration_generation()

    @staticmethod
    def _account_settings_from_session(
        session: AccountWorkspace,
    ) -> AccountSettings:
        return AccountSettings(
            rooms_text=session.rooms_text,
            thread_count=session.thread_count,
            reconnect_delay_seconds=session.reconnect_delay_seconds,
            task_query_interval_seconds=session.task_query_interval_seconds,
            notify_on_task_complete=session.notify_on_task_complete,
            concurrency_mode=session.concurrency_mode,
        )

    @staticmethod
    def _apply_account_settings(
        session: AccountWorkspace,
        settings: AccountSettings,
    ) -> None:
        session.rooms_text = settings.rooms_text
        session.thread_count = settings.thread_count
        session.reconnect_delay_seconds = settings.reconnect_delay_seconds
        session.task_query_interval_seconds = (
            settings.task_query_interval_seconds
        )
        session.notify_on_task_complete = settings.notify_on_task_complete
        session.concurrency_mode = settings.concurrency_mode

    def _sync_cookie_profile_settings(self) -> None:
        for profile in self._cookie_profiles:
            session = next(
                (
                    item
                    for item in self._account_sessions.values()
                    if (
                        item.credential_id
                        and item.credential_id == profile.credential_id
                    )
                    or item.cookie == profile.cookie
                ),
                None,
            )
            if session is None or not session.account_settings_saved:
                continue
            profile.settings = self._account_settings_from_session(
                session
            ).to_mapping()

    def _restore_active_session(self) -> None:
        session = self._active_session
        self._account_switching = True
        try:
            self.cookie_edit.setText(session.cookie)
            self.cookie_remark_edit.setText(session.remark)
            self.rooms_edit.setText(session.rooms_text)
            self.task_ids_edit.setText(session.task_ids_text)
            self.threads_spin.setValue(session.thread_count)
            self.reconnect_spin.setValue(session.reconnect_delay_seconds)
            self.task_interval_spin.setValue(session.task_query_interval_seconds)
            mode_index = self.concurrency_mode_combo.findData(
                session.concurrency_mode
            )
            self.concurrency_mode_combo.setCurrentIndex(
                max(0, mode_index)
            )
            self.disable_task_notify_check.setChecked(
                not session.notify_on_task_complete
            )
            self._application_state = session.application_state
            self._latest_task_snapshot = session.latest_task_snapshot
            self._task_progress_result = session.task_progress_result
            self._live_watch_time_result = session.live_watch_time_result
            self._pending_start_after_discovery = (
                session.pending_start_after_discovery
            )
            self._rediscovery_attempted_for_run = (
                session.rediscovery_attempted_for_run
            )
            self.discovery_status_label.setText(session.discovery_status_text)
            self._set_discovery_status_style(session.discovery_status_error)
            self._render_runtime_health(session.runtime_health)
            self._render_task_snapshot(session.latest_task_snapshot)
            if (
                not session.latest_task_snapshot.error
                and not session.latest_task_snapshot.progresses
                and session.task_progress_result
            ):
                self._show_task_message(self._build_task_progress_text())
            self.watch_time_label.clear()
        finally:
            self._account_switching = False

        self._task_refresh_timer.stop()
        self._live_watch_time_timer.stop()
        if session.controller.is_running and not session.controller.stop_signal_set:
            self._schedule_task_refresh()

    def _activate_account_session(
        self,
        session_id: str,
        *,
        remember_saved: bool = True,
    ) -> None:
        if session_id not in self._account_sessions:
            return
        if session_id == self._active_session_id:
            self._refresh_cookie_profile_combo(selected_session_id=session_id)
            self._restore_active_session()
            return
        self._capture_active_session()
        self._active_session_id = session_id
        session = self._active_session
        if remember_saved and not session.temporary and session.credential_id:
            self._last_selected_credential_id = session.credential_id
            try:
                self._write_cookie_profiles()
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "最近使用账号保存失败: %s", exc
                )
        self._refresh_cookie_profile_combo(selected_session_id=session_id)
        self._restore_active_session()
        logging.getLogger(__name__).info("已切换账号: UID %s", session.uid or "未知")

    def test_notification(self) -> None:
        urls = parse_notification_urls(self.notify_urls_edit.text().strip())
        if not urls:
            self._show_warning("提示", "请先填写通知地址")
            return

        def _do() -> None:
            notifier = MultiPlatformNotifier(urls)
            sent = notifier.notify(
                title="BiliDrop 通知测试",
                body="如果你看到这条消息，通知配置已生效。",
            )
            self._post_ui_task(
                self._show_info if sent else self._show_warning,
                "通知测试",
                "发送成功" if sent else "发送失败，请检查地址和运行日志",
            )

        threading.Thread(
            target=_do,
            daemon=True,
            name="gui-notification-test",
        ).start()

    def export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出脱敏诊断",
            "bilidrop-diagnostics.json",
            "JSON 文件 (*.json)",
        )
        if not path:
            return
        health = self.worker_controller.miner.health if self.worker_controller.miner else RuntimeHealth()
        try:
            room_ids = parse_room_ids(self.rooms_edit.text().strip())
        except ValueError:
            room_ids = []
        payload = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "app_version": APP_VERSION,
            "state": health.state.value,
            "room_ids": room_ids,
            "sessions": {
                "active": health.active_sessions,
                "target": health.target_sessions,
                "reconnect_count": health.reconnect_count,
            },
            "last_heartbeat_at": health.last_heartbeat_at,
            "last_error": redact_sensitive_text(health.last_error),
            "task_count": len(self._latest_task_snapshot.progresses),
            "task_completed_count": self._latest_task_snapshot.completed_count,
            "task_refreshed_at": self._latest_task_snapshot.refreshed_at,
            "task_error": redact_sensitive_text(self._latest_task_snapshot.error),
            "secrets_redacted": True,
        }
        try:
            save_config_data(path, payload)
            self._show_info("导出完成", "脱敏诊断已保存；不包含 Cookie 或通知地址。")
        except Exception as exc:
            self._show_error("导出失败", str(exc))

    # ---------- logging / cross-thread ----------

    def _install_logging(self) -> None:
        queue_handler = QueueLogHandler(self.log_queue)
        setup_logging(
            verbose=self.verbose_check.isChecked(),
            no_color=True,
            extra_handlers=[queue_handler],
        )

    def _post_ui_task(self, callback, *args, **kwargs) -> None:
        """Thread-safe dispatch onto the GUI thread. Drop-in replacement for the
        original Tk-era helper; all workers keep calling this same API."""
        if not self._ui_alive:
            return
        self.ui_call.emit(callback, args, kwargs)

    def _on_ui_call(self, fn, args, kwargs) -> None:
        if not self._ui_alive:
            return
        try:
            fn(*args, **kwargs)
        except Exception:
            logging.getLogger(__name__).exception("UI 任务执行失败")

    def _flush_log_queue(self) -> None:
        if not self._ui_alive:
            return
        # Drain the log queue in a single batch; appendPlainText per line is
        # still cheap for the 120ms tick, far cheaper than canvas redraws.
        lines: list[str] = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if lines:
            scroll_bar = self.log_text.verticalScrollBar()
            scroll_value = scroll_bar.value()
            self.log_text.appendPlainText("\n".join(lines))
            scroll_bar.setValue(min(scroll_value, scroll_bar.maximum()))

        if self._task_progress_pending:
            self._task_progress_pending = False
            self._show_task_message(self._build_task_progress_text())

        if self._task_refresh_trigger_pending:
            self._task_refresh_trigger_pending = False
            self.refresh_tasks(manual=False)

    # ---------- message helpers (main thread only) ----------

    def _show_info(self, title: str, msg: str) -> None:
        QMessageBox.information(self, title, msg)

    def _show_warning(self, title: str, msg: str) -> None:
        QMessageBox.warning(self, title, msg)

    def _show_error(self, title: str, msg: str) -> None:
        QMessageBox.critical(self, title, msg)

    # ---------- cookie profiles ----------

    def _load_cookie_profiles(self) -> None:
        try:
            state = load_cookie_profile_state(
                credential_store=self._credential_store
            )
            self._cookie_profiles = state.profiles
            self._last_selected_credential_id = (
                state.last_selected_credential_id
            )
        except Exception as exc:
            self._cookie_profiles = []
            self._last_selected_credential_id = ""
            logging.getLogger(__name__).warning("Cookie档案加载失败: %s", exc)

        for profile in self._cookie_profiles:
            session = AccountWorkspace.saved_account(
                credential_id=profile.credential_id,
                cookie=profile.cookie,
                remark=profile.remark,
            )
            account_settings = AccountSettings.from_mapping(profile.settings)
            if account_settings is not None:
                self._apply_account_settings(session, account_settings)
                session.account_settings_saved = True
            self._register_account_session(session)

        selected = next(
            (
                session.session_id
                for session in self._account_sessions.values()
                if session.credential_id == self._last_selected_credential_id
            ),
            "",
        )
        if not selected and self._account_sessions:
            selected = next(iter(self._account_sessions))
        if not selected:
            selected = self._register_account_session(
                AccountWorkspace.temporary_account()
            ).session_id
        self._active_session_id = selected
        self._refresh_cookie_profile_combo(selected_session_id=selected)

    def _load_stored_secrets(self) -> None:
        try:
            if not self.notify_urls_edit.text().strip():
                self.notify_urls_edit.setText(
                    self._credential_store.get("notification-urls")
                )
            # v2 曾把未保存 Cookie 当作“上次使用”持久化。迁移时主动删除，
            # 保证临时账号关闭程序后真的消失。
            self._credential_store.delete("last-cookie")
        except Exception as exc:
            logging.getLogger(__name__).warning("受保护凭据加载失败: %s", exc)

    def _validate_saved_account_logins(self) -> None:
        for session in tuple(self._account_sessions.values()):
            if session.temporary or not session.cookie or session.controller.is_running:
                continue
            self._begin_account_login_validation(session)

    def _begin_account_login_validation(
        self,
        session: AccountWorkspace,
    ) -> None:
        if not session.cookie or session.controller.is_running:
            return
        session.login_check_generation += 1
        generation = session.login_check_generation
        session.login_state = LoginState.CHECKING
        self._update_account_selector_label(session)
        session_id = session.session_id
        cookie = session.cookie

        def _do() -> None:
            async def _probe():
                client = BilibiliClient(cookie)
                try:
                    return await asyncio.wait_for(
                        client.get_self_info(),
                        timeout=20,
                    )
                finally:
                    await client.close()

            state = LoginState.ERROR
            detected_uid = ""
            permit = session.request_coordinator.acquire(
                "login-validation",
                group="auth-api",
                timeout_seconds=5.0,
            )
            validation_error: BaseException | None = None
            try:
                if permit is None:
                    raise RuntimeError("登录校验请求正在执行或冷却中")
                uid, _uname = asyncio.run(_probe())
                if uid:
                    state = LoginState.VALID
                    detected_uid = str(uid)
                else:
                    state = LoginState.INVALID
            except Exception as exc:
                validation_error = exc
                detail = str(exc).strip() or type(exc).__name__
                logging.getLogger(__name__).warning(
                    "账号登录状态检测失败 UID %s: %s",
                    session.uid or "未知",
                    detail,
                )
            finally:
                if permit is not None:
                    session.request_coordinator.finish(
                        permit,
                        cooldown_seconds=(
                            30.0
                            if validation_error is not None
                            and looks_rate_limited(validation_error)
                            else 0.0
                        ),
                    )
            self._post_ui_task(
                self._apply_account_login_state,
                session_id,
                generation,
                state,
                detected_uid,
            )

        threading.Thread(
            target=_do,
            daemon=True,
            name=f"gui-login-check-{session.uid or 'unknown'}",
        ).start()

    def _apply_account_login_state(
        self,
        session_id: str,
        generation: int,
        state: LoginState,
        detected_uid: str,
    ) -> None:
        session = self._account_sessions.get(session_id)
        if session is None or generation != session.login_check_generation:
            return
        expected_uid = session.uid
        if (
            state == LoginState.VALID
            and expected_uid
            and detected_uid
            and expected_uid != detected_uid
        ):
            state = LoginState.INVALID
        session.login_state = state
        self._update_account_selector_label(session)

    def _store_current_secrets(self) -> None:
        notify_urls = self.notify_urls_edit.text().strip()
        self._credential_store.delete("last-cookie")
        if notify_urls:
            self._credential_store.set("notification-urls", notify_urls)
        else:
            self._credential_store.delete("notification-urls")

    def _write_cookie_profiles(self) -> None:
        self._sync_cookie_profile_settings()
        save_cookie_profiles(
            self._cookie_profiles,
            credential_store=self._credential_store,
            last_selected_credential_id=self._last_selected_credential_id,
        )

    def _backup_cookie_profiles(self, reason: str) -> bool:
        store = self._credential_store
        backup = getattr(store, "backup", None)
        if not callable(backup):
            return True
        try:
            backup_path = backup(reason)
            if backup_path is not None:
                logging.getLogger(__name__).info(
                    "账号档案加密备份已创建: %s",
                    backup_path,
                )
            return True
        except Exception as exc:
            self._show_error(
                "账号备份失败",
                f"为避免账号档案丢失，本次操作已取消：{exc}",
            )
            return False

    def _refresh_cookie_profile_combo(
        self,
        *,
        selected_session_id: str | None = None,
    ) -> None:
        selected_session_id = selected_session_id or self._active_session_id
        self._cookie_profile_loading = True
        try:
            self.cookie_profile_combo.clear()
            selected_index = 0
            sessions = sorted(
                self._account_sessions.values(),
                key=lambda session: session.temporary,
            )
            for idx, session in enumerate(sessions):
                self.cookie_profile_combo.addItem(
                    session.selector_label,
                    session.session_id,
                )
                self.cookie_profile_combo.setItemData(
                    idx,
                    session.hint_text,
                    Qt.ToolTipRole,
                )
                if session.session_id == selected_session_id:
                    selected_index = idx
            if sessions:
                self.cookie_profile_combo.setCurrentIndex(selected_index)
        finally:
            self._cookie_profile_loading = False

    def _update_account_selector_label(self, session: AccountWorkspace) -> None:
        for index in range(self.cookie_profile_combo.count()):
            if self.cookie_profile_combo.itemData(index) == session.session_id:
                self.cookie_profile_combo.setItemText(index, session.selector_label)
                self.cookie_profile_combo.setItemData(
                    index,
                    session.hint_text,
                    Qt.ToolTipRole,
                )
                break

    def _selected_cookie_profile_index(self) -> int | None:
        credential_id = self._active_session.credential_id
        for index, profile in enumerate(self._cookie_profiles):
            if credential_id and profile.credential_id == credential_id:
                return index
        return None

    def _has_cookie_profile(self, cookie: str) -> bool:
        return any(profile.cookie == cookie for profile in self._cookie_profiles)

    def _cookie_profile_index_for_uid(self, uid: str) -> int | None:
        uid = uid.strip()
        if not uid:
            return None
        for index, profile in enumerate(self._cookie_profiles):
            if extract_cookie_uid(profile.cookie) == uid:
                return index
        return None

    def _session_for_cookie(self, cookie: str) -> AccountWorkspace | None:
        return next(
            (
                session
                for session in self._account_sessions.values()
                if session.cookie == cookie
            ),
            None,
        )

    def _session_for_credential(
        self,
        credential_id: str,
    ) -> AccountWorkspace | None:
        return next(
            (
                session
                for session in self._account_sessions.values()
                if credential_id and session.credential_id == credential_id
            ),
            None,
        )

    def _adopt_cookie_for_active_session(self, cookie: str) -> AccountWorkspace:
        cookie = cookie.strip()
        existing = self._session_for_cookie(cookie) if cookie else None
        if existing is not None and existing.session_id != self._active_session_id:
            self._activate_account_session(existing.session_id)
            return existing

        current = self._active_session
        occupied = bool(
            current.cookie
            or current.rooms_text
            or current.task_ids_text
            or current.latest_task_snapshot.progresses
            or current.task_progress_result
            or current.controller.is_running
            or not current.temporary
        )
        if cookie != current.cookie and occupied:
            current = self._register_account_session(
                AccountWorkspace.temporary_account(cookie=cookie)
            )
            self._activate_account_session(current.session_id, remember_saved=False)
        else:
            current.cookie = cookie
            self.cookie_edit.setText(cookie)
            self._refresh_cookie_profile_combo(selected_session_id=current.session_id)
        return current

    def new_temporary_account(self) -> None:
        self._capture_active_session()
        current = self._active_session
        if (
            current.temporary
            and not current.cookie
            and not current.controller.is_running
            and not current.rooms_text
            and not current.task_ids_text
            and not current.latest_task_snapshot.progresses
            and not current.task_progress_result
        ):
            self._activate_account_session(
                current.session_id,
                remember_saved=False,
            )
            return
        session = self._register_account_session(
            AccountWorkspace.temporary_account()
        )
        self._activate_account_session(session.session_id, remember_saved=False)

    def _confirm_save_new_cookie(self, profile_name: str) -> bool:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("保存账号档案")
        msg.setText("检测到新的 Cookie，是否保存为账号档案？")
        msg.setInformativeText(f"档案名称：{profile_name}")
        save_button = msg.addButton("保存", QMessageBox.AcceptRole)
        msg.addButton("暂不保存", QMessageBox.RejectRole)
        msg.setDefaultButton(save_button)
        msg.exec()
        return msg.clickedButton() == save_button

    def _prompt_save_new_cookie(self, cookie: str | None = None) -> None:
        cookie = (cookie if cookie is not None else self.cookie_edit.text()).strip()
        if not cookie:
            self._active_session.cookie = ""
            self._refresh_cookie_profile_combo()
            return
        session = self._adopt_cookie_for_active_session(cookie)
        if not session.remark:
            session.remark = self.cookie_remark_edit.text().strip()
        if not session.temporary or cookie == self._last_prompted_cookie:
            return

        self._last_prompted_cookie = cookie
        entered_remark = self.cookie_remark_edit.text().strip()
        profile_name = entered_remark or default_cookie_remark(cookie)
        if not self._confirm_save_new_cookie(profile_name):
            return
        if not entered_remark:
            self.cookie_remark_edit.setText(profile_name)
        self.save_cookie_profile()

    def _find_cookie_profile_to_update(self, cookie: str, remark: str) -> int | None:
        selected_index = self._selected_cookie_profile_index()
        if selected_index is not None:
            return selected_index
        for idx, item in enumerate(self._cookie_profiles):
            if item.cookie == cookie or item.remark == remark:
                return idx
        return None

    def _ask_cookie_profile_save_action(self, existing: CookieProfile) -> str:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Cookie档案已存在")
        msg.setText(f"已存在 Cookie 档案：{existing.remark}")
        msg.setInformativeText("请选择覆盖已有档案，还是新建一个档案。")
        overwrite_button = msg.addButton("覆盖", QMessageBox.AcceptRole)
        create_button = msg.addButton("新建", QMessageBox.ActionRole)
        cancel_button = msg.addButton("取消", QMessageBox.RejectRole)
        msg.setDefaultButton(overwrite_button)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == overwrite_button:
            return "overwrite"
        if clicked == create_button:
            return "create"
        if clicked == cancel_button:
            return "cancel"
        return "cancel"

    def _on_cookie_profile_selected(self, index: int) -> None:
        if self._cookie_profile_loading or index < 0:
            return
        session_id = str(self.cookie_profile_combo.itemData(index) or "")
        if session_id not in self._account_sessions:
            return
        self._activate_account_session(session_id)

    def save_cookie_profile(self) -> None:
        self._capture_active_session()
        session = self._active_session
        cookie = self.cookie_edit.text().strip()
        if not cookie:
            self._show_warning("提示", "请先填写 Cookie")
            return
        remark = self.cookie_remark_edit.text().strip() or default_cookie_remark(cookie)
        profile = CookieProfile(
            remark=remark,
            cookie=cookie,
            updated_at=now_text(),
            credential_id=session.credential_id,
            settings=self._account_settings_from_session(session).to_mapping(),
        )

        target_index = self._find_cookie_profile_to_update(cookie, remark)
        selected_index = self._selected_cookie_profile_index()
        overwritten_session: AccountWorkspace | None = None
        if target_index is not None and target_index != selected_index:
            existing = self._cookie_profiles[target_index]
            action = self._ask_cookie_profile_save_action(
                existing
            )
            if action == "cancel":
                return
            if action == "create":
                target_index = None
            else:
                overwritten_session = self._session_for_credential(
                    existing.credential_id
                )
                if overwritten_session and overwritten_session.controller.is_running:
                    self._show_warning("运行中", "该账号正在挂机，请先停止后再覆盖。")
                    return
                profile.credential_id = existing.credential_id

        old_profiles = list(self._cookie_profiles)
        if not self._backup_cookie_profiles(
            "overwrite" if target_index is not None else "save"
        ):
            return
        if target_index is None:
            self._cookie_profiles.append(profile)
        else:
            self._cookie_profiles[target_index] = profile

        try:
            self._last_selected_credential_id = profile.credential_id
            self._write_cookie_profiles()
            session.cookie = cookie
            session.remark = remark
            session.credential_id = profile.credential_id
            session.temporary = False
            session.account_settings_saved = True
            self._last_selected_credential_id = profile.credential_id
            # 第一次保存时 credential_id 由存储层生成，需要再写一次才能记录“最近使用”。
            self._write_cookie_profiles()
            if (
                overwritten_session is not None
                and overwritten_session.session_id != session.session_id
            ):
                self._account_sessions.pop(overwritten_session.session_id, None)
                self._automatic_mining_session_ids.discard(
                    overwritten_session.session_id
                )
            self.cookie_remark_edit.setText(remark)
            self._refresh_cookie_profile_combo(selected_session_id=session.session_id)
            self._last_prompted_cookie = ""
            logging.getLogger(__name__).info("Cookie已保存到 %s", cookie_store_path())
        except Exception as exc:
            self._cookie_profiles = old_profiles
            self._show_error("保存Cookie失败", str(exc))

    def delete_cookie_profile(self) -> None:
        self._capture_active_session()
        session = self._active_session
        if session.controller.is_running:
            self._show_warning("运行中", "请先停止这个账号的挂机，再删除档案。")
            return

        target_index = self._selected_cookie_profile_index()
        profile = (
            self._cookie_profiles[target_index]
            if target_index is not None
            else None
        )
        old_profiles = list(self._cookie_profiles)
        old_last_selected = self._last_selected_credential_id
        if target_index is not None and not self._backup_cookie_profiles("delete"):
            return
        try:
            if target_index is not None:
                self._cookie_profiles.pop(target_index)
                if self._last_selected_credential_id == session.credential_id:
                    self._last_selected_credential_id = (
                        self._cookie_profiles[0].credential_id
                        if self._cookie_profiles
                        else ""
                    )
                self._write_cookie_profiles()
                if profile and profile.credential_id:
                    self._credential_store.delete(profile.credential_id)

            self._account_sessions.pop(session.session_id, None)
            self._automatic_mining_session_ids.discard(session.session_id)
            if not self._account_sessions:
                self._register_account_session(AccountWorkspace.temporary_account())
            next_session = next(
                (
                    item
                    for item in self._account_sessions.values()
                    if item.credential_id == self._last_selected_credential_id
                ),
                next(iter(self._account_sessions.values())),
            )
            self._active_session_id = next_session.session_id
            self._refresh_cookie_profile_combo(
                selected_session_id=next_session.session_id
            )
            self._restore_active_session()
            logging.getLogger(__name__).info(
                "已删除账号: %s",
                profile.remark if profile else "临时账号",
            )
        except Exception as exc:
            self._cookie_profiles = old_profiles
            self._last_selected_credential_id = old_last_selected
            self._show_error("删除Cookie失败", str(exc))

    # ---------- update check ----------

    def _check_update_silent(self) -> None:
        if (
            not self.auto_check_updates_check.isChecked()
            or not should_check_update(APP_VERSION, UPDATE_CHANNEL)
        ):
            return

        def _do() -> None:
            result = check_latest_release(
                app_version=APP_VERSION,
                update_channel=UPDATE_CHANNEL,
                latest_release_api=LATEST_RELEASE_API,
                releases_url=RELEASES_URL,
            )
            if result is None:
                return
            self._post_ui_task(
                self._show_update_available,
                result.latest_version,
                result.release_url,
            )

        threading.Thread(target=_do, daemon=True, name="gui-update-check").start()

    def _show_update_available(self, latest_version: str, release_url: str) -> None:
        if show_update_available_dialog(
            self,
            app_version=APP_VERSION,
            latest_version=latest_version,
            release_url=release_url,
        ):
            webbrowser.open(release_url)

    # ---------- config ----------

    def _build_config(self) -> MinerConfig:
        self._capture_active_session()
        return self._build_session_config(self._active_session)

    def _build_session_config(
        self,
        session: AccountWorkspace,
        *,
        automatic_start_in_steady_mode: bool = False,
        automatic_catchup_sessions: int | None = None,
    ) -> MinerConfig:
        runtime_override = session.runtime_concurrency_override
        thread_count = runtime_override or session.thread_count
        if (
            automatic_catchup_sessions is not None
            and runtime_override is None
            and session.concurrency_mode == "automatic"
        ):
            thread_count = automatic_catchup_sessions
        return MinerConfig(
            cookie=session.cookie.strip(),
            room_ids=parse_room_ids(session.rooms_text.strip()),
            thread_count=thread_count,
            reconnect_delay_seconds=session.reconnect_delay_seconds,
            enable_web_heartbeat=True,
            task_ids=parse_task_ids(session.task_ids_text.strip()),
            task_query_interval_seconds=session.task_query_interval_seconds,
            notify_urls=parse_notification_urls(self.notify_urls_edit.text().strip()),
            notify_on_task_complete=session.notify_on_task_complete,
            concurrency_mode=(
                "fixed"
                if runtime_override is not None
                else session.concurrency_mode
            ),
            task_started_at=session.task_started_at,
            automatic_start_in_steady_mode=(
                automatic_start_in_steady_mode
                and runtime_override is None
                and session.concurrency_mode == "automatic"
            ),
        )

    # ---------- start / stop ----------

    @staticmethod
    def _completion_run_key(
        task_ids: list[str] | tuple[str, ...],
    ) -> tuple[str, tuple[str, ...]] | None:
        normalized = tuple(dict.fromkeys(task_id for task_id in task_ids if task_id))
        if not normalized:
            return None
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return day, normalized

    def start(self) -> None:
        self._capture_active_session()
        self._start_continuous_scope(
            (self._active_session,),
            interactive=True,
        )

    def _start_account_session(
        self,
        session: AccountWorkspace,
        *,
        interactive: bool,
        automatic: bool = False,
        automatic_start_in_steady_mode: bool = False,
    ) -> bool:
        logger = logging.getLogger(__name__)
        session_id = session.session_id
        if session.controller.is_running:
            if interactive:
                self._show_info(
                    "运行中",
                    "这个账号已在挂机；可以切换到其他账号继续启动。",
                )
            return False
        try:
            self._install_logging()
            automatic_catchup_sessions = (
                32 if self._concurrent_account_count() == 1 else 16
            )
            config = self._build_session_config(
                session,
                automatic_start_in_steady_mode=(
                    automatic_start_in_steady_mode
                ),
                automatic_catchup_sessions=automatic_catchup_sessions,
            )
            config.validate()
            completion_key = self._completion_run_key(config.task_ids)
            session.completion_auto_stop_bypass = bool(
                not automatic
                and completion_key is not None
                and session.completion_auto_stop_key == completion_key
            )
        except Exception as exc:
            if interactive:
                self._show_error("配置错误", str(exc))
            else:
                logger.warning(
                    "账号 UID %s 未启动: %s",
                    session.uid or "未知",
                    exc,
                )
            return False
        if session.login_state != LoginState.VALID:
            if session.login_state == LoginState.INVALID:
                if interactive:
                    self._show_warning(
                        "登录已失效",
                        "这个账号的登录状态已经失效，请点击“扫码登录”重新登录后再开始挂机。",
                    )
                else:
                    logger.warning(
                        "账号 UID %s 登录已失效，持续任务检测已跳过",
                        session.uid or "未知",
                    )
                return False
            if session.login_state != LoginState.CHECKING:
                self._begin_account_login_validation(session)
            if interactive:
                self._show_warning(
                    "正在检测登录状态",
                    "需要先确认账号登录有效。请稍等片刻；如果显示登录失效，请重新扫码登录。",
                )
            return False
        previous_owner = session.run_owner
        previous_automation_state = session.automation_state
        session.run_owner = RunOwner.AUTO if automatic else RunOwner.MANUAL
        if automatic:
            session.automation_state = AutomationState.AUTO_RUNNING
        try:
            started = session.controller.start(
                config,
                logger=logger,
                on_health=lambda health: self._post_ui_task(
                    self._apply_session_runtime_health, session_id, health
                ),
                on_task_snapshot=lambda snapshot: self._post_ui_task(
                    self._apply_session_task_snapshot, session_id, snapshot
                ),
                on_rewards_settled=lambda task_ids: self._post_ui_task(
                    self._stop_runtime_after_rewards_claimed,
                    session_id,
                    task_ids,
                ),
                request_coordinator=session.request_coordinator,
            )
        except Exception as exc:
            session.run_owner = previous_owner
            session.automation_state = previous_automation_state
            logger.exception("账号 UID %s 启动失败", session.uid or "未知")
            if interactive:
                self._show_error("启动失败", str(exc).strip() or type(exc).__name__)
            return False
        if not started:
            session.run_owner = previous_owner
            session.automation_state = previous_automation_state
            if interactive:
                self._show_info("运行中", "这个账号已在挂机。")
            return False
        session.application_state = ApplicationState.STARTING
        session.runtime_health = RuntimeHealth(
            state=ApplicationState.STARTING,
            concurrency_mode=config.concurrency_mode,
            concurrency_phase=(
                (
                    "steady"
                    if config.automatic_start_in_steady_mode
                    else "catchup"
                )
                if config.concurrency_mode == "automatic"
                else "fixed"
            ),
            concurrency_detail=(
                (
                    "后台已守候至少 15 分钟，新任务先以每房间 2 个会话启动"
                    if config.automatic_start_in_steady_mode
                    else (
                        f"自动并发从每房间 {config.thread_count} 个会话"
                        "启动并收集任务进度"
                    )
                )
                if config.concurrency_mode == "automatic"
                else (
                    f"手动加速：每房间固定 {config.thread_count} 个会话"
                    if session.runtime_concurrency_override is not None
                    else f"固定并发：每房间 {config.thread_count} 个会话"
                )
            ),
        )
        session.pending_start_after_discovery = False
        session.rediscovery_attempted_for_run = False
        if session_id == self._active_session_id:
            self._set_application_state(ApplicationState.STARTING)
            self._pending_start_after_discovery = False
            self._rediscovery_attempted_for_run = False
        logger.info(
            "账号 UID %s 的掉宝助手已启动（所有者: %s，触发: %s）",
            session.uid or "未知",
            session.run_owner.value,
            (
                "后台守候发现任务"
                if automatic_start_in_steady_mode
                else "后台立即启动" if automatic else "用户手动启动"
            ),
        )
        if session.completion_auto_stop_bypass:
            message = (
                "平台此前已把这组当天奖励判定为全部领取；"
                "已按你的要求继续挂机，本次不会自动暂停，请手动停止"
            )
            session.discovery_status_text = message
            logger.warning("账号 UID %s：%s", session.uid or "未知", message)
            if interactive:
                self._show_info("继续挂机", message)
            if session_id == self._active_session_id:
                self._set_discovery_status(message, False)
        if not config.task_ids:
            message = "未识别任务，已直接开始挂机；任务进度和自动领奖暂不可用"
            session.discovery_status_text = message
            if session_id == self._active_session_id:
                self._set_discovery_status(message, False)
                self._show_task_message(message)
            logger.info(message)
        if session_id == self._active_session_id:
            self._start_progress_animation()
        self._update_global_run_controls()
        return True

    def stop(self) -> None:
        self._capture_active_session()
        self._stop_continuous_scope((self._active_session,))

    def _stop_account_session(self, session: AccountWorkspace) -> None:
        logger = logging.getLogger(__name__)
        is_active = session.session_id == self._active_session_id
        if is_active:
            self._stop_progress_animation()
            self._task_refresh_timer.stop()
            self._live_watch_time_timer.stop()
        session.task_controller.stop_live_watch_time()
        result = session.controller.request_stop(logger=logger)
        if result == "stopping_started":
            session.application_state = ApplicationState.STOPPING
            if is_active:
                self._set_application_state(ApplicationState.STOPPING)
            self._stop_poll_timer.start()
        elif result == "not_running":
            session.application_state = ApplicationState.IDLE
            session.run_owner = RunOwner.NONE
            session.runtime_concurrency_override = None
            if is_active:
                self._set_application_state(ApplicationState.IDLE)
        self._refresh_cookie_profile_combo(selected_session_id=session.session_id)
        self._update_global_run_controls()

    def start_all(self) -> None:
        self._capture_active_session()
        template = self._active_session
        started = 0
        skipped = 0
        for session in tuple(self._account_sessions.values()):
            if not session.cookie.strip():
                skipped += 1
                continue
            if not session.rooms_text.strip():
                session.rooms_text = template.rooms_text
                session.task_ids_text = template.task_ids_text
                session.thread_count = template.thread_count
                session.reconnect_delay_seconds = (
                    template.reconnect_delay_seconds
                )
                session.task_query_interval_seconds = (
                    template.task_query_interval_seconds
                )
                session.notify_on_task_complete = (
                    template.notify_on_task_complete
                )
                session.concurrency_mode = template.concurrency_mode
            if self._start_account_session(session, interactive=False):
                started += 1
            else:
                skipped += 1
        logging.getLogger(__name__).info(
            "全部开始完成: 新启动 %s 个账号，跳过 %s 个账号",
            started,
            skipped,
        )
        self._update_global_run_controls()

    def stop_all(self) -> None:
        self._capture_active_session()
        for session in tuple(self._account_sessions.values()):
            self._stop_account_session(session)
        logging.getLogger(__name__).info("已请求停止全部账号")

    def _scope_sessions(self) -> tuple[AccountWorkspace, ...]:
        if self.apply_all_switch.isChecked():
            return tuple(self._account_sessions.values())
        return (self._active_session,)

    def _concurrent_account_count(self) -> int:
        """Count accounts that can participate in this run decision."""
        return max(
            1,
            sum(
                1
                for session in self._account_sessions.values()
                if session.controller.is_running
                or (
                    session.cookie.strip()
                    and (
                        session.login_state == LoginState.VALID
                        or session.session_id
                        in self._automatic_mining_session_ids
                    )
                )
            ),
        )

    def _boostable_scope_sessions(self) -> tuple[AccountWorkspace, ...]:
        return tuple(
            session
            for session in self._scope_sessions()
            if session.cookie.strip() or session.controller.is_running
        )

    def toggle_run_scope(self) -> None:
        self._capture_active_session()
        sessions = self._scope_sessions()
        if any(session.controller.is_running for session in sessions):
            self._stop_continuous_scope(sessions)
        else:
            self._start_continuous_scope(
                sessions,
                interactive=len(sessions) == 1,
            )
        self._update_global_run_controls()

    def _start_continuous_scope(
        self,
        sessions: tuple[AccountWorkspace, ...],
        *,
        interactive: bool,
    ) -> None:
        if not sessions:
            return
        template = self._active_session
        now = monotonic()
        for session in sessions:
            self._seed_session_runtime_config(session, template)
            if session.session_id not in self._automatic_mining_session_ids:
                session.automatic_guard_started_at = now
            session.automation_state = AutomationState.ARMED
            session.next_automatic_check_at = 0.0
            self._automatic_mining_session_ids.add(session.session_id)
        for session in sessions:
            started = self._start_account_session(
                session,
                interactive=interactive,
            )
            if started or session.login_state == LoginState.CHECKING:
                continue
            self._automatic_mining_session_ids.discard(session.session_id)
            session.automatic_guard_started_at = None
            session.automation_state = AutomationState.OFF
        logging.getLogger(__name__).info(
            "持续挂机已开启，作用范围：%s；全部领奖后关闭观看线程并保留任务检测",
            "所有账号" if len(sessions) > 1 else "当前账号",
        )
        QTimer.singleShot(0, self._automatic_mining_tick)

    def _stop_continuous_scope(
        self,
        sessions: tuple[AccountWorkspace, ...],
        *,
        disable_monitoring: bool = False,
    ) -> None:
        session_ids = {session.session_id for session in sessions}
        if disable_monitoring:
            self._automatic_mining_session_ids.difference_update(session_ids)
        stopped = 0
        for session in sessions:
            if disable_monitoring:
                session.automatic_guard_started_at = None
                session.automation_state = AutomationState.OFF
            elif session.session_id in self._automatic_mining_session_ids:
                session.automation_state = AutomationState.ARMED
            if session.controller.is_running:
                self._stop_account_session(session)
                stopped += 1
        logging.getLogger(__name__).info(
            "%s，作用范围：%s；已请求停止 %s 个账号的观看会话",
            (
                "任务监测与观看会话已停止"
                if disable_monitoring
                else "观看会话已停止，后台任务监测继续运行"
            ),
            "所有账号" if len(sessions) > 1 else "当前账号",
            stopped,
        )

    def toggle_background_auto_scope(self) -> None:
        """Compatibility alias for the v2.0 two-button interface."""
        self.toggle_run_scope()

    def enable_background_auto(self) -> None:
        """Compatibility entrypoint used by tests and tray integrations."""
        self._capture_active_session()
        sessions = self._scope_sessions()
        if not any(session.controller.is_running for session in sessions):
            self._start_continuous_scope(
                sessions,
                interactive=len(sessions) == 1,
            )
        self._update_global_run_controls()

    def disable_background_auto(self) -> None:
        self._stop_continuous_scope(
            self._scope_sessions(),
            disable_monitoring=True,
        )
        self._update_global_run_controls()

    def _stop_auto_started_sessions(self, session_ids: set[str]) -> int:
        stopped = 0
        for session_id in session_ids:
            session = self._account_sessions.get(session_id)
            if (
                session is None
                or session.run_owner != RunOwner.AUTO
                or not session.controller.is_running
            ):
                continue
            self._stop_account_session(session)
            stopped += 1
        return stopped

    @staticmethod
    def _automatic_start_uses_steady_sessions(
        session: AccountWorkspace,
        *,
        now: float | None = None,
    ) -> bool:
        started_at = session.automatic_guard_started_at
        if started_at is None:
            return False
        current = monotonic() if now is None else now
        return current - started_at >= AUTOMATIC_STEADY_GUARD_SECONDS

    def boost_concurrency_scope(self) -> None:
        self._capture_active_session()
        sessions = self._boostable_scope_sessions()
        if not sessions:
            self._show_warning(
                "没有可加速账号",
                "请先扫码登录账号，再选择仅本次加速或持续高并发。",
            )
            return
        fixed_high = tuple(
            session
            for session in sessions
            if session.concurrency_mode == "fixed"
            and session.thread_count >= PERSISTENT_HIGH_SESSIONS
        )
        choice = self._choose_concurrency_boost_mode(
            len(sessions),
            existing_fixed_high=bool(fixed_high),
        )
        if choice is None:
            return

        logger = logging.getLogger(__name__)
        running_applied = 0
        if choice == "once":
            for session in sessions:
                session.runtime_concurrency_override = (
                    ONE_TIME_BOOST_SESSIONS
                )
                if session.controller.is_running and (
                    session.controller.force_fixed_sessions_per_room(
                        ONE_TIME_BOOST_SESSIONS
                    )
                ):
                    running_applied += 1
            logger.warning(
                "已为 %s 个账号设置仅本次 100 线程加速；"
                "其中 %s 个正在运行的账号已立即生效",
                len(sessions),
                running_applied,
            )
            self._show_info(
                "仅本次加速已设置",
                (
                    f"已对 {len(sessions)} 个账号强制本次使用每房间 100 线程。\n"
                    "正在挂机的账号立即生效；尚未挂机的账号会在下一次开始时生效。\n"
                    "停止本次挂机后会恢复原来的自动/固定并发设置。\n"
                    "线程过多可能触发 B 站风控，导致观看进度不计时。"
                ),
            )
        else:
            for session in sessions:
                session.runtime_concurrency_override = None
                session.concurrency_mode = "fixed"
                session.thread_count = PERSISTENT_HIGH_SESSIONS
                if session.controller.is_running and (
                    session.controller.force_fixed_sessions_per_room(
                        PERSISTENT_HIGH_SESSIONS
                    )
                ):
                    running_applied += 1
            self.threads_spin.setValue(PERSISTENT_HIGH_SESSIONS)
            mode_index = self.concurrency_mode_combo.findData("fixed")
            self.concurrency_mode_combo.setCurrentIndex(max(0, mode_index))
            account_saved = self._persist_account_settings_for(sessions)
            saved = self._persist_fixed_concurrency_setting() and account_saved
            logger.warning(
                "已将 %s 个账号切换为固定 32 线程；"
                "其中 %s 个正在运行的账号已立即生效",
                len(sessions),
                running_applied,
            )
            self._show_info(
                "已切换为持续高并发",
                (
                    f"已将 {len(sessions)} 个账号切换为固定 32 线程"
                    f"{'并保存' if saved else '；但本次未能保存设置'}。\n"
                    "如需恢复，请打开“设置与日志”，在高级设置中把并发模式改回“自动调节”。"
                ),
            )
        self._update_global_run_controls()

    def _persist_account_settings_for(
        self,
        sessions: tuple[AccountWorkspace, ...],
    ) -> bool:
        saved_sessions = [session for session in sessions if not session.temporary]
        if not saved_sessions:
            return True
        if not self._backup_cookie_profiles("settings"):
            return False
        previous_flags = {
            session.session_id: session.account_settings_saved
            for session in saved_sessions
        }
        previous_profile_settings = [
            (profile, dict(profile.settings))
            for profile in self._cookie_profiles
        ]
        try:
            for session in saved_sessions:
                session.account_settings_saved = True
            self._write_cookie_profiles()
            return True
        except Exception as exc:
            for session in saved_sessions:
                session.account_settings_saved = previous_flags[
                    session.session_id
                ]
            for profile, settings in previous_profile_settings:
                profile.settings = settings
            logging.getLogger(__name__).warning(
                "账号设置保存失败: %s",
                exc,
            )
            return False

    def _choose_concurrency_boost_mode(
        self,
        account_count: int,
        *,
        existing_fixed_high: bool = False,
    ) -> str | None:
        return choose_concurrency_boost_mode(
            self,
            account_count,
            existing_fixed_high=existing_fixed_high,
        )

    def _persist_fixed_concurrency_setting(self) -> bool:
        try:
            payload = load_stored_config_data(self._credential_store) or {}
            payload["thread_count"] = PERSISTENT_HIGH_SESSIONS
            payload["concurrency_mode"] = "fixed"
            save_stored_config_data(self._credential_store, payload)
            return True
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "固定 32 线程已在本次运行中生效，但保存设置失败: %s",
                exc,
            )
            return False

    @staticmethod
    def _seed_session_runtime_config(
        session: AccountWorkspace,
        template: AccountWorkspace,
    ) -> None:
        if session.rooms_text.strip():
            return
        session.rooms_text = template.rooms_text
        session.task_ids_text = template.task_ids_text
        session.thread_count = template.thread_count
        session.reconnect_delay_seconds = template.reconnect_delay_seconds
        session.task_query_interval_seconds = (
            template.task_query_interval_seconds
        )
        session.notify_on_task_complete = template.notify_on_task_complete
        session.concurrency_mode = template.concurrency_mode

    def _automatic_mining_tick(self) -> None:
        if not self._automatic_mining_session_ids or not self._ui_alive:
            return
        self._capture_active_session()
        template = self._active_session
        now_epoch = time()
        for session in tuple(self._account_sessions.values()):
            if session.session_id not in self._automatic_mining_session_ids:
                continue
            self._seed_session_runtime_config(session, template)
            if (
                session.automatic_check_inflight
                or now_epoch < session.next_automatic_check_at
            ):
                continue
            if not session.cookie.strip() or not session.rooms_text.strip():
                session.next_automatic_check_at = now_epoch + 15 * 60
                continue
            if session.login_state == LoginState.INVALID:
                session.next_automatic_check_at = now_epoch + 15 * 60
                continue
            try:
                room_ids = parse_room_ids(session.rooms_text)
            except ValueError as exc:
                logging.getLogger(__name__).warning(
                    "账号 UID %s 自动挂机配置错误: %s",
                    session.uid or "未知",
                    exc,
                )
                session.next_automatic_check_at = now_epoch + 15 * 60
                continue
            if not room_ids:
                session.next_automatic_check_at = now_epoch + 15 * 60
                continue
            session.automatic_check_inflight = True
            session.automation_state = AutomationState.CHECKING
            session_id = session.session_id
            cookie = session.cookie
            room_id = room_ids[0]
            runtime_running = session.controller.is_running
            generation = session.configuration_generation
            threading.Thread(
                target=self._run_automatic_account_check,
                args=(
                    session_id,
                    generation,
                    cookie,
                    room_id,
                    runtime_running,
                ),
                daemon=True,
                name=f"auto-mining-check-{session.uid or 'unknown'}",
            ).start()

    def _run_automatic_account_check(
        self,
        session_id: str,
        generation: int,
        cookie: str,
        room_id: int,
        runtime_running: bool,
    ) -> None:
        try:
            discovery = self._automatic_discovery_service.discover(
                room_id,
                timeout_seconds=15,
                headless=True,
                cookie=cookie,
                force_refresh=True,
            )
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            selection = select_scheduled_task_group(
                discovery.groups,
                now=now,
            )
            if selection.group is None:
                result = AutomaticAccountCheckResult(
                    session_id=session_id,
                    selection=selection,
                    generation=generation,
                    error=discovery.message or "未发现可调度任务",
                )
            elif selection.phase == "future":
                result = AutomaticAccountCheckResult(
                    session_id=session_id,
                    selection=selection,
                    generation=generation,
                )
            else:

                async def _query_current():
                    client = BilibiliClient(cookie)
                    try:
                        progresses, room_info = await asyncio.gather(
                            client.get_task_progress(
                                list(selection.group.task_ids)
                            ),
                            client.get_live_room_info(room_id),
                        )
                        snapshot = TaskSnapshot(
                            progresses=tuple(progresses)
                        )
                        if (
                            not runtime_running
                            and all_tasks_completed(snapshot)
                        ):
                            claim_ids = claimable_reward_task_ids(snapshot)
                            if claim_ids:
                                claim_results = (
                                    await client.receive_all_mission_rewards(
                                        claim_ids
                                    )
                                )
                                for claim_id, claim_result in zip(
                                    claim_ids,
                                    claim_results,
                                ):
                                    if not bool(
                                        getattr(
                                            claim_result,
                                            "success",
                                            False,
                                        )
                                    ):
                                        continue
                                    for task in progresses:
                                        for point in task.check_points or []:
                                            if point.sid == claim_id:
                                                point.status = 3
                        return progresses, room_info.live_status
                    finally:
                        await client.close()

                session = self._account_sessions.get(session_id)
                if session is None:
                    raise RuntimeError("账号工作区已关闭")
                permit = session.request_coordinator.acquire(
                    "automatic-task-check",
                    group=TASK_API_GROUP,
                    timeout_seconds=10.0,
                )
                if permit is None:
                    raise RuntimeError("账号任务请求正在执行或冷却中")
                query_error: BaseException | None = None
                try:
                    progresses, live_status = asyncio.run(_query_current())
                except BaseException as exc:
                    query_error = exc
                    raise
                finally:
                    session.request_coordinator.finish(
                        permit,
                        cooldown_seconds=(
                            30.0
                            if query_error is not None
                            and looks_rate_limited(query_error)
                            else 0.0
                        ),
                    )
                result = AutomaticAccountCheckResult(
                    session_id=session_id,
                    selection=selection,
                    generation=generation,
                    snapshot=TaskSnapshot(progresses=tuple(progresses)),
                    live_status=live_status,
                )
        except Exception as exc:
            result = AutomaticAccountCheckResult(
                session_id=session_id,
                selection=ScheduledTaskSelection(
                    None,
                    "none",
                    15 * 60,
                ),
                generation=generation,
                error=str(exc).strip() or type(exc).__name__,
            )
        self._post_ui_task(self._apply_automatic_account_check, result)

    def _apply_automatic_account_check(
        self,
        result: AutomaticAccountCheckResult,
    ) -> None:
        session = self._account_sessions.get(result.session_id)
        if session is None:
            return
        session.automatic_check_inflight = False
        if result.generation != session.configuration_generation:
            session.automation_state = AutomationState.ARMED
            if session.session_id in self._automatic_mining_session_ids:
                session.next_automatic_check_at = 0.0
                QTimer.singleShot(0, self._automatic_mining_tick)
            logging.getLogger(__name__).info(
                "账号 UID %s 的旧后台检查结果已忽略（generation %s -> %s）",
                session.uid or "未知",
                result.generation,
                session.configuration_generation,
            )
            return
        if session.automatic_check_pending:
            session.automatic_check_pending = False
            session.next_automatic_check_at = 0.0
            QTimer.singleShot(0, self._automatic_mining_tick)
            return
        session.next_automatic_check_at = (
            time() + result.selection.next_check_seconds
        )
        if session.session_id not in self._automatic_mining_session_ids:
            session.automation_state = AutomationState.OFF
            return
        group = result.selection.group
        known_task_expired = (
            session.task_ends_at is not None
            and datetime.now(ZoneInfo("Asia/Shanghai")) >= session.task_ends_at
        )
        if result.selection.phase == "expired" or (
            result.error and known_task_expired
        ):
            session.task_phase = TaskPhase.EXPIRED
            if (
                session.controller.is_running
                and session.run_owner == RunOwner.AUTO
            ):
                self._stop_account_session(session)
            session.task_ids_text = ""
            session.task_started_at = None
            session.task_ends_at = None
            session.latest_task_snapshot = TaskSnapshot()
            if session.controller.is_running:
                session.controller.update_task_ids([])
            if session.session_id == self._active_session_id:
                self.task_ids_edit.clear()
                self._render_task_snapshot(session.latest_task_snapshot)
            session.discovery_status_text = (
                "持续任务检测：旧任务已结束，已清除旧进度；"
                "15 分钟后重新识别当天任务"
            )
            if session.session_id == self._active_session_id:
                self._set_discovery_status(
                    session.discovery_status_text,
                    False,
                )
            self._update_global_run_controls()
            session.automation_state = AutomationState.ARMED
            return
        if result.error:
            session.automation_state = AutomationState.COOLDOWN
            session.discovery_status_text = (
                f"后台自动检查未完成：{result.error}"
            )
            if session.session_id == self._active_session_id:
                self._set_discovery_status(
                    session.discovery_status_text,
                    False,
                )
            logging.getLogger(__name__).warning(
                "账号 UID %s 后台自动检查未完成: %s",
                session.uid or "未知",
                result.error,
            )
            return
        if group is None:
            return

        session.task_ids_text = ",".join(group.task_ids)
        session.task_started_at = group.start_at
        session.task_ends_at = group.end_at
        if session.controller.is_running:
            session.controller.update_task_ids(list(group.task_ids))
        if session.session_id == self._active_session_id:
            self.task_ids_edit.setText(session.task_ids_text)

        if result.selection.phase == "future":
            session.task_phase = TaskPhase.FUTURE
            session.automation_state = AutomationState.WAITING_TASK
            if (
                session.controller.is_running
                and session.run_owner == RunOwner.AUTO
            ):
                self._stop_account_session(session)
            start_text = (
                group.start_at.astimezone().strftime("%m-%d %H:%M")
                if group.start_at is not None
                else "稍后"
            )
            session.discovery_status_text = (
                f"持续任务检测：已识别 {group.label}，预计 {start_text} 开始；"
                "到时自动检查开播"
            )
            if session.session_id == self._active_session_id:
                self._set_discovery_status(
                    session.discovery_status_text,
                    False,
                )
            return

        session.latest_task_snapshot = result.snapshot
        session.task_phase = TaskPhase.ACTIVE
        if session.cookie:
            session.login_state = LoginState.VALID
        if session.session_id == self._active_session_id:
            self._render_task_snapshot(result.snapshot)
        if all_tasks_completed(result.snapshot):
            session.task_phase = TaskPhase.COMPLETED
            claim_ids = claimable_reward_task_ids(result.snapshot)
            session.automation_state = (
                AutomationState.CLAIMING
                if session.controller.is_running
                else AutomationState.ARMED
            )
            if all_task_rewards_claimed(result.snapshot):
                session.discovery_status_text = (
                    "平台已确认当天奖励全部领取，正在结束观看线程；"
                    "后台任务检测继续运行"
                    if session.controller.is_running
                    else "当天任务奖励已全部领取，后台任务检测继续运行"
                )
            elif claim_ids and session.controller.is_running:
                session.discovery_status_text = (
                    "当天任务已全部完成，正在自动领取并确认最后奖励；"
                    "确认全部领取后关闭观看线程，后台检测继续运行"
                )
            else:
                session.discovery_status_text = (
                    "当天任务已完成，等待平台确认领奖状态；"
                    "确认全部领取后关闭观看线程，后台检测继续运行"
                    if session.controller.is_running
                    else "当天任务已完成，后台检测继续运行"
                )
        elif result.live_status == 1:
            if not session.controller.is_running:
                self._start_account_session(
                    session,
                    interactive=False,
                    automatic=True,
                    automatic_start_in_steady_mode=(
                        self._automatic_start_uses_steady_sessions(session)
                    ),
                )
            session.automation_state = (
                AutomationState.AUTO_RUNNING
                if session.run_owner == RunOwner.AUTO
                else AutomationState.ARMED
            )
            session.discovery_status_text = (
                f"持续任务检测：{group.label} 已开始且直播已开播，正在挂机"
            )
        else:
            session.automation_state = AutomationState.WAITING_LIVE
            session.discovery_status_text = (
                f"持续任务检测：{group.label} 尚未开播；"
                "15 分钟后自动复查"
            )
        if session.session_id == self._active_session_id:
            self._set_discovery_status(
                session.discovery_status_text,
                False,
            )
        self._update_global_run_controls()

    def _update_global_run_controls(self) -> None:
        if not hasattr(self, "apply_all_switch"):
            return
        sessions = self._scope_sessions()
        any_running = any(
            session.controller.is_running for session in sessions
        )
        any_startable = any(
            bool(session.cookie.strip()) and not session.controller.is_running
            for session in sessions
        )
        action_blocked = any(
            session.application_state
            in {ApplicationState.DISCOVERING, ApplicationState.STOPPING}
            for session in sessions
        )
        self.start_btn.setText("停止" if any_running else "开始")
        self._set_action_button_color(
            self.start_btn,
            "red" if any_running else "green",
        )
        self.start_btn.setEnabled(
            not action_blocked and (any_running or any_startable)
        )
        self.boost_concurrency_btn.setEnabled(
            not action_blocked and bool(self._boostable_scope_sessions())
        )
        auto_enabled = any(
            session.session_id in self._automatic_mining_session_ids
            for session in sessions
        )
        scope_text = (
            "所有账号" if self.apply_all_switch.isChecked() else "当前账号"
        )
        self.auto_mining_description.setText(
            (
                f"作用范围：{scope_text}。后台任务检测已开启并会保持到程序退出；"
                "全部领奖后自动关闭观看线程，发现新任务后再启动。"
                if auto_enabled
                else
                f"作用范围：{scope_text}。点击开始会同时启动观看线程和后台任务检测；"
                "后台检测会保持到程序退出。"
            )
        )

    @staticmethod
    def _set_action_button_color(button, color: str) -> None:
        button.setStyleSheet(
            BUTTON_STYLES[color] + DISABLED_BUTTON_STYLE
        )

    def _on_apply_all_scope_changed(self, _checked: bool) -> None:
        self._update_global_run_controls()

    def _on_runtime_inputs_changed(self) -> None:
        if self._account_switching:
            return
        self._capture_active_session()
        targets = self._scope_sessions()
        should_wake = False
        for session in targets:
            if session.session_id not in self._automatic_mining_session_ids:
                continue
            session.automatic_guard_started_at = monotonic()
            session.next_automatic_check_at = 0.0
            if session.automatic_check_inflight:
                session.automatic_check_pending = True
            should_wake = True
        if should_wake:
            logging.getLogger(__name__).info(
                "房间或任务配置已更新，正在立即唤醒后台自动检查"
            )
            QTimer.singleShot(0, self._automatic_mining_tick)

    def _poll_worker_shutdown(self) -> None:
        logger = logging.getLogger(__name__)
        still_stopping = False
        for session in tuple(self._account_sessions.values()):
            controller = session.controller
            if not (controller.stop_signal_set or controller.stopping_in_progress):
                continue
            result = controller.poll_shutdown(logger=logger)
            if result == "running":
                still_stopping = True
                continue
            session.application_state = ApplicationState.IDLE
            session.runtime_health = RuntimeHealth()
            session.run_owner = RunOwner.NONE
            session.runtime_concurrency_override = None
            if session.session_id == self._active_session_id:
                self._render_runtime_health(session.runtime_health)
            else:
                self._update_account_selector_label(session)
        if not still_stopping:
            self._stop_poll_timer.stop()
        self._update_global_run_controls()

    def _stop_all_account_sessions(self, *, force: bool = False) -> None:
        logger = logging.getLogger(__name__)
        needs_poll = False
        for session in tuple(self._account_sessions.values()):
            session.task_controller.stop_live_watch_time()
            result = session.controller.request_stop(logger=logger)
            if result in {"stopping_started", "force_requested", "already_stopping"}:
                session.application_state = ApplicationState.STOPPING
                needs_poll = True
                if force and result == "stopping_started":
                    session.controller.request_stop(logger=logger)
            else:
                session.application_state = ApplicationState.IDLE
        if needs_poll:
            self._stop_poll_timer.start()

    # ---------- progress bar (Qt-native indeterminate) ----------

    def _start_progress_animation(self) -> None:
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

    def _stop_progress_animation(self) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

    # ---------- log / layout toggle ----------

    def open_settings_log(self) -> None:
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _toggle_cookie_visibility(self) -> None:
        visible = self.cookie_edit.echoMode() == QLineEdit.Password
        self.cookie_edit.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self.cookie_reveal_btn.setText("隐藏" if visible else "显示")

    def _toggle_notify_visibility(self) -> None:
        visible = self.notify_urls_edit.echoMode() == QLineEdit.Password
        self.notify_urls_edit.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self.notify_reveal_btn.setText("隐藏" if visible else "显示")

    def clear_logs(self) -> None:
        self.log_text.clear()

    # ---------- task progress ----------

    def _build_task_progress_text(self) -> str:
        return self._task_progress_result or "点击“手动刷新”查看任务进度"

    def _show_task_message(self, text: str) -> None:
        self.task_table.setRowCount(1)
        item = QTableWidgetItem(text or "暂无任务数据")
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.task_table.setItem(0, 0, item)
        self.task_table.setSpan(0, 0, 1, self.task_table.columnCount())
        self.claim_rewards_btn.setEnabled(False)

    def _apply_session_task_snapshot(
        self,
        session_id: str,
        snapshot: TaskSnapshot,
    ) -> None:
        session = self._account_sessions.get(session_id)
        if session is None:
            return
        session.latest_task_snapshot = snapshot
        session.task_progress_pending = False
        if session_id == self._active_session_id:
            self._task_progress_pending = False
            self._render_task_snapshot(snapshot)

    def _stop_runtime_after_rewards_claimed(
        self,
        session_id: str,
        settled_task_ids: tuple[str, ...],
    ) -> None:
        session = self._account_sessions.get(session_id)
        if (
            session is None
            or not session.controller.is_running
            or session.controller.stop_signal_set
        ):
            return
        current_task_ids = tuple(parse_task_ids(session.task_ids_text))
        if set(current_task_ids) != set(settled_task_ids):
            logging.getLogger(__name__).info(
                "账号 UID %s 的旧任务完成信号已忽略: %s -> %s",
                session.uid or "未知",
                settled_task_ids,
                current_task_ids,
            )
            return
        if session.completion_auto_stop_bypass:
            session.discovery_status_text = (
                "当天奖励显示已全部领取；本次属于手动继续挂机，"
                "不会自动暂停，请手动停止"
            )
            if session_id == self._active_session_id:
                self._set_discovery_status(
                    session.discovery_status_text,
                    False,
                )
            return
        completion_key = self._completion_run_key(
            current_task_ids
        )
        if completion_key is None:
            return
        session.completion_auto_stop_key = completion_key
        session.automation_state = AutomationState.ARMED
        session.discovery_status_text = (
            "当天任务奖励已全部领取，观看线程已自动关闭；"
            "后台任务检测继续运行，发现新任务后会自动启动"
        )
        logging.getLogger(__name__).info(
            "账号 UID %s 当天奖励已全部领取，正在关闭观看线程并保留后台检测",
            session.uid or "未知",
        )
        if session_id == self._active_session_id:
            self._set_discovery_status(
                session.discovery_status_text,
                False,
            )
        self._stop_account_session(session)


    def _apply_task_snapshot(self, snapshot: TaskSnapshot) -> None:
        self._active_session.latest_task_snapshot = snapshot
        self._render_task_snapshot(snapshot)

    def _render_task_snapshot(self, snapshot: TaskSnapshot) -> None:
        self._latest_task_snapshot = snapshot
        self.task_table.clearSpans()
        if snapshot.error:
            self._show_task_message(f"任务刷新失败：{snapshot.error}")
            self.discovery_status_label.setText("任务数据可能已失效，可重新识别当前任务")
            if (
                self._application_state == ApplicationState.RUNNING
                and not self._rediscovery_attempted_for_run
                and not self._account_switching
            ):
                self._rediscovery_attempted_for_run = True
                self._active_session.rediscovery_attempted_for_run = True
                self.browser_actions.rediscover_task_ids()
            return
        if not snapshot.progresses:
            self._show_task_message("未发现任务进度，请先识别当前任务")
            return

        progress_rows = task_progress_table_rows(list(snapshot.progresses))
        checkpoint_count = sum(
            len(task.check_points or [])
            for task in snapshot.progresses
        )
        if checkpoint_count:
            self.discovery_status_label.setText(
                (
                    f"已加载当天任务：{len(snapshot.progresses)} 个任务系列，"
                    f"{checkpoint_count} 个奖励节点"
                )
            )
        else:
            self.discovery_status_label.setText(
                f"已加载当天任务：{len(snapshot.progresses)} 个任务"
            )
        self._set_discovery_status_style(False)
        self.task_table.setRowCount(len(progress_rows))
        for row, progress in enumerate(progress_rows):
            limit = float(progress.limit_value or 0)
            cur = float(progress.cur_value or 0)
            percent = int(max(0, min(100, cur / limit * 100))) if limit > 0 else 0
            if progress.is_claimed:
                status = "已领取"
                claim_state = "已领取"
            elif progress.is_claimable:
                status = "已完成"
                claim_state = "待领取"
            elif progress.is_completed:
                status = "已完成"
                claim_state = "等待服务器确认"
            else:
                status = "进行中"
                claim_state = "完成后自动领取"
            values = (
                progress.label,
                f"{progress.cur_value}/{progress.limit_value}（{percent}%）",
                status,
                progress.reward_text,
                claim_state,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.task_table.setItem(row, column, item)
        self.claim_rewards_btn.setEnabled(
            any(progress.is_claimable for progress in progress_rows)
            and self._application_state
            in {
                ApplicationState.IDLE,
                ApplicationState.RUNNING,
                ApplicationState.ERROR,
            }
        )

    def _apply_session_runtime_health(
        self,
        session_id: str,
        health: RuntimeHealth,
    ) -> None:
        session = self._account_sessions.get(session_id)
        if session is None:
            return
        session.runtime_health = health
        session.application_state = health.state
        if session_id == self._active_session_id:
            self._render_runtime_health(health)
        else:
            self._update_account_selector_label(session)
        self._update_global_run_controls()

    def _apply_runtime_health(self, health: RuntimeHealth) -> None:
        self._active_session.runtime_health = health
        self._render_runtime_health(health)

    def _render_runtime_health(self, health: RuntimeHealth) -> None:
        self._set_application_state(health.state)
        owner = self._active_session.run_owner
        owner_label = {
            RunOwner.NONE: "未启动",
            RunOwner.MANUAL: "手动运行",
            RunOwner.AUTO: "后台自动运行",
        }[owner]
        heartbeat = "等待首次心跳"
        if health.last_heartbeat_at:
            age = max(0, int(time() - health.last_heartbeat_at))
            heartbeat = f"最近心跳 {age} 秒前"
        mode = health.concurrency_mode or self._active_session.concurrency_mode
        phase = health.concurrency_phase
        if mode == "automatic":
            phase_label = (
                "自动稳定"
                if phase == "steady"
                else "自动追赶"
            )
        else:
            phase_label = "固定并发"
        detail = (
            f"{owner_label} · 会话 当前 {health.active_sessions} / 目标 {health.target_sessions}"
            f" · {phase_label} · 重连 {health.reconnect_count} · {heartbeat}"
        )
        if health.concurrency_detail:
            detail += f" · {health.concurrency_detail}"
        if health.last_error:
            detail += f" · 最近错误：{health.last_error}"
        self.runtime_detail_label.setText(detail)

    def _set_application_state(self, state: ApplicationState) -> None:
        self._application_state = state
        session = self._account_sessions.get(self._active_session_id)
        if session is not None:
            session.application_state = state
            if session.runtime_health.state != state:
                session.runtime_health = replace(
                    session.runtime_health,
                    state=state,
                )
        labels = {
            ApplicationState.IDLE: ("未运行", "#343a46"),
            ApplicationState.DISCOVERING: ("识别中", "#1d4ed8"),
            ApplicationState.STARTING: ("启动中", "#9a6700"),
            ApplicationState.RUNNING: ("运行中", "#166534"),
            ApplicationState.STOPPING: ("停止中", "#9a3412"),
            ApplicationState.ERROR: ("异常", "#991b1b"),
        }
        monitoring_without_watch_threads = (
            state == ApplicationState.IDLE
            and session is not None
            and session.session_id in self._automatic_mining_session_ids
        )
        text, background = (
            ("持续监测任务中", "#1d4ed8")
            if monitoring_without_watch_threads
            else labels[state]
        )
        self.runtime_state_label.setText(text)
        self.runtime_state_label.setStyleSheet(
            f"background:{background};color:#ffffff;border-radius:12px;"
            "padding:6px 12px;font-weight:600;"
        )
        busy = state in {
            ApplicationState.DISCOVERING,
            ApplicationState.STARTING,
            ApplicationState.RUNNING,
            ApplicationState.STOPPING,
        }
        discovering = state == ApplicationState.DISCOVERING
        self.discover_btn.setText("取消识别" if discovering else "识别当前任务")
        self.discover_btn.setEnabled(
            discovering or state in {ApplicationState.IDLE, ApplicationState.ERROR}
        )
        self.overwatch_esports_btn.setEnabled(not busy)
        for widget in (
            self.cookie_edit,
            self.cookie_remark_edit,
            self.rooms_edit,
            self.task_ids_edit,
            self.notify_urls_edit,
            self.threads_spin,
            self.reconnect_spin,
            self.task_interval_spin,
        ):
            widget.setEnabled(not busy)
        self.cookie_profile_combo.setEnabled(not discovering)
        self.save_cookie_profile_btn.setEnabled(not busy)
        self.delete_cookie_profile_btn.setEnabled(not busy)
        self.claim_rewards_btn.setEnabled(
            state
            in {
                ApplicationState.IDLE,
                ApplicationState.RUNNING,
                ApplicationState.ERROR,
            }
            and any(
                row.is_claimable
                for row in task_progress_table_rows(
                    list(self._latest_task_snapshot.progresses)
                )
            )
        )
        if session is not None:
            self._update_account_selector_label(session)
        self._update_global_run_controls()

    def _set_discovery_status(self, text: str, error: bool = False) -> None:
        self.discovery_status_label.setText(text)
        session = self._account_sessions.get(self._active_session_id)
        if session is not None:
            session.discovery_status_text = text
            session.discovery_status_error = error
        self._set_discovery_status_style(error)
        if text.startswith("正在") and not self.worker_controller.is_running:
            self._set_application_state(ApplicationState.DISCOVERING)
        elif (
            self._application_state == ApplicationState.DISCOVERING
            and not self.worker_controller.is_running
        ):
            if error:
                self._pending_start_after_discovery = False
                self._active_session.pending_start_after_discovery = False
            self._set_application_state(
                ApplicationState.ERROR if error else ApplicationState.IDLE
            )

    def _set_discovery_status_style(self, error: bool) -> None:
        self.discovery_status_label.setStyleSheet(
            f"color:{'#fca5a5' if error else '#a7f3d0'};padding-left:92px;"
        )

    def _set_task_progress_text(self, text: str) -> None:
        self._set_session_task_progress_text(self._active_session_id, text)

    def _set_session_task_progress_text(
        self,
        session_id: str,
        text: str,
    ) -> None:
        session = self._account_sessions.get(session_id)
        if session is None:
            return
        session.task_progress_result = text
        session.task_progress_pending = True
        if session_id != self._active_session_id:
            return
        self._task_progress_result = text
        self._task_progress_pending = True

    def _set_live_watch_time_text(self, text: str) -> None:
        self._set_session_live_watch_time_text(self._active_session_id, text)

    def _set_session_live_watch_time_text(
        self,
        session_id: str,
        text: str,
    ) -> None:
        session = self._account_sessions.get(session_id)
        if session is None:
            return
        session.live_watch_time_result = text
        if session_id != self._active_session_id:
            return
        self._live_watch_time_result = text
        self.watch_time_label.setText(text)

    def _complete_task_refresh(self, result_text: str, rerun: bool) -> None:
        self._complete_session_task_refresh(
            self._active_session_id,
            result_text,
            rerun,
        )

    def _complete_session_task_refresh(
        self,
        session_id: str,
        result_text: str,
        rerun: bool,
    ) -> None:
        if result_text:
            self._set_session_task_progress_text(session_id, result_text)
        session = self._account_sessions.get(session_id)
        if rerun and session is not None:
            session.task_controller.refresh(manual=False)

    def refresh_tasks(self, *args, manual: bool = True, **kwargs) -> None:
        # QPushButton.clicked may pass a bool (checked) — ignore positional args.
        self._capture_active_session()
        self.task_controller.refresh(manual=manual)

    def claim_rewards(self, *args, **kwargs) -> None:
        # QPushButton.clicked may pass a bool (checked) — ignore positional args.
        self._capture_active_session()
        self.task_controller.claim_rewards()

    @staticmethod
    def _find_browser(name: str) -> bool:
        return BrowserActions.find_browser(name)

    @staticmethod
    def _detect_default_browser() -> str | None:
        return BrowserActions.detect_default_browser()

    @staticmethod
    def _available_browsers() -> list[str]:
        return BrowserActions.available_browsers()

    @staticmethod
    def _browser_label(browser: str) -> str:
        return BrowserActions.browser_label(browser)

    def _pick_browser(self) -> str | None:
        return self.browser_actions.pick_browser()

    @staticmethod
    def _browser_try_order(preferred: str | None) -> tuple[str, ...]:
        return BrowserActions.browser_try_order(preferred)

    @staticmethod
    def _extract_room_id_from_live_url(text: str) -> int | None:
        return BrowserActions.extract_room_id_from_live_url(text)

    def _apply_auto_room_id(self, room_id: int) -> None:
        changed = self._active_session.rooms_text != str(room_id)
        self.rooms_edit.setText(str(room_id))
        self._active_session.rooms_text = str(room_id)
        if changed:
            self._active_session.bump_configuration_generation()
        self._on_runtime_inputs_changed()

    def _apply_auto_cookie(self, cookie_str: str) -> AccountWorkspace:
        previous_cookie = self._active_session.cookie
        session = self._adopt_cookie_for_active_session(cookie_str)
        if session.cookie != previous_cookie:
            session.bump_configuration_generation()
        session.login_check_generation += 1
        session.login_state = LoginState.UNKNOWN
        self.cookie_edit.setText(cookie_str)
        if not session.remark and not self.cookie_remark_edit.text().strip():
            self.cookie_remark_edit.setPlaceholderText(
                f"不填写将保存为 {default_cookie_remark(cookie_str)}"
            )
        self._update_account_selector_label(session)
        return session

    def _apply_auto_task_ids(self, task_ids_str: str) -> None:
        task_ids = parse_task_ids(task_ids_str)
        normalized = ",".join(task_ids)
        sessions = self._scope_sessions()
        self.task_ids_edit.setText(normalized)
        for session in sessions:
            tasks_changed = parse_task_ids(session.task_ids_text) != task_ids
            session.task_ids_text = normalized
            session.pending_start_after_discovery = False
            session.rediscovery_attempted_for_run = False
            if tasks_changed:
                session.bump_configuration_generation()
                session.latest_task_snapshot = TaskSnapshot()
                session.task_progress_result = ""
                session.task_progress_pending = False
            if session.session_id != self._active_session_id:
                session.discovery_status_text = (
                    f"已从当前账号同步 {len(task_ids)} 个当天任务，"
                    "正在刷新本账号进度"
                )
                session.discovery_status_error = False
            if session.controller.is_running:
                session.controller.update_task_ids(task_ids)
        if self._active_session.latest_task_snapshot != self._latest_task_snapshot:
            self._render_task_snapshot(self._active_session.latest_task_snapshot)
        self._on_runtime_inputs_changed()
        for session in sessions:
            session.task_controller.refresh(manual=False)
        self._pending_start_after_discovery = False
        logging.getLogger(__name__).info(
            "任务识别结果已应用到%s并分别刷新进度",
            "所有账号" if self.apply_all_switch.isChecked() else "当前账号",
        )

    def _apply_selected_task_group(
        self,
        room_id: int | None,
        task_groups: list[dict[str, object]],
    ) -> None:
        self.browser_actions.apply_selected_task_group(room_id, task_groups)

    def _browser_sniff(
        self,
        url_keyword: str | None,
        hint: str,
        on_network_match=None,
        on_cookies=None,
        on_page_url=None,
        on_page_html=None,
        browser_preference: str | None = None,
        finish_on_any: bool = False,
    ) -> None:
        self.browser_actions.browser_sniff(
            url_keyword,
            hint,
            on_network_match=on_network_match,
            on_cookies=on_cookies,
            on_page_url=on_page_url,
            on_page_html=on_page_html,
            browser_preference=browser_preference,
            finish_on_any=finish_on_any,
        )

    def auto_fetch_room_id(self) -> None:
        if self.worker_controller.is_running:
            self._show_warning("运行中", "修改房间需要先停止当前挂机。")
            return
        self.browser_actions.auto_fetch_room_id()

    def auto_fetch_task_ids(self) -> None:
        if self._application_state == ApplicationState.DISCOVERING:
            self.browser_actions.cancel_discovery()
            self._set_discovery_status("正在取消任务识别…", False)
            self.discover_btn.setText("正在取消…")
            self.discover_btn.setEnabled(False)
            return
        self.browser_actions.auto_fetch_task_ids()

    def auto_fetch_overwatch_esports(self) -> None:
        if self.worker_controller.is_running:
            self._show_warning("运行中", "切换房间需要先停止当前挂机。")
            return
        self.rooms_edit.setText(str(OVERWATCH_ESPORTS_ROOM_ID))
        self.auto_fetch_task_ids()

    def auto_fetch_cookie(self) -> None:
        dialog = QrLoginDialog(self, on_success=self._apply_qr_login_cookie)
        dialog.exec()

    def _apply_qr_login_cookie(self, cookie: str) -> None:
        uid = extract_cookie_uid(cookie)
        profile_index = self._cookie_profile_index_for_uid(uid)
        if profile_index is not None:
            profile = self._cookie_profiles[profile_index]
            session = self._session_for_credential(profile.credential_id)
            if session is not None and session.controller.is_running:
                self._show_warning(
                    "账号正在挂机",
                    "扫码账号与正在挂机的档案相同。请先停止该账号，再刷新登录状态。",
                )
                return

            if not self._backup_cookie_profiles("qrrefresh"):
                return
            old_cookie = profile.cookie
            old_updated_at = profile.updated_at
            old_selected = self._last_selected_credential_id
            profile.cookie = cookie
            profile.updated_at = now_text()
            self._last_selected_credential_id = profile.credential_id
            try:
                self._write_cookie_profiles()
            except Exception as exc:
                profile.cookie = old_cookie
                profile.updated_at = old_updated_at
                self._last_selected_credential_id = old_selected
                self._show_error("更新账号登录失败", str(exc))
                return

            if session is None:
                session = AccountWorkspace.saved_account(
                    credential_id=profile.credential_id,
                    cookie=cookie,
                    remark=profile.remark,
                )
                account_settings = AccountSettings.from_mapping(
                    profile.settings
                )
                if account_settings is not None:
                    self._apply_account_settings(session, account_settings)
                    session.account_settings_saved = True
                session = self._register_account_session(session)
            cookie_changed = session.cookie != cookie
            session.cookie = cookie
            session.remark = profile.remark
            session.login_check_generation += 1
            session.login_state = LoginState.VALID
            if cookie_changed:
                session.bump_configuration_generation()
            self._activate_account_session(session.session_id)
            self.cookie_edit.setText(cookie)
            self.cookie_remark_edit.setText(profile.remark)
            self._refresh_cookie_profile_combo(
                selected_session_id=session.session_id
            )
            logging.getLogger(__name__).info(
                "扫码登录成功，已刷新同 UID 账号档案且保留原备注: UID %s",
                uid,
            )
            return

        session = self._apply_auto_cookie(cookie)
        session.login_state = LoginState.VALID
        self._update_account_selector_label(session)
        logging.getLogger(__name__).info(
            "扫码登录成功，已创建临时账号；仅保存档案后才会保留"
        )
        self._prompt_save_new_cookie(cookie)

    def _schedule_task_refresh(self) -> None:
        if (
            self.worker_controller.stop_signal_set
            or not self.worker_controller.is_running
        ):
            return
        self.refresh_tasks(manual=False)
        try:
            interval = self.task_interval_spin.value()
        except Exception:
            interval = 30
        self._task_refresh_timer.start(max(10, interval) * 1000)

    def _schedule_live_watch_time_refresh(self) -> None:
        """Deprecated compatibility hook; estimated watch-time polling is off."""
        self._live_watch_time_timer.stop()

    def _sync_config_to_miner(self) -> None:
        # Runtime configuration is immutable. Only logging verbosity is safe to
        # change without restarting account-owned clients and task services.
        verbose = self.verbose_check.isChecked()
        if verbose != self._last_verbose:
            self._last_verbose = verbose
            self._install_logging()
        self._capture_active_session()

    # ---------- desktop runtime / close ----------

    def _setup_system_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = tray_icon(self.windowIcon())
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Bilibili 直播掉宝助手")
        menu = QMenu(self)
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self.activate_existing_instance)
        menu.addAction(show_action)
        menu.addSeparator()
        start_action = QAction("开始当前账号", menu)
        start_action.triggered.connect(self.start)
        menu.addAction(start_action)
        stop_all_action = QAction("停止全部账号", menu)
        stop_all_action.triggered.connect(self.stop_all)
        menu.addAction(stop_all_action)
        menu.addSeparator()
        quit_action = QAction("退出程序", menu)
        quit_action.triggered.connect(self.exit_application)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def _on_tray_activated(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        if reason in {
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        }:
            self.activate_existing_instance()

    def activate_existing_instance(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if self._tray_icon is not None:
            self._tray_icon.showMessage(
                "BiliDrop 已在运行",
                "已显示正在运行的主窗口。",
                QSystemTrayIcon.Information,
                2500,
            )

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.WindowStateChange
            and self.isMinimized()
            and self.minimize_to_tray_check.isChecked()
            and self._tray_icon is not None
        ):
            QTimer.singleShot(0, self.hide)

    def exit_application(self) -> None:
        self._exit_requested = True
        self.close()

    def _shutdown_for_exit(self) -> None:
        self._capture_active_session()
        self._login_validation_timer.stop()
        if hasattr(self, "_automatic_mining_timer"):
            self._automatic_mining_timer.stop()
        if hasattr(self, "browser_actions"):
            self.browser_actions.cancel_discovery()
        try:
            self._store_current_secrets()
            self._write_cookie_profiles()
            self._stop_all_account_sessions(force=True)
        except Exception:
            logging.getLogger(__name__).exception("关闭时停止失败")
        if self._tray_icon is not None:
            self._tray_icon.hide()
        self._ui_alive = False

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            self._ui_alive
            and not self._exit_requested
            and self.close_to_tray_check.isChecked()
            and self._tray_icon is not None
        ):
            event.ignore()
            self.settings_dialog.hide()
            self.hide()
            self._tray_icon.showMessage(
                "BiliDrop 仍在后台运行",
                "任务检查和挂机不会中断；从托盘菜单可重新打开。",
                QSystemTrayIcon.Information,
                2500,
            )
            return
        self._shutdown_for_exit()
        event.accept()
        if self._exit_requested or self._tray_icon is not None:
            QTimer.singleShot(0, QApplication.instance().quit)

    # ---------- config load/save ----------

    def _apply_stored_config_values(
        self,
        values,
        *,
        preserve_account_fields: bool = False,
    ) -> None:
        del preserve_account_fields
        self._global_account_defaults = AccountSettings(
            rooms_text=values.rooms_text,
            thread_count=int(values.thread_count_text),
            reconnect_delay_seconds=int(values.reconnect_delay_text),
            task_query_interval_seconds=int(
                values.task_query_interval_text
            ),
            notify_on_task_complete=values.notify_on_task_complete,
            concurrency_mode=values.concurrency_mode,
        )
        for session in self._account_sessions.values():
            if not session.account_settings_saved and not session.controller.is_running:
                self._apply_account_settings(
                    session,
                    self._global_account_defaults,
                )
        self.notify_urls_edit.setText(
            values.notify_urls_text
            or self._credential_store.get("notification-urls")
        )
        self.verbose_check.setChecked(values.verbose)
        self.minimize_to_tray_check.setChecked(values.minimize_to_tray)
        self.close_to_tray_check.setChecked(values.close_to_tray)
        self.auto_check_updates_check.setChecked(values.auto_check_updates)
        self.apply_all_switch.setChecked(values.apply_to_all_accounts)
        enabled_ids = set(self._automatic_mining_session_ids)
        self._automatic_mining_session_ids.clear()
        for session_id in enabled_ids:
            session = self._account_sessions.get(session_id)
            if session is not None:
                session.automatic_guard_started_at = None
                session.automation_state = AutomationState.OFF
        stopped = self._stop_auto_started_sessions(enabled_ids)
        if enabled_ids:
            logging.getLogger(__name__).info(
                "加载设置已关闭持续任务检测；停止 %s 个自动运行，手动运行保持",
                stopped,
            )
        # 当前任务属于运行时数据；即使旧设置里有 task_ids 也不再恢复，
        # 避免第二天加载已经过期的任务。
        if hasattr(self, "_task_refresh_timer"):
            self._restore_active_session()
        self._refresh_cookie_profile_combo()
        self._update_global_run_controls()

    def _load_stored_settings_silent(self) -> None:
        try:
            payload = load_stored_config_data(self._credential_store)
            if payload:
                self._apply_stored_config_values(
                    values_from_config_data(payload),
                    preserve_account_fields=True,
                )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "已保存设置自动加载失败: %s",
                exc,
            )

    def load_config(self) -> None:
        try:
            payload = load_stored_config_data(self._credential_store)
            if not payload:
                self._show_warning("暂无设置", "还没有保存过程序设置。")
                return
            self._apply_stored_config_values(
                values_from_config_data(payload)
            )
            logging.getLogger(__name__).info(
                "设置已从统一凭据文件加载: %s",
                cookie_store_path(),
            )
        except Exception as exc:
            self._show_error("加载失败", str(exc))

    def save_config(self) -> None:
        try:
            config = self._build_config()
            target_sessions = self._scope_sessions()
            self._store_current_secrets()
            save_stored_config_data(
                self._credential_store,
                build_config_payload(
                    config,
                    verbose=self.verbose_check.isChecked(),
                    minimize_to_tray=self.minimize_to_tray_check.isChecked(),
                    close_to_tray=self.close_to_tray_check.isChecked(),
                    auto_check_updates=(
                        self.auto_check_updates_check.isChecked()
                    ),
                    # 持续任务检测仅在当前运行中有效，不能成为启动项。
                    automatic_mining_enabled=False,
                    apply_to_all_accounts=self.apply_all_switch.isChecked(),
                ),
            )
            if not self._persist_account_settings_for(target_sessions):
                raise OSError("账号级设置保存失败")
            logging.getLogger(__name__).info(
                "全局默认与账号设置已保存到统一凭据文件: %s",
                cookie_store_path(),
            )
        except Exception as exc:
            self._show_error("保存失败", str(exc))


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    configure_qt_app(app)
    install_window_chrome(app)
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        return 0
    window = MinerGUI()
    instance_guard.activation_requested.connect(
        window.activate_existing_instance
    )
    # Keep both objects alive for the full Qt event loop.
    app._bilidrop_instance_guard = instance_guard
    app._bilidrop_main_window = window
    window.show()
    return app.exec()
