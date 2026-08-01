import json
import sys

import pytest

from bilibili_drops_miner.credential_store import (
    JsonCredentialStore,
    MemoryCredentialStore,
)
from bilibili_drops_miner.gui_parts.cookie_profiles import (
    COOKIE_PROFILE_METADATA_KEY,
    CookieProfile,
    cookie_store_path,
    legacy_cookie_store_path,
    load_cookie_profile_state,
    load_cookie_profiles,
    save_cookie_profiles,
)
from bilibili_drops_miner.gui_parts.config_io import save_stored_config_data


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-specific")
def test_windows_combined_store_keeps_metadata_but_not_plaintext_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "credentials.json"
    store = JsonCredentialStore(target)
    profiles = [CookieProfile("主号备注", "test-secret-value", "now")]

    save_cookie_profiles(
        profiles,
        credential_store=store,
        last_selected_credential_id="",
    )

    content = target.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert "主号备注" in content
    assert "test-secret-value" not in content
    assert payload["metadata"][COOKIE_PROFILE_METADATA_KEY]["accounts"][0][
        "remark"
    ] == "主号备注"
    assert store.get(profiles[0].credential_id) == "test-secret-value"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-specific")
def test_saved_settings_body_is_dpapi_protected_in_same_file(tmp_path) -> None:
    target = tmp_path / "credentials.json"
    store = JsonCredentialStore(target)

    save_stored_config_data(store, {"room_ids": [987654321], "thread_count": 32})

    content = target.read_text(encoding="utf-8")
    assert "application-settings" in content
    assert "987654321" not in content


def test_cookie_profile_and_secret_share_one_store() -> None:
    store = MemoryCredentialStore()
    profiles = [
        CookieProfile(
            "主号",
            "fake-cookie-secret",
            "now",
            settings={
                "rooms_text": "23612045",
                "thread_count": 32,
                "concurrency_mode": "fixed",
            },
        )
    ]

    save_cookie_profiles(profiles, credential_store=store)
    state = load_cookie_profile_state(credential_store=store)

    metadata = store.get_metadata(COOKIE_PROFILE_METADATA_KEY)
    assert metadata["accounts"][0]["remark"] == "主号"
    assert "cookie" not in metadata["accounts"][0]
    assert state.profiles[0].cookie == "fake-cookie-secret"
    assert metadata["version"] == 5
    assert state.profiles[0].settings["thread_count"] == 32
    assert state.profiles[0].settings["rooms_text"] == "23612045"


def test_cookie_profile_state_remembers_only_a_saved_profile() -> None:
    store = MemoryCredentialStore()
    profiles = [
        CookieProfile("主号", "cookie-one", credential_id="account-one"),
        CookieProfile("小号", "cookie-two", credential_id="account-two"),
    ]
    save_cookie_profiles(
        profiles,
        credential_store=store,
        last_selected_credential_id="account-two",
    )

    state = load_cookie_profile_state(credential_store=store)

    assert state.last_selected_credential_id == "account-two"


def test_legacy_profile_without_account_settings_remains_compatible() -> None:
    store = MemoryCredentialStore()
    profile = CookieProfile(
        "旧版账号",
        "cookie-one",
        credential_id="account-one",
    )

    save_cookie_profiles([profile], credential_store=store)
    state = load_cookie_profile_state(credential_store=store)

    assert state.profiles[0].settings == {}


def test_cookie_profile_state_ignores_unknown_last_selected_id() -> None:
    store = MemoryCredentialStore()
    profiles = [CookieProfile("主号", "cookie-one", credential_id="account-one")]
    save_cookie_profiles(
        profiles,
        credential_store=store,
        last_selected_credential_id="temporary-session",
    )

    state = load_cookie_profile_state(credential_store=store)

    assert state.last_selected_credential_id == ""


def test_encrypted_store_backup_is_verified_and_rotated(tmp_path) -> None:
    target = tmp_path / "credentials.json"
    store = JsonCredentialStore(target)
    store.set_metadata("fixture", {"value": 1})
    original = target.read_bytes()

    first = store.backup("save", keep=2)
    assert first is not None
    assert first.read_bytes() == original
    store.set_metadata("fixture", {"value": 2})
    second = store.backup("overwrite", keep=2)
    store.set_metadata("fixture", {"value": 3})
    third = store.backup("delete", keep=2)

    assert second is not None
    assert third is not None
    backups = list((tmp_path / "backups").glob("credentials-*.json"))
    assert len(backups) == 2


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-specific")
def test_packaged_app_migrates_legacy_file_out_of_executable_directory(
    tmp_path,
    monkeypatch,
) -> None:
    program_dir = tmp_path / "program"
    local_app_data = tmp_path / "local-app-data"
    program_dir.mkdir()
    executable = program_dir / "bilibili-drops-miner-gui.exe"
    legacy_path = program_dir / "cookies.json"
    legacy_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "remark": "旧版主号",
                        "cookie": "DedeUserID=10001; SESSDATA=legacy-fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    profiles = load_cookie_profiles()

    combined_path = local_app_data / "BiliDrop" / "credentials.json"
    assert cookie_store_path() == combined_path
    assert legacy_cookie_store_path() == legacy_path
    assert len(profiles) == 1
    assert profiles[0].remark == "旧版主号"
    assert profiles[0].cookie.endswith("SESSDATA=legacy-fixture")
    assert combined_path.exists()
    assert "legacy-fixture" not in combined_path.read_text(encoding="utf-8")
    assert not legacy_path.exists()
    assert list((local_app_data / "BiliDrop" / "legacy").glob("cookies.json*"))


def test_failed_legacy_migration_preserves_original_file(
    tmp_path,
    monkeypatch,
) -> None:
    class FailingMetadataStore(MemoryCredentialStore):
        def set_metadata(self, key: str, value) -> None:
            raise OSError("synthetic metadata failure")

    executable = tmp_path / "bilibili-drops-miner-gui.exe"
    legacy_path = tmp_path / "cookies.json"
    legacy_path.write_text(
        json.dumps({"cookies": [{"remark": "旧账号", "cookie": "legacy-secret"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    with pytest.raises(OSError, match="synthetic metadata failure"):
        load_cookie_profiles(credential_store=FailingMetadataStore())

    assert legacy_path.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-specific")
def test_source_mode_migrates_cwd_legacy_file_to_appdata(
    tmp_path,
    monkeypatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    legacy_path = tmp_path / "cookies.json"
    legacy_path.write_text(
        json.dumps([{"remark": "源码旧账号", "cookie": "source-legacy-secret"}]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delattr(sys, "frozen", raising=False)

    state = load_cookie_profile_state()

    assert state.profiles[0].remark == "源码旧账号"
    assert not legacy_path.exists()
    assert cookie_store_path().exists()
    assert "source-legacy-secret" not in cookie_store_path().read_text(
        encoding="utf-8"
    )
