from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


COOKIE_STORE_NAME = "cookies.json"


@dataclass(slots=True)
class CookieProfile:
    remark: str
    cookie: str
    updated_at: str = ""


def cookie_store_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().with_name(COOKIE_STORE_NAME)
    return Path.cwd() / COOKIE_STORE_NAME


def default_cookie_remark(cookie: str) -> str:
    match = re.search(r"(?:^|;\s*)DedeUserID=([^;]+)", cookie)
    if match:
        return f"UID {match.group(1)}"
    return time.strftime("Cookie %Y-%m-%d %H:%M:%S")


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_cookie_profiles(path: str | Path | None = None) -> list[CookieProfile]:
    store_path = Path(path) if path is not None else cookie_store_path()
    if not store_path.exists():
        return []

    payload = json.loads(store_path.read_text(encoding="utf-8"))
    raw_profiles: Any
    if isinstance(payload, dict):
        raw_profiles = payload.get("cookies", [])
    else:
        raw_profiles = payload

    if not isinstance(raw_profiles, list):
        raise ValueError("Cookie 档案文件必须是列表或包含 cookies 列表的 JSON 对象")

    profiles: list[CookieProfile] = []
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            continue
        cookie = str(raw.get("cookie", "")).strip()
        if not cookie:
            continue
        remark = str(raw.get("remark", "")).strip() or default_cookie_remark(cookie)
        updated_at = str(raw.get("updated_at", "")).strip()
        profiles.append(CookieProfile(remark=remark, cookie=cookie, updated_at=updated_at))
    return profiles


def save_cookie_profiles(
    profiles: list[CookieProfile],
    path: str | Path | None = None,
) -> None:
    store_path = Path(path) if path is not None else cookie_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cookies": [asdict(profile) for profile in profiles]}
    store_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
