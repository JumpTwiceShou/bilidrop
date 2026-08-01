from bilibili_drops_miner._version import APP_VERSION
from bilibili_drops_miner.gui_parts.update_checker import (
    parse_update_payload,
    should_check_update,
)


def test_application_version_is_v2_1_0() -> None:
    assert APP_VERSION == "v2.1.0"


def test_release_channel_checks_for_updates() -> None:
    assert should_check_update("v2.0.0", "release")
    assert not should_check_update("v2.0.0-dev", "dev")


def test_older_public_release_is_not_reported_as_update() -> None:
    result = parse_update_payload(
        {
            "tag_name": "v1.6.0",
            "html_url": "https://example.invalid/releases/v1.6.0",
        },
        current_version="v2.0.0",
        releases_url="https://example.invalid/releases",
    )

    assert result is None


def test_v2_1_0_does_not_treat_v2_0_1_as_an_update() -> None:
    result = parse_update_payload(
        {
            "tag_name": "v2.0.1",
            "html_url": "https://example.invalid/releases/v2.0.1",
        },
        current_version=APP_VERSION,
        releases_url="https://example.invalid/releases",
    )

    assert result is None


def test_newer_public_release_is_reported() -> None:
    result = parse_update_payload(
        {
            "tag_name": "v2.0.1",
            "html_url": "https://example.invalid/releases/v2.0.1",
        },
        current_version="v2.0.0",
        releases_url="https://example.invalid/releases",
    )

    assert result is not None
    assert result.latest_version == "v2.0.1"


def test_invalid_release_tag_is_ignored() -> None:
    result = parse_update_payload(
        {"tag_name": "latest"},
        current_version="v2.0.0",
        releases_url="https://example.invalid/releases",
    )

    assert result is None
