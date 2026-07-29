from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bilibili_drops_miner.credential_store import (
    CredentialStore,
    JsonCredentialStore,
    default_credential_store_path,
)


LOGGER = logging.getLogger(__name__)
COOKIE_STORE_NAME = "cookies.json"
COOKIE_PROFILE_METADATA_KEY = "cookie_profiles"


@dataclass(slots=True)
class CookieProfile:
    remark: str
    cookie: str
    updated_at: str = ""
    credential_id: str = ""


@dataclass(slots=True)
class CookieProfileState:
    profiles: list[CookieProfile]
    last_selected_credential_id: str = ""


def cookie_store_path() -> Path:
    """Return the single combined profile/credential file used by the app."""

    return default_credential_store_path()


def legacy_cookie_store_path() -> Path:
    """Return the only legacy location eligible for automatic migration."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().with_name(COOKIE_STORE_NAME)
    return Path.cwd() / COOKIE_STORE_NAME


def default_cookie_remark(cookie: str) -> str:
    uid = extract_cookie_uid(cookie)
    if uid:
        return f"UID {uid}"
    return time.strftime("Cookie %Y-%m-%d %H:%M:%S")


def extract_cookie_uid(cookie: str) -> str:
    match = re.search(r"(?:^|;\s*)DedeUserID=([^;]+)", cookie)
    return match.group(1).strip() if match else ""


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _legacy_credential_id(cookie: str) -> str:
    return f"cookie-{uuid.uuid5(uuid.NAMESPACE_URL, 'bilidrop:' + cookie).hex}"


def _state_from_payload(
    payload: Any,
    credential_store: CredentialStore,
) -> CookieProfileState:
    raw_profiles: Any
    if isinstance(payload, dict):
        raw_profiles = payload.get("accounts")
        if raw_profiles is None:
            raw_profiles = payload.get("cookies", [])
        last_selected_credential_id = str(
            payload.get("last_selected_credential_id") or ""
        ).strip()
    else:
        raw_profiles = payload
        last_selected_credential_id = ""

    if not isinstance(raw_profiles, list):
        raise ValueError("Cookie 档案必须是列表或包含 accounts/cookies 列表的对象")

    profiles: list[CookieProfile] = []
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            continue
        legacy_cookie = str(raw.get("cookie", "")).strip()
        credential_id = str(raw.get("credential_id", "")).strip()
        if legacy_cookie and not credential_id:
            credential_id = _legacy_credential_id(legacy_cookie)
        if legacy_cookie:
            credential_store.set(credential_id, legacy_cookie)
        cookie = credential_store.get(credential_id) if credential_id else ""
        if not cookie:
            continue
        profiles.append(
            CookieProfile(
                remark=(
                    str(raw.get("remark", "")).strip()
                    or default_cookie_remark(cookie)
                ),
                cookie=cookie,
                updated_at=str(raw.get("updated_at", "")).strip(),
                credential_id=credential_id,
            )
        )

    if not any(
        profile.credential_id == last_selected_credential_id
        for profile in profiles
    ):
        last_selected_credential_id = ""
    return CookieProfileState(profiles, last_selected_credential_id)


def _metadata_state(credential_store: CredentialStore) -> CookieProfileState:
    payload = credential_store.get_metadata(COOKIE_PROFILE_METADATA_KEY)
    if payload is None:
        return CookieProfileState([])
    return _state_from_payload(payload, credential_store)


def _read_legacy_state(
    path: Path,
    credential_store: CredentialStore,
) -> CookieProfileState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _state_from_payload(payload, credential_store)


def _merge_states(
    current: CookieProfileState,
    legacy: CookieProfileState,
) -> CookieProfileState:
    profiles = list(current.profiles)
    known_ids = {profile.credential_id for profile in profiles}
    for profile in legacy.profiles:
        if profile.credential_id in known_ids:
            continue
        profiles.append(profile)
        known_ids.add(profile.credential_id)
    selected_id = (
        current.last_selected_credential_id
        or legacy.last_selected_credential_id
    )
    if selected_id not in known_ids:
        selected_id = ""
    return CookieProfileState(profiles, selected_id)


def _profile_signature(state: CookieProfileState) -> tuple:
    return (
        tuple(
            (
                profile.credential_id,
                profile.remark,
                profile.updated_at,
                profile.cookie,
            )
            for profile in state.profiles
        ),
        state.last_selected_credential_id,
    )


def _legacy_archive_path(source: Path) -> Path:
    archive_dir = default_credential_store_path().parent / "legacy"
    archive_dir.mkdir(parents=True, exist_ok=True)
    candidate = archive_dir / f"{source.name}.legacy.bak"
    if not candidate.exists():
        return candidate
    suffix = time.strftime("%Y%m%d-%H%M%S")
    return archive_dir / f"{source.name}.{suffix}.{uuid.uuid4().hex[:6]}.legacy.bak"


def _archive_legacy_file(source: Path) -> None:
    target = _legacy_archive_path(source)
    shutil.move(str(source), str(target))
    LOGGER.info("旧版 Cookie 档案已迁移到 %s", target)


def load_cookie_profiles(
    path: str | Path | None = None,
    *,
    credential_store: CredentialStore | None = None,
) -> list[CookieProfile]:
    return load_cookie_profile_state(
        path,
        credential_store=credential_store,
    ).profiles


def load_cookie_profile_state(
    path: str | Path | None = None,
    *,
    credential_store: CredentialStore | None = None,
) -> CookieProfileState:
    # An explicit path is a compatibility/import source and is never moved.
    if path is not None:
        source = Path(path)
        store = credential_store or JsonCredentialStore()
        if not source.exists():
            return CookieProfileState([])
        return _read_legacy_state(source, store)

    store = credential_store or JsonCredentialStore()
    current = _metadata_state(store)
    legacy_path = legacy_cookie_store_path()
    if not legacy_path.exists():
        return current

    legacy = _read_legacy_state(legacy_path, store)
    merged = _merge_states(current, legacy)
    save_cookie_profiles(
        merged.profiles,
        credential_store=store,
        last_selected_credential_id=merged.last_selected_credential_id,
    )
    verified = _metadata_state(store)
    if _profile_signature(verified) != _profile_signature(merged):
        raise OSError("旧版 Cookie 档案迁移校验失败，原文件已保留")
    try:
        _archive_legacy_file(legacy_path)
    except OSError as exc:
        # The encrypted combined file is already valid; retaining the source is
        # safe and lets the application retry moving it on the next launch.
        LOGGER.warning("旧版 Cookie 档案归档失败，原文件已保留: %s", exc)
    return verified


def save_cookie_profiles(
    profiles: list[CookieProfile],
    path: str | Path | None = None,
    *,
    credential_store: CredentialStore | None = None,
    last_selected_credential_id: str = "",
) -> None:
    if credential_store is not None:
        store = credential_store
    else:
        store = JsonCredentialStore(Path(path) if path is not None else None)

    accounts: list[dict[str, str]] = []
    for profile in profiles:
        credential_id = profile.credential_id or f"cookie-{uuid.uuid4().hex}"
        store.set(credential_id, profile.cookie)
        if store.get(credential_id) != profile.cookie:
            raise OSError(f"Cookie 凭据校验失败: {profile.remark}")
        profile.credential_id = credential_id
        accounts.append(
            {
                "remark": profile.remark,
                "credential_id": credential_id,
                "updated_at": profile.updated_at,
            }
        )

    valid_ids = {item["credential_id"] for item in accounts}
    selected_id = (
        last_selected_credential_id
        if last_selected_credential_id in valid_ids
        else ""
    )
    expected = {
        "version": 4,
        "last_selected_credential_id": selected_id,
        "accounts": accounts,
    }
    store.set_metadata(COOKIE_PROFILE_METADATA_KEY, expected)
    if store.get_metadata(COOKIE_PROFILE_METADATA_KEY) != expected:
        raise OSError("Cookie 档案元数据写入校验失败")
