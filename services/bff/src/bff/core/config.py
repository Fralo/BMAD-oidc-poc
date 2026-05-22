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
    oidc_audience: str = ""
    oidc_client_id: str = ""
    # Browser-facing OIDC base URL — used to derive the `/auth/login` 302
    # target by combining this scheme+authority with the *path* from
    # `discovery.authorization_endpoint`. Defaults to `${OIDC_ISSUER_URL}`
    # (the production case where front-channel = back-channel). Override in
    # compose dev where the BFF must redirect the browser through a host
    # the browser can resolve (e.g. `http://localhost:8080/realms/...`)
    # while back-channel calls go to `http://keycloak:8080/realms/...`.
    # Story 7.2 replaces the prior `OIDC_AUTHORIZE_URL_BROWSER` env var.
    oidc_public_base_url: str = ""
    bff_session_cookie_name: str = "bff_session"
    bff_csrf_cookie_name: str = "csrf_token"
    bff_session_cookie_secure: bool = False
    enable_test_reset: bool = False
    test_reset_token: str = ""

    # BFF → Resource Server base URL (Story 3.5). Compose-internal default
    # matches the `resource-server` service name in `compose/app.yml`; in dev
    # (host runs), override to the local RS port. Required-fail-fast validation
    # at startup (`_validate_rs_base_url`) closes the misconfig hole where a
    # silent default could direct traffic at `localhost` or an attacker-controlled
    # URL.
    rs_base_url: str = "http://resource-server:8000"

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
    def _validate_oidc_issuer_url(self) -> AppSettings:
        # CR9 (Story 3.5 review): the BFF→Keycloak refresh-token call in
        # ``ResourceServerClient._refresh_access_token`` constructs the token
        # endpoint as ``oidc_issuer_url.rstrip("/") +
        # "/protocol/openid-connect/token"``. If the env var is missing, the
        # resulting URL is the relative path ``/protocol/...`` and httpx
        # raises ``UnsupportedProtocol`` on every refresh attempt → every
        # BFF→RS 401 cycle classifies as ``transport_error`` → cookie-
        # clearing 401 → silent logout loop. Fail-fast at startup.
        val = self.oidc_issuer_url.strip()
        if not val:
            msg = (
                "OIDC_ISSUER_URL is required and must be non-empty "
                "(the BFF↔IdP back-channel issuer URL — typically "
                "http://keycloak:8080/realms/<realm> in compose)"
            )
            raise ValueError(msg)
        if not val.startswith(("http://", "https://")):
            msg = (
                "OIDC_ISSUER_URL must start with 'http://' or 'https://' "
                f"(got: '{val[:40]}...')"
            )
            raise ValueError(msg)
        # Mirror `_validate_rs_base_url`: reject path-only URLs like
        # `http://` or `http:///foo` where urlparse yields an empty netloc.
        # Without this guard, `fetch_discovery` issues a GET against
        # `/.well-known/openid-configuration` (a relative path) and httpx
        # raises an opaque `UnsupportedProtocol` at startup.
        from urllib.parse import urlparse

        if not urlparse(val).netloc:
            msg = (
                "OIDC_ISSUER_URL must include a host "
                f"(got: '{val[:40]}'; expected e.g. http://keycloak:8080/realms/<realm>)"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_oidc_public_base_url(self) -> AppSettings:
        # Story 7.2: OIDC_PUBLIC_BASE_URL contributes only its scheme+authority
        # to the `/auth/login` 302 target. The path component is intentionally
        # discarded — the authorize URL path is always taken from
        # `discovery.authorization_endpoint`. When unset,
        # `effective_oidc_public_base_url` falls back to OIDC_ISSUER_URL
        # (the production case where front-channel = back-channel). In compose
        # dev it MUST be overridden to a browser-resolvable host. Fail-fast on
        # http(s) prefix + non-empty netloc when a value is supplied.
        val = self.oidc_public_base_url.strip()
        if val and not val.startswith(("http://", "https://")):
            msg = (
                "OIDC_PUBLIC_BASE_URL must start with 'http://' or 'https://' "
                f"(got: '{val[:40]}...')"
            )
            raise ValueError(msg)
        if val:
            from urllib.parse import urlparse

            if not urlparse(val).netloc:
                msg = (
                    "OIDC_PUBLIC_BASE_URL must include a host "
                    f"(got: '{val[:40]}'; expected e.g. http://localhost:8080)"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_rs_base_url(self) -> AppSettings:
        # Story 3.5: BFF→RS base URL is required-fail-fast. Mirrors the
        # `_validate_oidc_issuer_url` pattern. A silent default could direct
        # production traffic at `localhost` (which would not resolve to the
        # RS in compose) or, worse, an attacker-controlled URL if a typo'd
        # env var lands in the deployment config.
        #
        # CR5: also reject values that are well-formed strings but produce
        # a URL with no netloc (e.g., ``http://`` alone, ``http:///foo``) —
        # the original check accepted these and the BFF would only fail at
        # first request with a confusing transport-level error.
        val = self.rs_base_url.strip()
        if not val:
            msg = (
                "RS_BASE_URL is required and must be non-empty "
                "(the BFF→Resource Server base URL — typically "
                "http://resource-server:8000 in compose, "
                "http://localhost:8001 in dev)"
            )
            raise ValueError(msg)
        if not val.startswith(("http://", "https://")):
            msg = (
                "RS_BASE_URL must start with 'http://' or 'https://' "
                f"(got: '{val[:40]}...')"
            )
            raise ValueError(msg)
        # urlparse picks up only the host the URL claims; require it
        # non-empty so the BFF can never silently target a path-only URL.
        from urllib.parse import urlparse

        parsed = urlparse(val)
        if not parsed.netloc:
            msg = (
                "RS_BASE_URL must include a host "
                f"(got: '{val[:40]}'; expected e.g. http://resource-server:8000)"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_bff_client_secret(self) -> AppSettings:
        # Story 1.3 Review Findings D3: BFF_CLIENT_SECRET is declared
        # required-fail-fast but the field defaulted to "" with no
        # enforcement. Story 1.5's OIDC plugin is the first consumer; failing
        # at the BFF's startup catches misconfig at first deploy rather than
        # at the first OIDC redirect. D141 follow-up: the secret now lives in
        # the repo-root `.env` (single canonical entry point).
        if not self.bff_client_secret.strip():
            msg = (
                "BFF_CLIENT_SECRET is required and must be non-empty "
                "(set it in the repo-root .env or the deployment env)"
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
    def effective_oidc_public_base_url(self) -> str:
        """Browser-facing OIDC base. Falls back to OIDC_ISSUER_URL when unset.

        Story 7.2: `/auth/login`'s 302 redirect target is built by replacing
        the scheme+authority of `discovery.authorization_endpoint` with this
        value (keeping the path). Production deployments leave it unset
        (defaults to the issuer); compose dev sets it to the host-facing
        URL the browser can resolve.
        """
        val = self.oidc_public_base_url.strip()
        return val if val else self.oidc_issuer_url

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
