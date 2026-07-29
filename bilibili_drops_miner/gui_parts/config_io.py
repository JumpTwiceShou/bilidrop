from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bilibili_drops_miner.config import DEFAULT_SESSIONS_PER_ROOM, MinerConfig
from bilibili_drops_miner.credential_store import CredentialStore


APP_SETTINGS_CREDENTIAL_ID = "application-settings"
CONCURRENCY_POLICY_VERSION = 2


@dataclass(slots=True)
class GuiConfigValues:
    cookie: str
    rooms_text: str
    thread_count_text: str
    reconnect_delay_text: str
    task_ids_text: str
    task_query_interval_text: str
    notify_urls_text: str
    notify_on_task_complete: bool
    verbose: bool
    concurrency_mode: str
    minimize_to_tray: bool
    close_to_tray: bool
    automatic_mining_enabled: bool
    apply_to_all_accounts: bool


def load_config_data(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("配置文件必须是 JSON 对象")
    return payload


def values_from_config_data(data: dict[str, Any]) -> GuiConfigValues:
    policy_version = int(data.get("concurrency_policy_version", 0) or 0)
    concurrency_mode = str(data.get("concurrency_mode", "automatic"))
    if policy_version < CONCURRENCY_POLICY_VERSION:
        # Older GUI builds wrote their then-default "fixed" value even when
        # the user never made a policy choice. Migrate that implicit default
        # once; fixed mode explicitly saved by this version remains fixed.
        concurrency_mode = "automatic"
    return GuiConfigValues(
        cookie=str(data.get("cookie", "")),
        rooms_text=",".join(str(x) for x in data.get("room_ids", [])),
        thread_count_text=str(data.get("thread_count", DEFAULT_SESSIONS_PER_ROOM)),
        reconnect_delay_text=str(data.get("reconnect_delay_seconds", 8)),
        task_ids_text=",".join(str(x) for x in data.get("task_ids", [])),
        task_query_interval_text=str(data.get("task_query_interval_seconds", 30)),
        notify_urls_text=",".join(str(x) for x in data.get("notify_urls", [])),
        notify_on_task_complete=bool(data.get("notify_on_task_complete", True)),
        verbose=bool(data.get("verbose", False)),
        concurrency_mode=concurrency_mode,
        minimize_to_tray=bool(data.get("minimize_to_tray", True)),
        close_to_tray=bool(data.get("close_to_tray", True)),
        automatic_mining_enabled=bool(
            data.get("automatic_mining_enabled", False)
        ),
        apply_to_all_accounts=bool(
            data.get("apply_to_all_accounts", False)
        ),
    )


def build_config_payload(
    config: MinerConfig,
    *,
    verbose: bool,
    include_secrets: bool = False,
    minimize_to_tray: bool = True,
    close_to_tray: bool = True,
    automatic_mining_enabled: bool = False,
    apply_to_all_accounts: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "room_ids": config.room_ids,
        "thread_count": config.thread_count,
        "reconnect_delay_seconds": config.reconnect_delay_seconds,
        "enable_web_heartbeat": config.enable_web_heartbeat,
        "task_ids": config.task_ids,
        "task_query_interval_seconds": config.task_query_interval_seconds,
        "notify_on_task_complete": config.notify_on_task_complete,
        "concurrency_mode": config.concurrency_mode,
        "concurrency_policy_version": CONCURRENCY_POLICY_VERSION,
        "minimize_to_tray": minimize_to_tray,
        "close_to_tray": close_to_tray,
        "automatic_mining_enabled": automatic_mining_enabled,
        "apply_to_all_accounts": apply_to_all_accounts,
        "verbose": verbose,
    }
    if include_secrets:
        payload["cookie"] = config.cookie
        payload["notify_urls"] = config.notify_urls
    return payload


def save_config_data(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_stored_config_data(credential_store: CredentialStore) -> dict[str, Any]:
    encoded = credential_store.get(APP_SETTINGS_CREDENTIAL_ID)
    if not encoded:
        return {}
    payload = json.loads(encoded)
    if not isinstance(payload, dict):
        raise ValueError("已保存设置格式错误")
    return payload


def save_stored_config_data(
    credential_store: CredentialStore,
    data: dict[str, Any],
) -> None:
    if any(key in data for key in ("cookie", "notify_urls")):
        raise ValueError("普通设置不能重复保存 Cookie 或通知地址")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    credential_store.set(APP_SETTINGS_CREDENTIAL_ID, encoded)
    if load_stored_config_data(credential_store) != data:
        raise OSError("设置写入校验失败")
