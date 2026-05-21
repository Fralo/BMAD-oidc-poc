"""Tests for `resource_server.auth.oidc_discovery` — Story 7.2 AC5 matrix.

Covers: happy path, transport error, non-2xx, non-JSON body, missing
required field, and extra-unknown-fields tolerance.

Uses `httpx.MockTransport` injected via `client_factory`. The RS test
suite does not have `respx`; stdlib-friendly `MockTransport` keeps the
dependency surface narrow (per resource-server PROJECT_CONTEXT.md: no new
libraries without human approval).
"""

from collections.abc import Callable

import httpx
import pytest

from resource_server.auth.oidc_discovery import (
    DiscoveryFetchError,
    OidcDiscovery,
    fetch_discovery,
)

_ISSUER = "http://kc/realms/x"
_WELL_KNOWN = f"{_ISSUER}/.well-known/openid-configuration"


def _good_payload() -> dict[str, str]:
    return {
        "issuer": "http://kc/realms/x",
        "authorization_endpoint": "http://kc/realms/x/protocol/openid-connect/auth",
        "token_endpoint": "http://kc/realms/x/protocol/openid-connect/token",
        "jwks_uri": "http://kc/realms/x/protocol/openid-connect/certs",
        "end_session_endpoint": "http://kc/realms/x/protocol/openid-connect/logout",
        "revocation_endpoint": "http://kc/realms/x/protocol/openid-connect/revoke",
    }


def _factory_for(transport: httpx.MockTransport) -> Callable[..., httpx.AsyncClient]:
    def _build(**kw: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, **kw)

    return _build


async def test_fetch_discovery_happy_path() -> None:
    payload = _good_payload()

    def _handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _WELL_KNOWN
        return httpx.Response(200, json=payload)

    discovery = await fetch_discovery(
        _ISSUER,
        connect_timeout=5.0,
        read_timeout=10.0,
        client_factory=_factory_for(httpx.MockTransport(_handler)),
    )

    assert isinstance(discovery, OidcDiscovery)
    assert discovery.issuer == payload["issuer"]
    assert discovery.jwks_uri == payload["jwks_uri"]


async def test_fetch_discovery_strips_trailing_slash_on_issuer() -> None:
    payload = _good_payload()

    def _handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _WELL_KNOWN
        return httpx.Response(200, json=payload)

    await fetch_discovery(
        _ISSUER + "/",
        connect_timeout=5.0,
        read_timeout=10.0,
        client_factory=_factory_for(httpx.MockTransport(_handler)),
    )


async def test_fetch_discovery_raises_on_transport_error() -> None:
    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(DiscoveryFetchError) as excinfo:
        await fetch_discovery(
            _ISSUER,
            connect_timeout=5.0,
            read_timeout=10.0,
            client_factory=_factory_for(httpx.MockTransport(_handler)),
        )
    assert excinfo.value.classifier == "transport_error:ConnectError"


async def test_fetch_discovery_raises_on_404() -> None:
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(DiscoveryFetchError) as excinfo:
        await fetch_discovery(
            _ISSUER,
            connect_timeout=5.0,
            read_timeout=10.0,
            client_factory=_factory_for(httpx.MockTransport(_handler)),
        )
    assert excinfo.value.classifier == "http_404"


async def test_fetch_discovery_raises_on_non_json_body() -> None:
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>generic landing</html>")

    with pytest.raises(DiscoveryFetchError) as excinfo:
        await fetch_discovery(
            _ISSUER,
            connect_timeout=5.0,
            read_timeout=10.0,
            client_factory=_factory_for(httpx.MockTransport(_handler)),
        )
    assert excinfo.value.classifier == "non_json_body"


async def test_fetch_discovery_raises_on_non_object_body() -> None:
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["array", "not", "object"])

    with pytest.raises(DiscoveryFetchError) as excinfo:
        await fetch_discovery(
            _ISSUER,
            connect_timeout=5.0,
            read_timeout=10.0,
            client_factory=_factory_for(httpx.MockTransport(_handler)),
        )
    assert excinfo.value.classifier == "non_object_body"


@pytest.mark.parametrize(
    "missing_field",
    [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "end_session_endpoint",
        "revocation_endpoint",
    ],
)
async def test_fetch_discovery_raises_on_missing_required_field(
    missing_field: str,
) -> None:
    payload = _good_payload()
    del payload[missing_field]

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(DiscoveryFetchError) as excinfo:
        await fetch_discovery(
            _ISSUER,
            connect_timeout=5.0,
            read_timeout=10.0,
            client_factory=_factory_for(httpx.MockTransport(_handler)),
        )
    assert excinfo.value.classifier == f"missing_field:{missing_field}"


async def test_fetch_discovery_accepts_extra_unknown_fields() -> None:
    payload = {
        **_good_payload(),
        "scopes_supported": ["openid", "reading-speed:read"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
    }

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    discovery = await fetch_discovery(
        _ISSUER,
        connect_timeout=5.0,
        read_timeout=10.0,
        client_factory=_factory_for(httpx.MockTransport(_handler)),
    )

    assert isinstance(discovery, OidcDiscovery)
    assert not hasattr(discovery, "scopes_supported")


async def test_oidc_discovery_is_frozen() -> None:
    discovery = OidcDiscovery(
        issuer="i",
        authorization_endpoint="a",
        token_endpoint="t",
        jwks_uri="j",
        end_session_endpoint="e",
        revocation_endpoint="r",
    )
    with pytest.raises(AttributeError):
        discovery.issuer = "tampered"  # type: ignore[misc]


def test_discovery_fetch_error_exposes_classifier() -> None:
    exc = DiscoveryFetchError("http_503")
    assert exc.classifier == "http_503"
    assert str(exc) == "http_503"
