from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QIntValidator,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_drops_miner.config import (
    DEFAULT_SESSIONS_PER_ROOM,
    MAX_RECONNECT_DELAY_SECONDS,
    MAX_SESSIONS_PER_ROOM,
    MAX_TASK_QUERY_INTERVAL_SECONDS,
    MIN_RECONNECT_DELAY_SECONDS,
    MIN_TASK_QUERY_INTERVAL_SECONDS,
)
from bilibili_drops_miner.gui_parts.styles import (
    BUTTON_STYLES,
    CARD_STYLE,
    DISABLED_BUTTON_STYLE,
)


@dataclass(slots=True)
class MainWindowCallbacks:
    auto_fetch_cookie: Callable[..., None]
    auto_fetch_room_id: Callable[..., None]
    auto_fetch_task_ids: Callable[..., None]
    auto_fetch_overwatch_esports: Callable[..., None]
    toggle_run: Callable[..., None]
    boost_concurrency: Callable[..., None]
    load_config: Callable[..., None]
    save_config: Callable[..., None]
    select_cookie_profile: Callable[..., None]
    save_cookie_profile: Callable[..., None]
    delete_cookie_profile: Callable[..., None]
    clear_logs: Callable[..., None]
    claim_rewards: Callable[..., None]
    refresh_tasks: Callable[..., None]
    open_settings_log: Callable[..., None]
    toggle_cookie_visibility: Callable[..., None]
    toggle_notify_visibility: Callable[..., None]
    test_notification: Callable[..., None]
    export_diagnostics: Callable[..., None]


@dataclass(slots=True)
class MainWindowWidgets:
    cookie_edit: QLineEdit
    rooms_edit: QLineEdit
    task_ids_edit: QLineEdit
    notify_urls_edit: QLineEdit
    cookie_profile_combo: QComboBox
    cookie_remark_edit: QLineEdit
    threads_spin: NumericLineEdit
    reconnect_spin: NumericLineEdit
    task_interval_spin: NumericLineEdit
    verbose_check: QCheckBox
    disable_task_notify_check: QCheckBox
    progress_bar: QProgressBar
    task_table: QTableWidget
    log_text: QPlainTextEdit
    settings_dialog: QDialog
    settings_tabs: QTabWidget
    settings_button: QPushButton
    claim_rewards_btn: QPushButton
    start_btn: QPushButton
    boost_concurrency_btn: QPushButton
    apply_all_switch: ToggleSwitch
    auto_mining_description: QLabel
    concurrency_mode_combo: QComboBox
    minimize_to_tray_check: QCheckBox
    close_to_tray_check: QCheckBox
    auto_check_updates_check: QCheckBox
    discover_btn: QPushButton
    overwatch_esports_btn: QPushButton
    cookie_reveal_btn: QPushButton
    save_cookie_profile_btn: QPushButton
    delete_cookie_profile_btn: QPushButton
    notify_reveal_btn: QPushButton
    runtime_state_label: QLabel
    runtime_detail_label: QLabel
    discovery_status_label: QLabel
    watch_time_label: QLabel


class NumericLineEdit(QLineEdit):
    """A bounded integer field with no steppers or wheel-based changes."""

    def __init__(self, minimum: int, maximum: int, value: int) -> None:
        super().__init__()
        self._minimum = minimum
        self._maximum = maximum
        self.setValidator(QIntValidator(minimum, maximum, self))
        self.setInputMethodHints(Qt.ImhDigitsOnly)
        self.setValue(value)

    def value(self) -> int:
        try:
            value = int(self.text().strip())
        except ValueError:
            value = self._minimum
        return max(self._minimum, min(self._maximum, value))

    def setValue(self, value: int) -> None:
        bounded = max(self._minimum, min(self._maximum, int(value)))
        self.setText(str(bounded))

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.setValue(self.value())
        super().focusOutEvent(event)


class ToggleSwitch(QCheckBox):
    """Compact iOS-style boolean switch without the native focus rectangle."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        opacity = 1.0 if self.isEnabled() else 0.45
        painter.setOpacity(opacity)
        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(
            QColor("#f59e0b" if self.isChecked() else "#4b5563")
        )
        painter.drawRoundedRect(
            track,
            track.height() / 2,
            track.height() / 2,
        )
        knob_size = track.height() - 4
        knob_x = (
            track.right() - knob_size - 2
            if self.isChecked()
            else track.left() + 2
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(
            QRectF(knob_x, track.top() + 2, knob_size, knob_size)
        )


def build_main_window_layout(
    window: QMainWindow,
    callbacks: MainWindowCallbacks,
) -> MainWindowWidgets:
    scroll = QScrollArea(window)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    window.setCentralWidget(scroll)
    central = QWidget()
    scroll.setWidget(central)
    root = QVBoxLayout(central)
    root.setContentsMargins(20, 18, 20, 20)
    root.setSpacing(12)

    header = QHBoxLayout()
    title = QLabel("Bilibili 直播掉宝助手")
    title.setFont(_font(16, bold=True))
    subtitle = QLabel("输入房间号，程序自动识别任务并管理挂机状态")
    subtitle.setStyleSheet("color:#aeb6c5;")
    title_stack = QVBoxLayout()
    title_stack.setSpacing(2)
    title_stack.addWidget(title)
    title_stack.addWidget(subtitle)
    header.addLayout(title_stack)
    header.addStretch(1)
    settings_button = _button("设置与日志", "gray", callbacks.open_settings_log)
    settings_button.setToolTip("打开高级设置和实时运行日志")
    header.addWidget(settings_button)
    runtime_state_label = QLabel("未运行")
    runtime_state_label.setObjectName("stateBadge")
    runtime_state_label.setAlignment(Qt.AlignCenter)
    runtime_state_label.setMinimumWidth(92)
    runtime_state_label.setStyleSheet(
        "background:#343a46;color:#e6e7eb;border-radius:12px;padding:6px 12px;font-weight:600;"
    )
    header.addWidget(runtime_state_label)
    root.addLayout(header)

    account_card, account_layout = _card("1  账号")
    cookie_profile_combo = QComboBox()
    cookie_profile_combo.setAccessibleName("账号档案与临时账号")
    cookie_profile_combo.currentIndexChanged.connect(callbacks.select_cookie_profile)
    cookie_profile_combo.setMinimumWidth(260)
    cookie_profile_combo.setMaximumWidth(520)
    cookie_remark_edit = _line_edit("账号备注，例如主号")
    cookie_remark_edit.setMinimumWidth(150)
    cookie_remark_edit.setMaximumWidth(230)
    save_cookie_profile_btn = _button(
        "保存档案",
        "blue",
        callbacks.save_cookie_profile,
    )
    delete_cookie_profile_btn = _button(
        "删除",
        "gray",
        callbacks.delete_cookie_profile,
    )
    account_row = QHBoxLayout()
    account_row.setSpacing(8)
    account_row.addWidget(_buddy_label("账号档案", cookie_profile_combo))
    cookie_profile_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    cookie_remark_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    account_row.addWidget(cookie_profile_combo, 3)
    account_row.addWidget(cookie_remark_edit, 2)
    account_row.addWidget(save_cookie_profile_btn)
    account_row.addWidget(delete_cookie_profile_btn)
    account_layout.addLayout(account_row)
    cookie_edit = _line_edit("SESSDATA、bili_jct 等登录 Cookie")
    cookie_edit.setEchoMode(QLineEdit.Password)
    cookie_edit.setAccessibleName("Bilibili Cookie")
    cookie_reveal_btn = _button("显示", "gray", callbacks.toggle_cookie_visibility)
    account_layout.addLayout(
        _form_row(
            "Cookie",
            cookie_edit,
            cookie_reveal_btn,
            _button("扫码登录", "purple", callbacks.auto_fetch_cookie),
        )
    )
    root.addWidget(account_card)

    room_card, room_layout = _card("2  直播与任务")
    rooms_edit = _line_edit("直播间号或直播间 URL，多个用英文逗号分隔")
    rooms_edit.setAccessibleName("直播间号")
    discover_btn = _button("识别当前任务", "blue", callbacks.auto_fetch_task_ids)
    overwatch_esports_btn = _button(
        "守望先锋电竞",
        "gray",
        callbacks.auto_fetch_overwatch_esports,
    )
    overwatch_esports_btn.setToolTip("设置房间 23612045 并立即识别")
    room_layout.addLayout(
        _form_row(
            "房间",
            rooms_edit,
            _button("浏览器获取", "gray", callbacks.auto_fetch_room_id),
            overwatch_esports_btn,
            discover_btn,
        )
    )
    discovery_status_label = QLabel(
        "填写房间号后点击“识别当前任务”；无需等待直播间开播"
    )
    discovery_status_label.setWordWrap(True)
    discovery_status_label.setStyleSheet("color:#aeb6c5;padding-left:92px;")
    room_layout.addWidget(discovery_status_label)
    root.addWidget(room_card)

    runtime_card, runtime_layout = _card("3  运行")
    runtime_header = QVBoxLayout()
    runtime_text = QVBoxLayout()
    runtime_detail_label = QLabel("连接 0/0 · 重连 0 · 等待启动")
    runtime_detail_label.setStyleSheet("color:#aeb6c5;")
    runtime_detail_label.setWordWrap(True)
    watch_time_label = QLabel()
    watch_time_label.setVisible(False)
    runtime_text.addWidget(runtime_detail_label)
    runtime_header.addLayout(runtime_text)
    action_row = QHBoxLayout()
    action_row.setSpacing(10)
    start_btn = _button("开始", "green", callbacks.toggle_run)
    start_btn.setMinimumWidth(150)
    boost_concurrency_btn = _button(
        "加速执行（本次 100 线程）",
        "gray",
        callbacks.boost_concurrency,
    )
    boost_concurrency_btn.setMinimumWidth(190)
    boost_concurrency_btn.setToolTip(
        "仅本次强制 100 线程；持续模式仍保存为固定 32，可在高级设置修改"
    )
    action_row.addWidget(start_btn)
    action_row.addWidget(boost_concurrency_btn)
    action_row.addStretch(1)
    scope_label = QLabel("应用到所有账号")
    scope_label.setStyleSheet("color:#c7ced9;")
    apply_all_switch = ToggleSwitch()
    apply_all_switch.setAccessibleName("应用到所有账号")
    apply_all_switch.setToolTip(
        "开启后，识别任务和“开始/停止”都会应用到所有账号；"
        "每个账号仍独立查询自己的进度"
    )
    scope_label.setBuddy(apply_all_switch)
    action_row.addWidget(scope_label)
    action_row.addWidget(apply_all_switch)
    runtime_header.addLayout(action_row)
    auto_mining_description = QLabel(
        "当前只操作所选账号。开始后启动观看线程和后台任务检测；"
        "停止只关闭观看线程，后台检测保留到程序退出。"
    )
    auto_mining_description.setWordWrap(True)
    auto_mining_description.setStyleSheet("color:#8f9bad;font-size:9pt;")
    runtime_header.addWidget(auto_mining_description)
    runtime_layout.addLayout(runtime_header)
    progress_bar = QProgressBar()
    progress_bar.setTextVisible(False)
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)
    progress_bar.setVisible(False)
    runtime_layout.addWidget(progress_bar)
    root.addWidget(runtime_card)

    task_card, task_layout = _card("任务进度")
    task_header = QHBoxLayout()
    task_header.addStretch(1)
    claim_rewards_btn = _button("手动领取", "blue", callbacks.claim_rewards)
    claim_rewards_btn.setToolTip("奖励会自动领取；自动领取失败时可在此手动重试")
    claim_rewards_btn.setEnabled(False)
    task_header.addWidget(claim_rewards_btn)
    task_header.addWidget(_button("刷新", "gray", callbacks.refresh_tasks))
    task_layout.addLayout(task_header)
    task_table = QTableWidget(0, 5)
    task_table.setHorizontalHeaderLabels(["任务 / 奖励节点", "进度", "状态", "奖励", "领取"])
    task_table.setAccessibleName("任务进度列表")
    task_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    task_table.setAlternatingRowColors(True)
    task_table.verticalHeader().setVisible(False)
    task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for column in (1, 2, 3, 4):
        task_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
    task_table.setMinimumHeight(190)
    task_layout.addWidget(task_table)
    root.addWidget(task_card)
    root.addStretch(1)

    settings_dialog = QDialog(window)
    settings_dialog.setWindowTitle("设置与日志")
    settings_dialog.setModal(False)
    settings_dialog.resize(900, 640)
    settings_dialog_layout = QVBoxLayout(settings_dialog)
    settings_dialog_layout.setContentsMargins(18, 16, 18, 18)
    settings_dialog_layout.setSpacing(12)
    dialog_title = QLabel("设置与日志")
    dialog_title.setFont(_font(15, bold=True))
    dialog_subtitle = QLabel("调整高级参数，或查看当前运行日志")
    dialog_subtitle.setStyleSheet("color:#aeb6c5;")
    settings_dialog_layout.addWidget(dialog_title)
    settings_dialog_layout.addWidget(dialog_subtitle)
    settings_tabs = QTabWidget()
    settings_dialog_layout.addWidget(settings_tabs, 1)

    advanced_scroll = QScrollArea()
    advanced_scroll.setWidgetResizable(True)
    advanced_scroll.setFrameShape(QFrame.NoFrame)
    advanced_page = QWidget()
    advanced_scroll.setWidget(advanced_page)
    advanced_stack = QVBoxLayout(advanced_page)
    advanced_stack.setContentsMargins(14, 14, 14, 14)
    advanced_stack.setSpacing(10)

    threads_spin = _numeric_input(
        1, MAX_SESSIONS_PER_ROOM, DEFAULT_SESSIONS_PER_ROOM
    )
    reconnect_spin = _numeric_input(
        MIN_RECONNECT_DELAY_SECONDS, MAX_RECONNECT_DELAY_SECONDS, 8
    )
    task_interval_spin = _numeric_input(
        MIN_TASK_QUERY_INTERVAL_SECONDS, MAX_TASK_QUERY_INTERVAL_SECONDS, 30
    )
    connection_group, connection_layout = _settings_group(
        "连接参数",
        "默认值适合普通使用；并发越高越容易触发平台限频。",
    )
    connection_fields = QHBoxLayout()
    connection_fields.setSpacing(12)
    for title, control in (
        ("每房间并发会话", threads_spin),
        ("断线重试等待（秒）", reconnect_spin),
        ("任务刷新间隔（秒）", task_interval_spin),
    ):
        connection_fields.addWidget(_field_widget(title, control), 1)
    connection_layout.addLayout(connection_fields)
    concurrency_mode_combo = QComboBox()
    concurrency_mode_combo.addItem(
        "自动调节（追赶 16，3 分钟检测后 2）", "automatic"
    )
    concurrency_mode_combo.addItem("固定并发", "fixed")
    concurrency_mode_combo.setToolTip(
        "自动模式先用 16 个心跳会话；3 分钟进度增量不足 16 时降为 2 个，"
        "并保持到下一组新任务。后台检测到初始进度为 0 的新任务直接使用 2 个。"
    )
    connection_layout.addWidget(
        _field_widget("并发模式", concurrency_mode_combo)
    )
    advanced_stack.addWidget(connection_group)

    task_ids_edit = _line_edit("自动识别结果；仅排障时需要手动修改")
    task_ids_edit.setAccessibleName("任务 ID 高级设置")
    task_group, task_group_layout = _settings_group(
        "任务识别",
        "正常情况下由房间号自动识别。只有自动识别失败时，才需要手动填写任务 ID。",
    )
    task_group_layout.addWidget(task_ids_edit)
    advanced_stack.addWidget(task_group)

    notify_urls_edit = _line_edit(
        "Telegram：tgram://BotToken/ChatID；也支持 Gotify、Server 酱、企业微信"
    )
    notify_urls_edit.setEchoMode(QLineEdit.Password)
    notify_urls_edit.setAccessibleName("通知地址")
    notify_urls_edit.setToolTip(
        "Telegram 格式：tgram://BotToken/ChatID；多个通知地址用逗号分隔"
    )
    notify_reveal_btn = _button("显示", "gray", callbacks.toggle_notify_visibility)
    notification_group, notification_layout = _settings_group(
        "通知与运行行为",
        "Telegram 使用 tgram://BotToken/ChatID；通知地址会隐藏并保存在受保护凭据中。",
    )
    notification_row = QHBoxLayout()
    notification_row.setSpacing(8)
    notification_row.addWidget(notify_urls_edit, 1)
    notification_row.addWidget(notify_reveal_btn)
    notification_row.addWidget(_button("测试通知", "gray", callbacks.test_notification))
    notification_layout.addLayout(notification_row)

    verbose_check = QCheckBox("输出详细运行日志")
    disable_task_notify_check = QCheckBox("不发送任务完成通知")
    option_row = QHBoxLayout()
    option_row.setSpacing(20)
    option_row.addWidget(verbose_check)
    option_row.addWidget(disable_task_notify_check)
    option_row.addStretch(1)
    notification_layout.addLayout(option_row)
    advanced_stack.addWidget(notification_group)

    desktop_group, desktop_layout = _settings_group(
        "桌面运行",
        "默认最小化和关闭主窗口后继续驻留托盘；可在这里恢复普通窗口行为。",
    )
    minimize_to_tray_check = QCheckBox("最小化到托盘")
    minimize_to_tray_check.setChecked(True)
    close_to_tray_check = QCheckBox("关闭到托盘")
    close_to_tray_check.setChecked(True)
    auto_check_updates_check = QCheckBox("启动时检查更新")
    auto_check_updates_check.setChecked(True)
    auto_check_updates_check.setToolTip(
        "只检查 GitHub Release；发现新版本后询问是否打开发布页，不自动下载或安装"
    )
    desktop_options = QHBoxLayout()
    desktop_options.setSpacing(20)
    desktop_options.addWidget(minimize_to_tray_check)
    desktop_options.addWidget(close_to_tray_check)
    desktop_options.addWidget(auto_check_updates_check)
    desktop_options.addStretch(1)
    desktop_layout.addLayout(desktop_options)
    advanced_stack.addWidget(desktop_group)

    settings_actions = QHBoxLayout()
    settings_actions.setSpacing(8)
    settings_actions.addWidget(_button("导出诊断", "gray", callbacks.export_diagnostics))
    settings_actions.addStretch(1)
    settings_actions.addWidget(_button("加载设置", "gray", callbacks.load_config))
    settings_actions.addWidget(_button("保存设置", "blue", callbacks.save_config))
    advanced_stack.addLayout(settings_actions)
    advanced_stack.addStretch(1)
    settings_tabs.addTab(advanced_scroll, "高级设置")

    log_page = QWidget()
    log_layout = QVBoxLayout(log_page)
    log_layout.setContentsMargins(14, 14, 14, 14)
    log_layout.setSpacing(10)
    log_head = QHBoxLayout()
    log_title = QLabel("实时运行日志")
    log_title.setFont(_font(11, bold=True))
    log_head.addWidget(log_title)
    log_head.addStretch(1)
    log_head.addWidget(_button("清空", "gray", callbacks.clear_logs))
    log_layout.addLayout(log_head)
    log_text = QPlainTextEdit()
    log_text.setReadOnly(True)
    log_text.setFont(QFont("Consolas", 10))
    log_text.setMaximumBlockCount(5000)
    log_text.setMinimumHeight(420)
    log_layout.addWidget(log_text, 1)
    settings_tabs.addTab(log_page, "运行日志")

    return MainWindowWidgets(
        cookie_edit=cookie_edit,
        rooms_edit=rooms_edit,
        task_ids_edit=task_ids_edit,
        notify_urls_edit=notify_urls_edit,
        cookie_profile_combo=cookie_profile_combo,
        cookie_remark_edit=cookie_remark_edit,
        threads_spin=threads_spin,
        reconnect_spin=reconnect_spin,
        task_interval_spin=task_interval_spin,
        verbose_check=verbose_check,
        disable_task_notify_check=disable_task_notify_check,
        progress_bar=progress_bar,
        task_table=task_table,
        log_text=log_text,
        settings_dialog=settings_dialog,
        settings_tabs=settings_tabs,
        settings_button=settings_button,
        claim_rewards_btn=claim_rewards_btn,
        start_btn=start_btn,
        boost_concurrency_btn=boost_concurrency_btn,
        apply_all_switch=apply_all_switch,
        auto_mining_description=auto_mining_description,
        concurrency_mode_combo=concurrency_mode_combo,
        minimize_to_tray_check=minimize_to_tray_check,
        close_to_tray_check=close_to_tray_check,
        auto_check_updates_check=auto_check_updates_check,
        discover_btn=discover_btn,
        overwatch_esports_btn=overwatch_esports_btn,
        cookie_reveal_btn=cookie_reveal_btn,
        save_cookie_profile_btn=save_cookie_profile_btn,
        delete_cookie_profile_btn=delete_cookie_profile_btn,
        notify_reveal_btn=notify_reveal_btn,
        runtime_state_label=runtime_state_label,
        runtime_detail_label=runtime_detail_label,
        discovery_status_label=discovery_status_label,
        watch_time_label=watch_time_label,
    )


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(CARD_STYLE)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 14, 18, 16)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setFont(_font(11, bold=True))
        layout.addWidget(label)
    return card, layout


def _font(size: int, *, bold: bool = False) -> QFont:
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    return font


def _line_edit(placeholder: str) -> QLineEdit:
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    return widget


def _numeric_input(minimum: int, maximum: int, value: int) -> NumericLineEdit:
    return NumericLineEdit(minimum, maximum, value)


def _button(text: str, color: str, slot: Callable[..., None]) -> QPushButton:
    button = QPushButton(text)
    button.setStyleSheet(
        BUTTON_STYLES.get(color, BUTTON_STYLES[""]) + DISABLED_BUTTON_STYLE
    )
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(slot)
    return button


def _buddy_label(text: str, buddy: QWidget) -> QLabel:
    label = QLabel(text)
    label.setBuddy(buddy)
    label.setStyleSheet("color:#aeb6c5;")
    label.setMinimumWidth(76)
    return label


def _form_row(label: str, primary: QWidget, *extras: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_buddy_label(label, primary))
    primary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    row.addWidget(primary, 1)
    for widget in extras:
        row.addWidget(widget)
    return row


def _settings_group(
    title: str,
    description: str,
) -> tuple[QFrame, QVBoxLayout]:
    group = QFrame()
    group.setObjectName("settingsGroup")
    group.setStyleSheet(
        "QFrame#settingsGroup{background:#20242d;border:1px solid #323845;"
        "border-radius:8px;}"
    )
    layout = QVBoxLayout(group)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setFont(_font(10, bold=True))
    layout.addWidget(title_label)
    description_label = QLabel(description)
    description_label.setWordWrap(True)
    description_label.setStyleSheet("color:#9da7b8;")
    layout.addWidget(description_label)
    return group, layout


def _field_widget(title: str, control: QWidget) -> QWidget:
    field = QWidget()
    layout = QVBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    label = _buddy_label(title, control)
    label.setMinimumWidth(0)
    layout.addWidget(label)
    control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    layout.addWidget(control)
    return field


def _runtime_action_group(
    title: str,
    primary: QPushButton,
    secondary: QPushButton,
) -> QWidget:
    group = QFrame()
    group.setObjectName("runtimeActionGroup")
    group.setStyleSheet(
        "QFrame#runtimeActionGroup{background:#20242d;border:1px solid #323845;"
        "border-radius:8px;}"
    )
    layout = QVBoxLayout(group)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(7)
    label = QLabel(title)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("color:#aeb6c5;font-size:9pt;")
    layout.addWidget(label)
    buttons = QHBoxLayout()
    buttons.setSpacing(6)
    buttons.addWidget(primary, 1)
    buttons.addWidget(secondary, 1)
    layout.addLayout(buttons)
    return group
