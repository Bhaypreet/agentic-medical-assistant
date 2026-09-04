import pytest

from app.config import Settings


def _settings(**overrides):
    base = {
        "groq_api_key": "test-key",
        "environment": "development",
        "api_keys": "",
        "secret_key": "",
    }
    return Settings(**{**base, **overrides})


def test_development_runs_without_api_keys():
    assert _settings().allowed_api_keys == set()


def test_production_refuses_to_start_without_a_secret_key():
    # SECRET_KEY is the pepper for every stored password hash, so a
    # production deployment without one is not safe to run.
    with pytest.raises(ValueError, match="SECRET_KEY must be set"):
        _settings(environment="production")


def test_production_refuses_a_short_secret_key():
    with pytest.raises(ValueError, match="SECRET_KEY must be set"):
        _settings(environment="production", secret_key="too-short")


def test_production_refuses_report_content_logging():
    # This flag writes OCR text and parsed lab values to stdout.
    with pytest.raises(ValueError, match="cannot be enabled in production"):
        _settings(
            environment="production",
            secret_key="k" * 32,
            debug_log_report_content=True,
        )


def test_production_starts_with_a_secret_key():
    settings = _settings(environment="production", secret_key="k" * 32, api_keys="one, two ,three")

    assert settings.is_production
    assert settings.allowed_api_keys == {"one", "two", "three"}


def test_api_keys_are_optional_now_that_users_sign_in():
    # Machine keys are for service callers; people use accounts. A
    # production deployment with no machine keys is perfectly valid.
    settings = _settings(environment="production", secret_key="k" * 32)

    assert settings.allowed_api_keys == set()


def test_cors_origins_are_split_and_trimmed():
    settings = _settings(allowed_origins="https://a.example , https://b.example")

    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_a_missing_api_key_is_fatal():
    with pytest.raises(ValueError):
        Settings(_env_file=None, groq_api_key=None)
