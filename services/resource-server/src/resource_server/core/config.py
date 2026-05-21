import os
import warnings
from enum import StrEnum
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_LOG_MODES = frozenset({"plain", "json"})
VALID_PROFILES = frozenset({"default", "mock"})


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env") or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "resource-server"
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO
    log_mode: str = "plain"
    profile: Literal["default", "mock"] = "default"

    @field_validator("profile", mode="before")
    @classmethod
    def _normalize_profile(cls, value: object) -> str:
        s = str(value).lower() if value is not None else "default"
        if s not in VALID_PROFILES:
            allowed = ", ".join(sorted(VALID_PROFILES))
            msg = f"Invalid profile '{value}'. Must be one of: {allowed}"
            raise ValueError(msg)
        return s

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> str:
        return str(value).upper()

    @field_validator("log_mode")
    @classmethod
    def _normalize_log_mode(cls, value: str) -> str:
        lower = value.lower()
        if lower not in VALID_LOG_MODES:
            warnings.warn(
                f"Invalid LOG_MODE '{value}', falling back to 'plain'",
                stacklevel=2,
            )
            return "plain"
        return lower

    otel_export_enabled: bool = False
    otel_exporter_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "resource-server"

    root_path: str = ""
    cors_enabled: bool = False
    cors_allow_origins: str = ""
    cors_allow_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = "Authorization,Content-Type"
    cors_allow_credentials: bool = False
    cors_expose_headers: str = ""

    database_url: str | None = None

    # BMAD_books AR29 env vars (RS subset). Story 7.2 dropped OIDC_JWKS_URL —
    # the RS now reads `jwks_uri` from the cached OIDC discovery doc.
    #   - RS_DATABASE_URL is the canonical async SQLAlchemy URL for the
    #     Resource Server's SQLite file.
    #   - OIDC_ISSUER_URL + OIDC_AUDIENCE remain. ISSUER_URL is the discovery
    #     fetch target; AUDIENCE is the JWT `aud` claim the RS enforces.
    #   - ENABLE_TEST_RESET / TEST_RESET_TOKEN gate the test-reset endpoint.
    rs_database_url: str = ""
    oidc_issuer_url: str = ""
    oidc_audience: str = ""
    enable_test_reset: bool = False
    test_reset_token: str = "change-me"

    # OIDC discovery fetch timeouts (architecture §C6 / AR19: RS→Keycloak
    # 5s connect / 10s read, zero retries). Story 7.2 renamed from
    # `oidc_jwks_*` (the previous /health JWKS probe) to mirror the BFF.
    oidc_discovery_connect_timeout: float = 5.0
    oidc_discovery_read_timeout: float = 10.0

    auth_type: Literal["none", "entra", "oidc_bearer"] = "none"
    auth_external_issuer: str = ""
    auth_external_audience: str = ""
    auth_external_discovery_uri: str = ""
    auth_external_jwks_uri: str = ""
    auth_external_token_uri: str = ""
    auth_external_client_id: str = ""
    auth_external_client_secret: str = ""

    auth_http_timeout_seconds: float = 10.0
    auth_http_retry_attempts: int = 1

    @model_validator(mode="after")
    def _validate_oidc_required_fail_fast(self) -> AppSettings:
        """Reject empty / whitespace-only OIDC config at AppSettings build.

        Mirrors the BFF's BFF_CLIENT_SECRET fail-fast (Story 1.3 review's
        decision-needed #3): the JWT validation surface that Story 3.2 lands
        is unusable without these values, so failing at first boot — rather
        than at first request — surfaces misconfiguration to operators with
        a precise error message. The values themselves are not pattern-
        validated here (URL well-formedness is the consumer's responsibility);
        only non-empty-after-strip is enforced.
        """
        for field_name, env_name in (
            ("oidc_issuer_url", "OIDC_ISSUER_URL"),
            ("oidc_audience", "OIDC_AUDIENCE"),
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                msg = (
                    f"{env_name} is required and must be non-empty "
                    "(set it in compose/app.yml's resource-server "
                    "`environment:` block or the deployment env)"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_external_auth_requirements(self) -> AppSettings:
        if self.auth_type != "entra":
            pass
        else:
            missing_fields: list[str] = []
            if not self.auth_external_issuer.strip():
                missing_fields.append("AUTH_EXTERNAL_ISSUER")
            if (
                not self.auth_external_discovery_uri.strip()
                and not self.auth_external_jwks_uri.strip()
            ):
                missing_fields.append(
                    "AUTH_EXTERNAL_DISCOVERY_URI or AUTH_EXTERNAL_JWKS_URI"
                )
            if missing_fields:
                missing = ", ".join(missing_fields)
                msg = f"AUTH_TYPE=entra requires the following settings: {missing}"
                raise ValueError(msg)

        if self.cors_allow_credentials and "*" in self.cors_allow_origins_list:
            msg = (
                "CORS_ALLOW_ORIGINS cannot include '*' when CORS_ALLOW_CREDENTIALS=true"
            )
            raise ValueError(msg)
        return self

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return self._parse_csv(self.cors_allow_origins)

    @property
    def cors_allow_methods_list(self) -> list[str]:
        return self._parse_csv(self.cors_allow_methods)

    @property
    def cors_allow_headers_list(self) -> list[str]:
        return self._parse_csv(self.cors_allow_headers)

    @property
    def cors_expose_headers_list(self) -> list[str]:
        return self._parse_csv(self.cors_expose_headers)

    @property
    def effective_database_url(self) -> str:
        """URL used for engine creation. Resolution order:
        1. RS_DATABASE_URL (AR29 canonical name) if set.
        2. DATABASE_URL (archetype default) if set.
        3. In-memory SQLite (sqlite://) for tests / unset deployments.
        """
        for raw in (self.rs_database_url, self.database_url):
            if raw is not None and isinstance(raw, str) and raw.strip():
                return raw.strip()
        return "sqlite://"


settings = AppSettings()
