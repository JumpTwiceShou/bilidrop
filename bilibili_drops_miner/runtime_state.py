from __future__ import annotations

from enum import Enum


class RunOwner(str, Enum):
    NONE = "none"
    MANUAL = "manual"
    AUTO = "auto"


class AutomationState(str, Enum):
    OFF = "off"
    ARMED = "armed"
    CHECKING = "checking"
    WAITING_TASK = "waiting_task"
    WAITING_LIVE = "waiting_live"
    AUTO_RUNNING = "auto_running"
    CLAIMING = "claiming"
    COOLDOWN = "cooldown"


class TaskPhase(str, Enum):
    UNKNOWN = "unknown"
    FUTURE = "future"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
