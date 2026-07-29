from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import time

from bilibili_drops_miner.client_parts.models import TaskProgress


class ApplicationState(str, Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class DiscoveryStatus(str, Enum):
    SUCCESS = "success"
    AMBIGUOUS = "ambiguous"
    OFFLINE = "offline"
    NO_BROWSER = "no_browser"
    NO_TASKS = "no_tasks"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    label: str
    credential_id: str = ""
    uid: int | None = None


@dataclass(frozen=True, slots=True)
class RoomConfiguration:
    room_ids: tuple[int, ...]
    sessions_per_room: int


@dataclass(frozen=True, slots=True)
class DiscoveredTaskGroup:
    label: str
    task_ids: tuple[str, ...]
    active: bool = False
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TaskDiscoveryResult:
    room_id: int
    status: DiscoveryStatus
    groups: tuple[DiscoveredTaskGroup, ...] = field(default_factory=tuple)
    selected_group: DiscoveredTaskGroup | None = None
    browser: str = ""
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status in {DiscoveryStatus.SUCCESS, DiscoveryStatus.AMBIGUOUS}


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    state: ApplicationState = ApplicationState.IDLE
    active_sessions: int = 0
    target_sessions: int = 0
    reconnect_count: int = 0
    last_heartbeat_at: float | None = None
    last_error: str = ""
    concurrency_mode: str = ""
    concurrency_phase: str = ""
    concurrency_detail: str = ""


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    progresses: tuple[TaskProgress, ...] = field(default_factory=tuple)
    refreshed_at: float = field(default_factory=time)
    error: str = ""

    @property
    def completed_count(self) -> int:
        completed = 0
        for item in self.progresses:
            checkpoints = item.check_points or []
            if checkpoints:
                completed += sum(1 for point in checkpoints if point.is_completed)
            elif item.is_completed:
                completed += 1
        return completed
