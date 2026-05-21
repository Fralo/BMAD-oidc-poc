import pytest
from pydantic import ValidationError

from resource_server.core.config import AppSettings


def test_default_settings_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("PROFILE", raising=False)
    settings = AppSettings()
    assert settings.app_name == "resource-server"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.profile == "default"
    assert settings.effective_database_url == "sqlite://"


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_valid_log_levels(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    monkeypatch.setenv("LOG_LEVEL", level)
    settings = AppSettings()
    assert settings.log_level == level


def test_log_level_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = AppSettings()
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INVALID")
    with pytest.raises(ValidationError):
        AppSettings()


def test_root_path_defaults_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOT_PATH", raising=False)
    settings = AppSettings()
    assert settings.root_path == ""


def test_root_path_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_PATH", "/api/v1")
    settings = AppSettings()
    assert settings.root_path == "/api/v1"


def test_effective_database_url_default_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = AppSettings()
    assert settings.effective_database_url == "sqlite://"


def test_effective_database_url_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    settings = AppSettings()
    assert settings.effective_database_url == "sqlite://"


def test_effective_database_url_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "   ")
    settings = AppSettings()
    assert settings.effective_database_url == "sqlite://"


def test_effective_database_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@host:3306/db")
    settings = AppSettings()
    assert settings.effective_database_url == "mysql+pymysql://u:p@host:3306/db"


def test_default_log_mode_is_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_MODE", raising=False)
    settings = AppSettings()
    assert settings.log_mode == "plain"


def test_log_mode_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_MODE", "json")
    settings = AppSettings()
    assert settings.log_mode == "json"


def test_log_mode_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_MODE", "xml")
    with pytest.warns(UserWarning, match="Invalid LOG_MODE"):
        settings = AppSettings()
    assert settings.log_mode == "plain"


def test_entra_auth_requires_external_settings() -> None:
    with pytest.raises(ValidationError, match="AUTH_TYPE=entra requires"):
        AppSettings(auth_type="entra")


def test_entra_auth_accepts_required_settings() -> None:
    settings = AppSettings(
        auth_type="entra",
        auth_external_issuer="https://issuer.example.test",
        auth_external_discovery_uri="https://issuer.example.test/.well-known/openid-configuration",
    )
    assert settings.auth_type == "entra"
    assert settings.auth_external_token_uri == ""
    assert settings.auth_external_client_id == ""
    assert settings.auth_external_client_secret == ""


def test_entra_auth_accepts_m2m_settings() -> None:
    settings = AppSettings(
        auth_type="entra",
        auth_external_issuer="https://issuer.example.test",
        auth_external_discovery_uri="https://issuer.example.test/.well-known/openid-configuration",
        auth_external_token_uri="https://issuer.example.test/oauth2/v2.0/token",
        auth_external_client_id="client-id",
        auth_external_client_secret="client-secret",
    )
    assert settings.auth_external_token_uri != ""
    assert settings.auth_external_client_id == "client-id"
    assert settings.auth_external_client_secret == "client-secret"


def test_cors_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ENABLED", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    settings = AppSettings()
    assert settings.cors_enabled is False
    assert settings.cors_allow_origins_list == []


def test_cors_csv_parsing_trims_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        " http://localhost:3000 , https://app.example.com ,,",
    )
    monkeypatch.setenv("CORS_ALLOW_METHODS", "GET, POST,OPTIONS")
    monkeypatch.setenv("CORS_ALLOW_HEADERS", "Authorization, Content-Type")
    monkeypatch.setenv("CORS_EXPOSE_HEADERS", "X-Request-Id, X-Trace-Id")
    settings = AppSettings()

    assert settings.cors_allow_origins_list == [
        "http://localhost:3000",
        "https://app.example.com",
    ]
    assert settings.cors_allow_methods_list == ["GET", "POST", "OPTIONS"]
    assert settings.cors_allow_headers_list == ["Authorization", "Content-Type"]
    assert settings.cors_expose_headers_list == ["X-Request-Id", "X-Trace-Id"]


def test_cors_wildcard_forbidden_with_credentials() -> None:
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS cannot include"):
        AppSettings(
            cors_allow_origins="*",
            cors_allow_credentials=True,
        )


def test_profile_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROFILE", raising=False)
    settings = AppSettings()
    assert settings.profile == "default"


def test_profile_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILE", "mock")
    settings = AppSettings()
    assert settings.profile == "mock"


def test_profile_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILE", "MOCK")
    settings = AppSettings()
    assert settings.profile == "mock"


def test_profile_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILE", "staging")
    with pytest.raises(ValidationError, match="Invalid profile"):
        AppSettings()


# ---------------------------------------------------------------------------
# Required-fail-fast: OIDC_ISSUER_URL / OIDC_JWKS_URL / OIDC_AUDIENCE
# ---------------------------------------------------------------------------
# Story 3.1 review patch CR1: add the missing fail-fast tests for the
# `_validate_oidc_required_fail_fast` model_validator (spec Dev Notes lines
# 313-315 + "Previous story intelligence" line 394: "Two tests per field
# (missing + whitespace-only)" — required-fail-fast mirrors BFF Story 1.3
# review's decision-needed #3). Closes coverage gap on core/config.py
# lines 133-138 (the raise path).


def test_oidc_issuer_url_required_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_ISSUER_URL", raising=False)
    with pytest.raises(ValidationError, match="OIDC_ISSUER_URL is required"):
        AppSettings()


def test_oidc_issuer_url_required_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER_URL", "   ")
    with pytest.raises(ValidationError, match="OIDC_ISSUER_URL is required"):
        AppSettings()


def test_oidc_audience_required_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    with pytest.raises(ValidationError, match="OIDC_AUDIENCE is required"):
        AppSettings()


def test_oidc_audience_required_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_AUDIENCE", "   ")
    with pytest.raises(ValidationError, match="OIDC_AUDIENCE is required"):
        AppSettings()
