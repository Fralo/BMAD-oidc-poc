"""OIDC discovery document loader (Story 7.2).

Fetches `${ISSUER}/.well-known/openid-configuration` once at process startup
and caches the parsed URLs into a frozen `OidcDiscovery` dataclass. The
lifespan hook in `resource_server.main` calls `fetch_discovery(...)` and
stashes the result on `app.state.oidc_discovery`; the JWT-validation surface
in `auth/oidc_bearer.py` reads `discovery.issuer` + `discovery.jwks_uri`
from there.

Failures (transport, non-2xx, malformed JSON, missing/empty required field)
raise `DiscoveryFetchError(classifier)` — the classifier is a single token
safe for ERROR logging (no URLs, no response bodies). Honors architecture
§C6 budget (5s connect / 10s read; zero retries — operator restarts the
process if Keycloak is flaky at startup).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

_REQUIRED_FIELDS: tuple[str, ...] = (
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "jwks_uri",
    "end_session_endpoint",
    "revocation_endpoint",
)


@dataclass(frozen=True, kw_only=True, slots=True)
class OidcDiscovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str
    revocation_endpoint: str


class DiscoveryFetchError(Exception):
    """Raised when the startup discovery fetch fails.

    The single positional argument is a one-token classifier
    (e.g. `transport_error:ConnectError`, `http_404`, `non_json_body`,
    `missing_field:jwks_uri`). Logged at ERROR by the lifespan hook;
    never echoed to an authenticated caller.
    """

    def __init__(self, classifier: str) -> None:
        super().__init__(classifier)
        self.classifier = classifier


async def fetch_discovery(
    issuer_url: str,
    *,
    connect_timeout: float,
    read_timeout: float,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> OidcDiscovery:
    """GET `${issuer_url}/.well-known/openid-configuration` and parse it.

    Architecture §C6 timeouts; `follow_redirects=True` so a Keycloak ingress
    with trailing-slash normalization (302 on the well-known path) works.
    """
    canonical_issuer = issuer_url.rstrip("/")
    url = canonical_issuer + "/.well-known/openid-configuration"
    timeout = httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=read_timeout,
        pool=read_timeout,
    )
    factory = client_factory or httpx.AsyncClient
    try:
        async with factory(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise DiscoveryFetchError(f"transport_error:{type(exc).__name__}") from exc
    if not (200 <= response.status_code < 300):
        raise DiscoveryFetchError(f"http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise DiscoveryFetchError("non_json_body") from exc
    if not isinstance(payload, dict):
        raise DiscoveryFetchError("non_object_body")
    return _validated(payload)


def _validated(payload: dict[str, Any]) -> OidcDiscovery:
    resolved: dict[str, str] = {}
    for field_name in _REQUIRED_FIELDS:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value:
            raise DiscoveryFetchError(f"missing_field:{field_name}")
        resolved[field_name] = value
    return OidcDiscovery(**resolved)
