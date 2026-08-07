from app.config import Settings


def test_playwright_headless_env_var_converts_false_string_to_bool(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "false")
    settings = Settings(_env_file=None)
    assert settings.playwright_headless is False


def test_playwright_headless_env_var_converts_true_string_to_bool(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "true")
    settings = Settings(_env_file=None)
    assert settings.playwright_headless is True


def test_playwright_headless_defaults_to_false_without_env_var(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PLAYWRIGHT_HEADLESS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.playwright_headless is False
