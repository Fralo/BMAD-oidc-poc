"""PKCE (RFC 7636) verifier/challenge helpers for the BFF's OIDC client.

The `code_verifier` is a high-entropy random URL-safe string (43–128 chars,
RFC 7636 §4.1). The `code_challenge` is the base64url-no-pad SHA-256 hash of
the verifier (S256 challenge method, RFC 7636 §4.2). Both live server-side on
the BFF: the verifier is persisted in the `auth_states` row at `/auth/login`
and replayed against Keycloak's `/token` endpoint at `/auth/callback`.
"""

import base64
import hashlib
import secrets
from typing import Final

S256_METHOD: Final[str] = "S256"

_VERIFIER_ENTROPY_BYTES = 64


def generate_code_verifier() -> str:
    """Return a fresh, URL-safe PKCE `code_verifier` (RFC 7636 §4.1)."""
    return secrets.token_urlsafe(_VERIFIER_ENTROPY_BYTES)


def compute_code_challenge(verifier: str) -> str:
    """Return `base64url-no-pad(SHA256(verifier))` — the S256 challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
