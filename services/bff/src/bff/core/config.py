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

    app_name: str = "bff"
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

    root_path: str = ""
    cors_enabled: bool = False
    cors_allow_origins: str = ""
    cors_allow_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = "Authorization,Content-Type"
    cors_allow_credentials: bool = False
    cors_expose_headers: str = ""

    database_url: str | None = None

    # BMAD_books project env vars (AR29). Pydantic-settings reads these from the
    # repo-root .env file via env_file in SettingsConfigDict; values are required
    # at startup for fail-fast behavior matching the archetype's config policy.
    # Consumers land in later stories: BFF_CLIENT_SECRET (Story 1.5),
    # BFF_BASE_URL (Story 1.5), OIDC_* (Stories 1.5 + health probe here),
    # BFF_*_COOKIE_* (Stories 1.5–1.6), ENABLE_TEST_RESET / TEST_RESET_TOKEN
    # (Story 1.12). BFF_DATABASE_URL is the canonical async SQLAlchemy URL.
    bff_database_url: str = ""
    bff_client_secret: str = ""
    bff_base_url: str = "http://localhost:8000"
    oidc_issuer_url: str = ""
    oidc_jwks_url: str = ""
    oidc_audience: str = ""
    oidc_client_id: str = ""
    # Browser-facing authorize URL — used in the 302 from /auth/login. Differs
    # from `oidc_issuer_url` (the BFF↔IdP back-channel URL) because the browser
    # cannot resolve compose-internal hostnames like `keycloak:8080`. In
    # compose with `KC_HOSTNAME=localhost`, the discovery doc emits
    # `http://localhost:8080/...` and the BFF MUST use that for redirects.
    # (See deferred-work.md#D2 / #D8, closed by Story 1.5.)
    oidc_authorize_url_browser: str = ""
    bff_session_cookie_name: str = "bff_session"
    bff_csrf_cookie_name: str = "csrf_token"
    bff_session_cookie_secure: bool = False
    enable_test_reset: bool = False
    test_reset_token: str = ""

    # OIDC discovery probe timeouts (architecture §C6: BFF→Keycloak 5s/10s, no
    # retries). The discovery fetch uses these.
    oidc_discovery_connect_timeout: float = 5.0
    oidc_discovery_read_timeout: float = 10.0

    @model_validator(mode="after")
    def _validate_cors_requirements(self) -> AppSettings:
        if self.cors_allow_credentials and "*" in self.cors_allow_origins_list:
            msg = (
                "CORS_ALLOW_ORIGINS cannot include '*' when CORS_ALLOW_CREDENTIALS=true"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_oidc_authorize_url_browser(self) -> AppSettings:
        # Story 1.5 closes deferred-work.md#D2 / #D8: a browser-facing authorize
        # URL is required so /auth/login can redirect through a hostname the
        # user's browser actually resolves. Fail-fast at startup so the misconfig
        # surfaces at first boot rather than at first OIDC redirect.
        val = self.oidc_authorize_url_browser.strip()
        if not val:
            msg = (
                "OIDC_AUTHORIZE_URL_BROWSER is required and must be non-empty "
                "(the browser-facing authorize URL — typically "
                "http://localhost:8080/realms/<realm> in compose)"
            )
            raise ValueError(msg)
        if not val.startswith(("http://", "https://")):
            msg = (
                "OIDC_AUTHORIZE_URL_BROWSER must start with 'http://' or 'https://' "
                f"(got: '{val[:40]}...')"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_bff_client_secret(self) -> AppSettings:
        # Story 1.3 Review Findings D3: services/bff/.env.example declares
        # BFF_CLIENT_SECRET as "required-fail-fast even in 1.3" but the field
        # defaulted to "" with no enforcement. Story 1.5's OIDC plugin is the
        # first consumer; failing at the BFF's startup catches misconfig at
        # first deploy rather than at the first OIDC redirect.
        if not self.bff_client_secret.strip():
            msg = (
                "BFF_CLIENT_SECRET is required and must be non-empty "
                "(set it in services/bff/.env or the deployment env)"
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
        1. BFF_DATABASE_URL (AR29 canonical name) if set.
        2. DATABASE_URL (archetype default) if set.
        3. In-memory SQLite (sqlite://) for tests / unset deployments.
        """
        for raw in (self.bff_database_url, self.database_url):
            if raw is not None and isinstance(raw, str) and raw.strip():
                return raw.strip()
        return "sqlite://"


settings = AppSettings()
