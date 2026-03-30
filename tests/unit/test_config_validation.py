from app.config.settings import RunMode, Settings


def test_config_defaults_safe_mode() -> None:
    settings = Settings()
    assert settings.mode == RunMode.PAPER
    assert settings.live_enable_flag is False
    assert settings.live_execution_enabled is False


def test_allowlist_parsing() -> None:
    settings = Settings(allowlisted_tokens="0x1, 0x2")
    assert settings.allowlisted_tokens_set == {"0x1", "0x2"}