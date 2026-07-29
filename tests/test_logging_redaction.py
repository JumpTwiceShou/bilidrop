from bilibili_drops_miner.logging_utils import redact_sensitive_text


def test_sensitive_values_are_redacted() -> None:
    output = redact_sensitive_text(
        "SESSDATA=abc; bili_jct=csrf-value access_token: token-value"
    )
    assert "abc" not in output
    assert "csrf-value" not in output
    assert "token-value" not in output
    assert output.count("<redacted>") == 3
