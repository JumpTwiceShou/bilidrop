from __future__ import annotations

import base64
import copy
import ctypes
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from ctypes import wintypes
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class CredentialStore(ABC):
    @abstractmethod
    def get(self, credential_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def set(self, credential_id: str, secret: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, credential_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, key: str):
        raise NotImplementedError

    @abstractmethod
    def set_metadata(self, key: str, value) -> None:
        raise NotImplementedError


class MemoryCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._metadata: dict[str, object] = {}

    def get(self, credential_id: str) -> str:
        return self._values.get(credential_id, "")

    def set(self, credential_id: str, secret: str) -> None:
        self._values[credential_id] = secret

    def delete(self, credential_id: str) -> None:
        self._values.pop(credential_id, None)

    def get_metadata(self, key: str):
        return copy.deepcopy(self._metadata.get(key))

    def set_metadata(self, key: str, value) -> None:
        self._metadata[key] = copy.deepcopy(value)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_transform(data: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise OSError("Windows DPAPI 仅在 Windows 上可用")
    buffer = ctypes.create_string_buffer(data)
    input_blob = _DataBlob(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    description = "BiliDrop credential" if protect else None
    ok = function(
        ctypes.byref(input_blob),
        description,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class JsonCredentialStore(CredentialStore):
    """Store protected secrets and their program-owned metadata in one JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_credential_store_path()
        self.protected = sys.platform == "win32"

    def get(self, credential_id: str) -> str:
        entry = self._read().get("credentials", {}).get(credential_id)
        if not isinstance(entry, dict):
            return ""
        encoded = str(entry.get("value") or "")
        if not encoded:
            return ""
        raw = base64.b64decode(encoded.encode("ascii"))
        if bool(entry.get("protected")):
            raw = _dpapi_transform(raw, protect=False)
        return raw.decode("utf-8")

    def set(self, credential_id: str, secret: str) -> None:
        if not credential_id.strip():
            raise ValueError("credential_id 不能为空")
        payload = self._read()
        raw = secret.encode("utf-8")
        if self.protected:
            raw = _dpapi_transform(raw, protect=True)
        else:
            LOGGER.warning("当前平台没有 DPAPI，凭据回退为独立本地存储")
        payload.setdefault("credentials", {})[credential_id] = {
            "protected": self.protected,
            "value": base64.b64encode(raw).decode("ascii"),
        }
        self._write(payload)
        if self.get(credential_id) != secret:
            raise OSError("凭据写入校验失败")

    def delete(self, credential_id: str) -> None:
        payload = self._read()
        credentials = payload.setdefault("credentials", {})
        if credential_id in credentials:
            del credentials[credential_id]
            self._write(payload)

    def get_metadata(self, key: str):
        metadata = self._read().get("metadata", {})
        if not isinstance(metadata, dict):
            return None
        return copy.deepcopy(metadata.get(key))

    def set_metadata(self, key: str, value) -> None:
        if not key.strip():
            raise ValueError("metadata key 不能为空")
        payload = self._read()
        metadata = payload.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            payload["metadata"] = metadata
        metadata[key] = copy.deepcopy(value)
        payload["version"] = max(int(payload.get("version") or 1), 2)
        self._write(payload)

    def backup(self, reason: str = "profiles", *, keep: int = 10) -> Path | None:
        """Copy the encrypted store before an account-destructive mutation."""

        if not self.path.exists():
            return None
        # Do not bless malformed data as the only rollback source.
        self._read()
        safe_reason = "".join(
            char for char in reason.lower() if char.isascii() and char.isalnum()
        ) or "profiles"
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        target = backup_dir / (
            f"{self.path.stem}-{timestamp}-{safe_reason}-"
            f"{uuid.uuid4().hex[:6]}{self.path.suffix}"
        )
        shutil.copy2(self.path, target)
        if target.read_bytes() != self.path.read_bytes():
            target.unlink(missing_ok=True)
            raise OSError("账号凭据备份校验失败")
        backups = sorted(
            backup_dir.glob(f"{self.path.stem}-*{self.path.suffix}"),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
            reverse=True,
        )
        for stale in backups[max(1, int(keep)):]:
            stale.unlink(missing_ok=True)
        return target

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 2, "credentials": {}, "metadata": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("凭据存储格式错误")
        return payload

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if sys.platform != "win32":
                os.chmod(self.path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()


def default_credential_store_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "BiliDrop" / "credentials.json"
    return Path.home() / ".config" / "bilidrop" / "credentials.json"
