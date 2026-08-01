from bilibili_drops_miner.account_settings import AccountSettings


def test_empty_legacy_profile_inherits_global_defaults() -> None:
    assert AccountSettings.from_mapping({}) is None


def test_account_settings_are_normalized_and_round_trip() -> None:
    settings = AccountSettings.from_mapping(
        {
            "rooms_text": "23612045",
            "thread_count": 100,
            "reconnect_delay_seconds": 8,
            "task_query_interval_seconds": 30,
            "notify_on_task_complete": False,
            "concurrency_mode": "fixed",
        }
    )

    assert settings is not None
    assert settings.thread_count == 100
    assert settings.concurrency_mode == "fixed"
    assert AccountSettings.from_mapping(settings.to_mapping()) == settings
