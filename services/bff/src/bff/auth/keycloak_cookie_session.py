"""Authlib + PyJWT-based OIDC cookie-session plugin (Story 1.5).

The BFF acts as a confidential Authorization Code client (no PKCE — the
confidential `client_secret` is the trust basis with the AS, authenticated
via `client_secret_basic` per RFC 6749 §2.3.1). This module exposes:

* `state_id_serializer(secret)` / `sign_state_id` / `verify_state_id` —
  HMAC-signed short-lived cookie carrying the `auth_states.id` (5-min TTL).
* `build_authorize_url(...)` — assembles the 302-target sent to the browser
  on `/auth/login`. Uses the *browser-facing* authorize URL (see D2/D8 split).
* `exchange_code(...)` — back-channel POST to Keycloak's `/token` endpoint.
  Honors architecture §C6 (5s connect / 10s read; no retries).
* `verify_id_token(...)` — JWKS-backed RS256 verification with `iss`/`aud`/
  `exp`/`nonce` claim checks. Raises `OidcVerificationError` on any failure.
"""

import logging
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from authlib.integrations.httpx_client import AsyncOAuth2Client
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

# itsdangerous salt — domain-separates this signer from any other use of the
# BFF's session secret. Static value is safe; the secret carries the entropy.
_STATE_ID_SALT = "bff-state-id"

# Architecture §C6: BFF → Keycloak budget. No retries on `/token`; the user
# can simply click "Log in" again if Keycloak is flaky.
_TOKEN_EXCHANGE_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)


class OidcVerificationError(Exception):
    """Raised on any token-exchange or id-token-verification failure.

    Callers map this to `ErrorCode.AUTH_STATE_INVALID` (HTTP 400). The
    exception's message MUST NOT contain token material — only a short
    classifier for the failure mode (used for logging at WARN).
    """


# ---------------------------------------------------------------------------
# State-id cookie signing
# ---------------------------------------------------------------------------


def state_id_serializer(secret: str) -> URLSafeTimedSerializer:
    """Return a configured `URLSafeTimedSerializer` keyed on `secret`."""
    return URLSafeTimedSerializer(secret_key=secret, salt=_STATE_ID_SALT)


def sign_state_id(serializer: URLSafeTimedSerializer, row_id: str) -> str:
    """HMAC-sign the auth_states row id; emits a URL-safe string."""
    return serializer.dumps(row_id)


def verify_state_id(
    serializer: URLSafeTimedSerializer,
    signed: str | None,
    *,
    max_age_seconds: int = 300,
) -> str | None:
    """Verify the signed state-id cookie. Returns the row id or `None`.

    Defaults to a 5-minute max_age (matches `auth_states.expires_at` TTL).
    Returns `None` on missing/empty/malformed/expired/tampered input — the
    caller maps `None` to a 400 `auth_state_invalid` response.
    """
    if not signed:
        return None
    try:
        loaded = serializer.loads(signed, max_age=max_age_seconds)
    except BadSignature, SignatureExpired:
        return None
    if not isinstance(loaded, str):
        return None
    return loaded


# ---------------------------------------------------------------------------
# Authorize URL
# ---------------------------------------------------------------------------


def build_authorize_url(
    *,
    authorize_endpoint: str,
    redirect_uri: str,
    client_id: str,
    scopes: Iterable[str],
    state: str,
    nonce: str,
) -> str:
    """Return the browser-facing 302 target for `/auth/login`.

    Story 7.2: `authorize_endpoint` is the full URL of the OIDC authorize
    endpoint (scheme+authority+path) — typically derived from
    `discovery.authorization_endpoint` with the host:port rebased onto
    `OIDC_PUBLIC_BASE_URL` (the browser-facing host the user can resolve).
    The endpoint already encodes Keycloak's `/protocol/openid-connect/auth`
    path, so this function is now query-string-only. No `code_challenge`
    is sent — this is a confidential client and the `client_secret`
    (carried on the back-channel `/token` POST) is the trust basis.
    """
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(scopes),
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": nonce,
    }
    return f"{authorize_endpoint}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# return_to validation (open-redirect prevention — closes D33)
# ---------------------------------------------------------------------------


def safe_return_to(raw: str | None) -> str:
    """Sanitize a user-supplied `return_to` query parameter.

    Returns the input when it is an absolute path (starts with a single `/`)
    with no scheme before the first slash boundary and length ≤ 1024. Anything
    else collapses silently to `"/"` — no signal to a probing attacker.
    """
    if not raw or len(raw) > 1024:
        return "/"
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    # Block `https:foo`, `javascript:alert`, etc. before the first slash boundary.
    first_slash = raw.index("/", 1) if "/" in raw[1:] else len(raw)
    if ":" in raw[:first_slash]:
        return "/"
    return raw


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


async def exchange_code(
    *,
    code: str,
    redirect_uri: str,
    token_url: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Exchange `code` for an access/refresh/id-token triple.

    Honors §C6 timeouts. Authenticates with `client_secret_basic` (Authlib
    default). Raises `OidcVerificationError` on any non-2xx from Keycloak
    (invalid/expired code, client_secret mismatch, network failure).
    """
    try:
        async with AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            timeout=_TOKEN_EXCHANGE_TIMEOUT,
        ) as client:
            token = await client.fetch_token(
                url=token_url,
                grant_type="authorization_code",
                code=code,
                redirect_uri=redirect_uri,
            )
    except Exception as exc:  # Authlib raises a constellation of errors here
        # noqa: BLE001 -- normalize any failure to a single exception class so
        # the router can map all of them to one 400 `auth_state_invalid`.
        raise OidcVerificationError(
            f"token_exchange_failed: {type(exc).__name__}"
        ) from exc
    if not isinstance(token, dict):
        raise OidcVerificationError("token_exchange_returned_non_mapping")
    return token


# ---------------------------------------------------------------------------
# id_token verification
# ---------------------------------------------------------------------------

# Module-level cache keyed by JWKS URL so `cache_keys=True` actually persists
# across requests. PyJWKClient.get_signing_key_from_jwt uses synchronous urllib
# internally; that call is infrequent (key cache hit on most requests) but
# callers should be aware it blocks the event loop on a cache miss.
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = jwt.PyJWKClient(
            jwks_url, cache_keys=True, max_cached_keys=4
        )
    return _jwks_clients[jwks_url]


def verify_id_token(
    *,
    id_token: str,
    jwks_url: str,
    expected_issuer: str,
    expected_audience: str,
    expected_nonce: str,
) -> dict[str, Any]:
    """RS256-verify the id_token via JWKS and assert claim constraints.

    `expected_issuer` MUST be the browser-facing issuer URL (Keycloak signs
    tokens with `iss=KC_HOSTNAME` — see D2/D8 caveat in story 1.5 dev notes).
    Returns the decoded claims dict on success; raises `OidcVerificationError`
    on any failure.
    """
    try:
        jwks_client = _get_jwks_client(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        decoded = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
            options={"require": ["iss", "aud", "exp", "iat", "nonce", "sub"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise OidcVerificationError(f"id_token_invalid: {type(exc).__name__}") from exc

    if not isinstance(decoded, dict):  # pragma: no cover -- PyJWT always returns dict
        raise OidcVerificationError("id_token_decoded_non_mapping")

    if decoded.get("nonce") != expected_nonce:
        raise OidcVerificationError("id_token_nonce_mismatch")

    return decoded


# ---------------------------------------------------------------------------
# Revocation + RP-Initiated Logout (Story 1.7)
# ---------------------------------------------------------------------------


async def revoke_refresh_token(
    *,
    refresh_token: str,
    revocation_url: str,
    client_id: str,
    client_secret: str,
) -> None:
    """POST `refresh_token` to the OIDC revocation endpoint (RFC 7009 §2.1).

    Uses HTTP Basic auth for confidential clients (httpx auto-base64s the
    `client_id:client_secret` pair). Honors architecture §C6 (5s connect /
    10s read; zero retries). Raises `httpx.HTTPStatusError` on any non-2xx
    response (including 3xx — a redirect from a misconfigured AS or a
    path-rewriting proxy would otherwise be silently treated as success
    while NOT revoking the token, bypassing AC7). Transport failures
    surface as the matching `httpx.HTTPError` subclass. The caller
    (`/auth/logout`) wraps this in try/except so an unreachable AS does
    NOT block local session teardown (architecture §A7 — degrade honestly).
    """
    async with httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT) as client:
        response = await client.post(
            revocation_url,
            data={"token": refresh_token, "token_type_hint": "refresh_token"},
            auth=(client_id, client_secret),
        )
        if not response.is_success:
            raise httpx.HTTPStatusError(
                f"revocation endpoint returned {response.status_code}",
                request=response.request,
                response=response,
            )


def build_end_session_url(
    *,
    end_session_url: str,
    id_token: str,
    post_logout_redirect_uri: str,
) -> str:
    """Build a front-channel RP-initiated logout URL per OIDC RP-Initiated Logout 1.0.

    Keycloak validates `post_logout_redirect_uri` against the realm's
    `post.logout.redirect.uris` attribute. The browser is redirected here;
    Keycloak clears its SSO cookie and 302s back to the post-logout URI.
    """
    params = urlencode({
        "id_token_hint": id_token,
        "post_logout_redirect_uri": post_logout_redirect_uri,
    })
    separator = "&" if "?" in end_session_url else "?"
    return f"{end_session_url}{separator}{params}"


async def end_session(
    *,
    id_token: str,
    end_session_url: str,
    client_id: str,
    client_secret: str,
) -> None:
    """POST to the OIDC RP-Initiated Logout endpoint with `id_token_hint`.

    Keycloak's confidential-client POST variant takes `client_id` and
    `client_secret` as form fields (NOT Basic auth — RP-Initiated Logout
    spec leaves auth to the OP). Honors §C6 timeouts; zero retries.
    Raises `httpx.HTTPStatusError` on any non-2xx response (including 3xx
    — `follow_redirects=False` is the httpx default for POST, so a
    redirect from a misconfigured AS would otherwise be silently
    swallowed). Caller wraps in try/except per §A7.
    """
    async with httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT) as client:
        response = await client.post(
            end_session_url,
            data={
                "id_token_hint": id_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if not response.is_success:
            raise httpx.HTTPStatusError(
                f"end_session endpoint returned {response.status_code}",
                request=response.request,
                response=response,
            )
