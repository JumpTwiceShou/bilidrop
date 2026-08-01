from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from bilibili_drops_miner.config import DEFAULT_SESSIONS_PER_ROOM
from bilibili_drops_miner.domain import ApplicationState, RuntimeHealth, TaskSnapshot
from bilibili_drops_miner.gui_parts.cookie_profiles import extract_cookie_uid
from bilibili_drops_miner.gui_parts.worker_controller import WorkerController
from bilibili_drops_miner.request_coordinator import AccountRequestCoordinator
from bilibili_drops_miner.runtime_state import (
    AutomationState,
    RunOwner,
    TaskPhase,
)


DEFAULT_DISCOVERY_HINT = "填写房间号后点击“识别当前任务”；无需等待直播间开播"

STATE_LABELS = {
    ApplicationState.IDLE: "未运行",
    ApplicationState.DISCOVERING: "识别中",
    ApplicationState.STARTING: "启动中",
    ApplicationState.RUNNING: "挂机中",
    ApplicationState.STOPPING: "停止中",
    ApplicationState.ERROR: "异常",
}


class LoginState(str, Enum):
    UNKNOWN = "unknown"
    CHECKING = "checking"
    VALID = "valid"
    INVALID = "invalid"
    ERROR = "error"


LOGIN_STATE_LABELS = {
    LoginState.UNKNOWN: "登录未检测",
    LoginState.CHECKING: "登录检测中",
    LoginState.VALID: "登录有效",
    LoginState.INVALID: "登录失效",
    LoginState.ERROR: "登录检测失败",
}


@dataclass(slots=True)
class AccountWorkspace:
    session_id: str
    cookie: str = ""
    remark: str = ""
    credential_id: str = ""
    temporary: bool = True
    controller: WorkerController = field(
        default_factory=lambda: WorkerController(auto_force_stop_after_seconds=2.0)
    )
    task_controller: Any = None
    rooms_text: str = ""
    task_ids_text: str = ""
    thread_count: int = DEFAULT_SESSIONS_PER_ROOM
    reconnect_delay_seconds: int = 8
    task_query_interval_seconds: int = 30
    notify_on_task_complete: bool = True
    concurrency_mode: str = "automatic"
    account_settings_saved: bool = False
    run_owner: RunOwner = RunOwner.NONE
    automation_state: AutomationState = AutomationState.OFF
    task_phase: TaskPhase = TaskPhase.UNKNOWN
    configuration_generation: int = 0
    request_coordinator: AccountRequestCoordinator = field(
        default_factory=AccountRequestCoordinator
    )
    next_automatic_check_at: float = 0.0
    automatic_check_inflight: bool = False
    automatic_check_pending: bool = False
    automatic_guard_started_at: float | None = None
    runtime_concurrency_override: int | None = None
    completion_auto_stop_key: tuple[str, tuple[str, ...]] | None = None
    completion_auto_stop_bypass: bool = False
    task_started_at: datetime | None = None
    task_ends_at: datetime | None = None
    application_state: ApplicationState = ApplicationState.IDLE
    runtime_health: RuntimeHealth = field(default_factory=RuntimeHealth)
    latest_task_snapshot: TaskSnapshot = field(default_factory=TaskSnapshot)
    task_progress_result: str = ""
    live_watch_time_result: str = ""
    task_progress_pending: bool = False
    task_refresh_trigger_pending: bool = False
    pending_start_after_discovery: bool = False
    rediscovery_attempted_for_run: bool = False
    discovery_status_text: str = DEFAULT_DISCOVERY_HINT
    discovery_status_error: bool = False
    login_state: LoginState = LoginState.UNKNOWN
    login_check_generation: int = 0

    @classmethod
    def temporary_account(cls, *, cookie: str = "", remark: str = ""):
        return cls(
            session_id=f"temp:{uuid.uuid4().hex}",
            cookie=cookie,
            remark=remark,
            temporary=True,
        )

    @classmethod
    def saved_account(
        cls,
        *,
        credential_id: str,
        cookie: str,
        remark: str,
    ):
        identity = credential_id or uuid.uuid4().hex
        return cls(
            session_id=f"saved:{identity}",
            cookie=cookie,
            remark=remark,
            credential_id=credential_id,
            temporary=False,
        )

    @property
    def uid(self) -> str:
        return extract_cookie_uid(self.cookie)

    @property
    def state_label(self) -> str:
        return STATE_LABELS[self.application_state]

    @property
    def auto_started_runtime(self) -> bool:
        return self.run_owner == RunOwner.AUTO

    @auto_started_runtime.setter
    def auto_started_runtime(self, value: bool) -> None:
        if value:
            self.run_owner = RunOwner.AUTO
        elif self.run_owner == RunOwner.AUTO:
            self.run_owner = RunOwner.NONE

    def bump_configuration_generation(self) -> int:
        self.configuration_generation += 1
        return self.configuration_generation

    @property
    def selector_label(self) -> str:
        uid_label = f"UID {self.uid}" if self.uid else "UID 未识别"
        login_label = (
            LOGIN_STATE_LABELS[self.login_state]
            if self.cookie
            else "未登录"
        )
        if self.temporary:
            return (
                f"{uid_label} · 临时·关闭即删 · {login_label} · "
                f"{self.state_label}"
            )
        name = self.remark.strip() or "已保存账号"
        identity = "" if uid_label in name else f" · {uid_label}"
        return (
            f"{name}{identity} · 已保存 · {login_label} · "
            f"{self.state_label}"
        )

    @property
    def hint_text(self) -> str:
        uid_label = f"UID {self.uid}" if self.uid else "UID 尚未识别"
        login_label = (
            LOGIN_STATE_LABELS[self.login_state]
            if self.cookie
            else "未登录"
        )
        if self.temporary:
            return (
                f"临时账号 · {uid_label} · {login_label} · "
                "未保存，关闭程序后删除"
            )
        name = self.remark.strip() or "账号档案"
        return (
            f"已保存档案 · {name} · {uid_label} · {login_label} · "
            "默认记住最近使用"
        )
