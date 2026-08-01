import json

import pytest

from bilibili_drops_miner.config import MinerConfig
from bilibili_drops_miner.credential_store import MemoryCredentialStore
from bilibili_drops_miner.gui_parts.config_io import (
    build_config_payload,
    load_config_data,
    load_stored_config_data,
    save_config_data,
    save_stored_config_data,
    values_from_config_data,
)


def _config(**overrides) -> MinerConfig:
    values = {
        "cookie": "secret-cookie",
        "room_ids": [23612045],
        "thread_count": 16,
        "reconnect_delay_seconds": 8,
        "task_ids": ["task-a"],
        "task_query_interval_seconds": 30,
        "notify_urls": ["gotifys://host/secret"],
    }
    values.update(overrides)
    return MinerConfig(**values)


def test_new_settings_payload_excludes_secrets() -> None:
    payload = build_config_payload(
        _config(concurrency_mode="automatic"),
        verbose=False,
        minimize_to_tray=False,
        close_to_tray=True,
        auto_check_updates=False,
        automatic_mining_enabled=True,
        apply_to_all_accounts=True,
    )
    assert "cookie" not in payload
    assert "notify_urls" not in payload
    assert payload["concurrency_mode"] == "automatic"
    assert payload["minimize_to_tray"] is False
    assert payload["close_to_tray"] is True
    assert payload["auto_check_updates"] is False
    assert payload["automatic_mining_enabled"] is True
    assert payload["apply_to_all_accounts"] is True
    assert payload["concurrency_policy_version"] == 2
    assert payload["settings_schema_version"] == 5
    assert "task_ids" not in payload


def test_legacy_config_is_still_readable() -> None:
    values = values_from_config_data(
        {
            "cookie": "legacy-cookie",
            "room_ids": [1, 2],
            "thread_count": 128,
            "notify_urls": ["schan://legacy"],
        }
    )
    assert values.cookie == "legacy-cookie"
    assert values.rooms_text == "1,2"
    assert values.thread_count_text == "128"
    assert values.notify_urls_text == "schan://legacy"


def test_missing_session_count_uses_new_default() -> None:
    values = values_from_config_data({"room_ids": [1]})
    assert values.thread_count_text == "16"
    assert values.concurrency_mode == "automatic"
    assert values.apply_to_all_accounts is False
    assert values.auto_check_updates is True


def test_legacy_implicit_fixed_mode_migrates_to_automatic() -> None:
    values = values_from_config_data(
        {
            "room_ids": [1],
            "concurrency_mode": "fixed",
        }
    )
    assert values.concurrency_mode == "automatic"


def test_new_explicit_fixed_mode_is_preserved() -> None:
    values = values_from_config_data(
        {
            "room_ids": [1],
            "concurrency_mode": "fixed",
            "concurrency_policy_version": 2,
        }
    )
    assert values.concurrency_mode == "fixed"


def test_atomic_config_write_round_trip(tmp_path) -> None:
    target = tmp_path / "config.json"
    save_config_data(target, {"room_ids": [1]})
    assert load_config_data(target) == {"room_ids": [1]}
    assert json.loads(target.read_text(encoding="utf-8"))["room_ids"] == [1]


def test_settings_round_trip_through_combined_credential_store() -> None:
    store = MemoryCredentialStore()
    payload = build_config_payload(_config(), verbose=True)

    save_stored_config_data(store, payload)

    assert load_stored_config_data(store) == payload


def test_combined_settings_reject_duplicate_secrets() -> None:
    with pytest.raises(ValueError, match="不能重复保存"):
        save_stored_config_data(
            MemoryCredentialStore(),
            {"room_ids": [1], "cookie": "must-not-be-duplicated"},
        )


@pytest.mark.parametrize("count", [0, 129])
def test_session_count_is_bounded(count: int) -> None:
    with pytest.raises(ValueError):
        _config(thread_count=count).validate()
