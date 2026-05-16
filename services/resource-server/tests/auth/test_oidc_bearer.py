"""Tests for `resource_server.auth.oidc_bearer` — JWT validation + scope enforcement.

Mounts a small test endpoint guarded by `require_scope("reading-speed:read")`
on the production FastAPI app for the duration of this module's tests (added
in a module-scoped autouse fixture, removed in teardown so other test files
don't see the route).

All tests use the `synthetic_rs_idp` fixture which patches
`jwt.PyJWKClient.fetch_data` and `settings.oidc_*` so signature verification
resolves entirely in-process (no real Keycloak / no real HTTP).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from resource_server.auth import oidc_bearer
from resource_server.auth.models import Principal
from resource_server.auth.oidc_bearer import require_scope
from resource_server.main import app

from .synthetic_idp import (
    DEFAULT_ROTATED_KID,
    SyntheticRsIdp,
    build_synthetic_rs_idp,
    random_subject,
)

_TEST_ROUTE_READ = "/_test/oidc/scoped-read"
_TEST_ROUTE_WRITE = "/_test/oidc/scoped-write"


async def _handler_read(
    principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
) -> dict[str, Any]:
    return {
        "sub": principal.subject,
        "scopes": sorted(principal.scopes),
        "name": principal.name,
    }


async def _handler_write(
    principal: Annotated[Principal, Depends(require_scope("reading-speed:write"))],
) -> dict[str, Any]:
    return {"sub": principal.subject}


@pytest.fixture(scope="module", autouse=True)
def _mount_test_routes() -> Any:
    """Mount /_test/oidc/* endpoints on the prod app for this module only.

    Removes them in teardown so other test modules don't see them. The routes
    must NOT be exposed in production — they exist solely to exercise
    `require_scope` from the request layer.
    """
    app.add_api_route(_TEST_ROUTE_READ, _handler_read, methods=["GET"])
    app.add_api_route(_TEST_ROUTE_WRITE, _handler_write, methods=["GET"])
    yield
    app.router.routes = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) not in (_TEST_ROUTE_READ, _TEST_ROUTE_WRITE)
    ]


@pytest.fixture(name="synthetic_rs_idp")
def synthetic_rs_idp_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticRsIdp:
    return build_synthetic_rs_idp(monkeypatch)


@pytest.fixture(name="oidc_client")
async def oidc_client_fixture():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Happy path + scope enforcement
# ---------------------------------------------------------------------------


async def test_happy_path_required_scope_present_returns_200(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    sub = random_subject()
    token = synthetic_rs_idp.make_access_token(
        sub=sub, scope="openid reading-speed:read"
    )
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == sub
    assert "reading-speed:read" in body["scopes"]


async def test_wrong_scope_returns_403_forbidden_scope(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(scope="openid")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 403
    assert response.json() == {
        "errorCode": "forbidden_scope",
        "message": "Required scope is missing",
        "detail": None,
    }


async def test_scoped_write_endpoint_rejects_read_only_scope(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(scope="openid reading-speed:read")
    response = await oidc_client.get(_TEST_ROUTE_WRITE, headers=_auth_header(token))
    assert response.status_code == 403
    assert response.json()["errorCode"] == "forbidden_scope"


# ---------------------------------------------------------------------------
# JWT validation failure modes — every path maps to 401 session_expired
# ---------------------------------------------------------------------------


async def test_expired_token_returns_401_session_expired(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(exp_offset_seconds=-10)
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "session_expired",
        "message": "Authentication required",
        "detail": None,
    }


async def test_wrong_audience_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(aud="some-other-audience")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_wrong_issuer_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(iss="https://attacker.test/")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_malformed_jwt_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    response = await oidc_client.get(
        _TEST_ROUTE_READ, headers=_auth_header("not.a.valid.jwt")
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_token_signed_with_unknown_key_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa

    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = synthetic_rs_idp.make_access_token(signing_key=rogue_key)
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_token_with_alg_none_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    # Manually construct an alg=none token (PyJWT rejects unsigned encoding by
    # default, so build the wire form by hand).
    header = {"alg": "none", "typ": "JWT", "kid": synthetic_rs_idp.kid}
    claims = {
        "iss": synthetic_rs_idp.issuer,
        "aud": synthetic_rs_idp.audience,
        "sub": "test-sub",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "scope": "openid reading-speed:read",
    }

    def _b64(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    token = f"{_b64(header)}.{_b64(claims)}."
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_token_with_alg_hs256_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    claims = {
        "iss": synthetic_rs_idp.issuer,
        "aud": synthetic_rs_idp.audience,
        "sub": "test-sub",
        "exp": int(time.time()) + 300,
        "scope": "openid reading-speed:read",
    }
    # Sign with HMAC using a known secret; decode pins algorithms=["RS256"] so
    # the symmetric algorithm is rejected before signature verification.
    token = jwt.encode(claims, "shared-secret", algorithm="HS256")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_missing_required_exp_claim_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(claims_override={"exp": None})
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_missing_required_sub_claim_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(claims_override={"sub": None})
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


# ---------------------------------------------------------------------------
# Authorization header parsing
# ---------------------------------------------------------------------------


async def test_missing_authorization_header_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    response = await oidc_client.get(_TEST_ROUTE_READ)
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_empty_bearer_token_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    response = await oidc_client.get(
        _TEST_ROUTE_READ, headers={"Authorization": "Bearer "}
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_whitespace_only_bearer_token_returns_401(
    synthetic_rs_idp: SyntheticRsIdp,
) -> None:
    # FastAPI's HTTPBearer strips trailing whitespace from the header value
    # before constructing credentials.credentials; to exercise the
    # whitespace-only branch in get_authenticated_principal we call the
    # dependency directly with a hand-built credentials object.
    from fastapi.security import HTTPAuthorizationCredentials

    from resource_server.auth.oidc_bearer import (
        AppException,
        ErrorCode,
        get_authenticated_principal,
    )

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="   ")
    with pytest.raises(AppException) as exc_info:
        await get_authenticated_principal(creds)
    assert exc_info.value.error_code is ErrorCode.SESSION_EXPIRED


async def test_basic_auth_scheme_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    response = await oidc_client.get(
        _TEST_ROUTE_READ,
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


# ---------------------------------------------------------------------------
# JWKS cache + key rotation
# ---------------------------------------------------------------------------


async def test_jwks_cache_hit_avoids_refetch_on_repeated_valid_requests(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    """Repeated requests with the same valid token MUST trigger exactly one
    JWKS fetch — cache_keys=True + the module-level dict cache."""
    token = synthetic_rs_idp.make_access_token()
    for _ in range(3):
        response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
        assert response.status_code == 200
    assert synthetic_rs_idp.fetch_call_count == 1


async def test_jwks_kid_miss_then_rotation_hit_triggers_refetch(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    """When a token's `kid` is not in the cached JWKS, PyJWKClient re-fetches
    exactly once; if the new JWKS contains the kid, validation succeeds."""
    # 1st request: prime the cache with the default kid.
    primer_token = synthetic_rs_idp.make_access_token()
    response = await oidc_client.get(
        _TEST_ROUTE_READ, headers=_auth_header(primer_token)
    )
    assert response.status_code == 200
    assert synthetic_rs_idp.fetch_call_count == 1

    # Now rotate: register a new kid and sign a token with it.
    alt_key = synthetic_rs_idp.register_rotated_kid(DEFAULT_ROTATED_KID)
    rotated_token = synthetic_rs_idp.make_access_token(
        signing_key=alt_key, kid=DEFAULT_ROTATED_KID
    )

    response = await oidc_client.get(
        _TEST_ROUTE_READ, headers=_auth_header(rotated_token)
    )
    assert response.status_code == 200
    # PyJWKClient detected the kid miss and re-fetched once — count is now 2.
    assert synthetic_rs_idp.fetch_call_count == 2


async def test_jwks_kid_miss_unknown_after_refetch_returns_401(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    """If the token's kid is missing from BOTH the cached JWKS and a re-fetched
    JWKS (key truly does not exist), validation fails 401."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = synthetic_rs_idp.make_access_token(
        signing_key=rogue_key, kid="never-issued-kid"
    )

    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


# ---------------------------------------------------------------------------
# Principal field population
# ---------------------------------------------------------------------------


async def test_principal_scopes_is_frozenset_with_expected_members(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(
        scope="openid reading-speed:read reading-speed:write"
    )
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["scopes"] == sorted(
        ["openid", "reading-speed:read", "reading-speed:write"]
    )


async def test_principal_subject_populated_from_jwt_sub_claim(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    sub = "user-a-uuid-1234"
    token = synthetic_rs_idp.make_access_token(sub=sub)
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 200
    assert response.json()["sub"] == sub


async def test_principal_name_populated_from_preferred_username(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(preferred_username="alice")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 200
    assert response.json()["name"] == "alice"


async def test_principal_name_none_when_preferred_username_absent(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    token = synthetic_rs_idp.make_access_token(preferred_username=None)
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 200
    assert response.json()["name"] is None


async def test_cross_user_isolation_distinct_subjects(
    synthetic_rs_idp: SyntheticRsIdp, oidc_client: AsyncClient
) -> None:
    sub_a = "user-a-" + random_subject()
    sub_b = "user-b-" + random_subject()
    token_a = synthetic_rs_idp.make_access_token(sub=sub_a)
    token_b = synthetic_rs_idp.make_access_token(sub=sub_b)

    r_a = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token_a))
    r_b = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token_b))

    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json()["sub"] == sub_a
    assert r_b.json()["sub"] == sub_b
    assert r_a.json()["sub"] != r_b.json()["sub"]


# ---------------------------------------------------------------------------
# Logging — failures emit WARNING with sanitized content
# ---------------------------------------------------------------------------


async def test_jwt_validation_failure_emits_warning_log_with_sanitized_reason(
    synthetic_rs_idp: SyntheticRsIdp,
    oidc_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="resource_server.auth.oidc_bearer")
    token = synthetic_rs_idp.make_access_token(exp_offset_seconds=-10)
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 401

    records = [
        r for r in caplog.records if r.name == "resource_server.auth.oidc_bearer"
    ]
    assert any("JWT validation failed" in r.getMessage() for r in records)
    # Sanitization: NO token contents, NO claim values, NO kid leak into the log.
    for r in records:
        msg = r.getMessage()
        assert token not in msg
        assert synthetic_rs_idp.kid not in msg


async def test_scope_rejection_emits_warning_log_with_sub_and_scope(
    synthetic_rs_idp: SyntheticRsIdp,
    oidc_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="resource_server.auth.oidc_bearer")
    sub = random_subject()
    token = synthetic_rs_idp.make_access_token(sub=sub, scope="openid")
    response = await oidc_client.get(_TEST_ROUTE_READ, headers=_auth_header(token))
    assert response.status_code == 403

    records = [
        r for r in caplog.records if r.name == "resource_server.auth.oidc_bearer"
    ]
    assert any("Scope check failed" in r.getMessage() for r in records)
    assert any(
        sub in r.getMessage() and "reading-speed:read" in r.getMessage()
        for r in records
    )


# ---------------------------------------------------------------------------
# make_oidc_bearer_auth (archetype seam) — both unsupported flows + happy path
# ---------------------------------------------------------------------------


async def test_make_oidc_bearer_auth_authenticate_returns_principal(
    synthetic_rs_idp: SyntheticRsIdp,
) -> None:
    from resource_server.core.config import settings

    auth_fns = oidc_bearer.make_oidc_bearer_auth(settings)
    token = synthetic_rs_idp.make_access_token(sub="seam-test-sub")
    principal = await auth_fns.authenticate_bearer_token(token)
    assert principal.subject == "seam-test-sub"
    assert "reading-speed:read" in principal.scopes


async def test_make_oidc_bearer_auth_authenticate_raises_unauthorized_on_bad_token(
    synthetic_rs_idp: SyntheticRsIdp,
) -> None:
    from resource_server.auth.contracts import UnauthorizedError
    from resource_server.core.config import settings

    auth_fns = oidc_bearer.make_oidc_bearer_auth(settings)
    with pytest.raises(UnauthorizedError):
        await auth_fns.authenticate_bearer_token("not.a.real.jwt")


async def test_make_oidc_bearer_auth_client_credentials_unsupported() -> None:
    from resource_server.auth.contracts import AuthFeatureNotSupportedError
    from resource_server.core.config import settings

    auth_fns = oidc_bearer.make_oidc_bearer_auth(settings)
    with pytest.raises(AuthFeatureNotSupportedError):
        await auth_fns.get_client_credentials_access_token("any-scope")


async def test_make_oidc_bearer_auth_on_behalf_of_unsupported() -> None:
    from resource_server.auth.contracts import AuthFeatureNotSupportedError
    from resource_server.core.config import settings

    auth_fns = oidc_bearer.make_oidc_bearer_auth(settings)
    with pytest.raises(AuthFeatureNotSupportedError):
        await auth_fns.get_on_behalf_of_access_token("scope", "user-token")


# ---------------------------------------------------------------------------
# Helper unit tests — _parse_scopes covers non-string claim shape
# ---------------------------------------------------------------------------


def test_parse_scopes_returns_empty_frozenset_for_non_string_claim() -> None:
    """Keycloak emits `scope` as a space-delimited string; non-string shapes
    (None, list, int) MUST yield an empty frozenset rather than raise."""
    assert oidc_bearer._parse_scopes(None) == frozenset()
    assert oidc_bearer._parse_scopes(["openid"]) == frozenset()
    assert oidc_bearer._parse_scopes(42) == frozenset()


def test_parse_scopes_splits_on_any_whitespace_and_drops_empty() -> None:
    assert oidc_bearer._parse_scopes("openid reading-speed:read") == frozenset(
        {"openid", "reading-speed:read"}
    )
    assert oidc_bearer._parse_scopes("") == frozenset()
    assert oidc_bearer._parse_scopes("   ") == frozenset()


# ---------------------------------------------------------------------------
# Factory dispatch — oidc_bearer is wired up alongside none + entra
# ---------------------------------------------------------------------------


def test_factory_dispatch_includes_oidc_bearer(
    synthetic_rs_idp: SyntheticRsIdp,
) -> None:
    from resource_server.auth.factory import get_auth
    from resource_server.core.config import AppSettings

    test_settings = AppSettings(
        auth_type="oidc_bearer",
        oidc_issuer_url=synthetic_rs_idp.issuer,
        oidc_jwks_url=synthetic_rs_idp.jwks_url,
        oidc_audience=synthetic_rs_idp.audience,
    )
    auth_fns = get_auth(test_settings)
    assert auth_fns.role_mapper("admin") == "admin"
    # Returned AuthFunctions has the four callables wired:
    assert callable(auth_fns.authenticate_bearer_token)
    assert callable(auth_fns.get_client_credentials_access_token)
    assert callable(auth_fns.get_on_behalf_of_access_token)
