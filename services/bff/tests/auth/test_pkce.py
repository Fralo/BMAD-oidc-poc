"""Tests for `bff.auth.pkce` (PKCE verifier/challenge helpers)."""

import base64
import hashlib
import re

import pytest

from bff.auth.pkce import (
    S256_METHOD,
    compute_code_challenge,
    generate_code_verifier,
)

# RFC 7636 §4.1 — verifier is 43–128 URL-safe characters.
_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


def test_s256_method_constant() -> None:
    assert S256_METHOD == "S256"


@pytest.mark.parametrize("_iteration", range(8))
def test_generate_code_verifier_within_rfc_7636_bounds(_iteration: int) -> None:
    """Verifier length is in [43, 128] and uses only URL-safe characters."""
    verifier = generate_code_verifier()
    assert 43 <= len(verifier) <= 128, (
        f"verifier length {len(verifier)} outside RFC 7636 bounds"
    )
    assert _VERIFIER_PATTERN.match(verifier), verifier


def test_generate_code_verifier_is_unique_across_calls() -> None:
    """High-entropy generator: two consecutive calls return distinct values."""
    verifiers = {generate_code_verifier() for _ in range(50)}
    assert len(verifiers) == 50


def test_compute_code_challenge_is_url_safe_no_pad() -> None:
    challenge = compute_code_challenge(generate_code_verifier())
    assert "+" not in challenge
    assert "/" not in challenge
    assert "=" not in challenge
    # base64url-no-pad of a 32-byte SHA-256 digest is exactly 43 chars.
    assert len(challenge) == 43


def test_compute_code_challenge_is_deterministic() -> None:
    verifier = generate_code_verifier()
    assert compute_code_challenge(verifier) == compute_code_challenge(verifier)


def test_compute_code_challenge_matches_rfc_7636_worked_example() -> None:
    """RFC 7636 Appendix B worked example.

    verifier  = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    """
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert compute_code_challenge(verifier) == expected_challenge


def test_compute_code_challenge_round_trip() -> None:
    """`base64url-decode(challenge) == SHA256(verifier)` — the verification math."""
    verifier = generate_code_verifier()
    challenge = compute_code_challenge(verifier)
    # Pad before decoding (b64 needs `len % 4 == 0`).
    padding = "=" * (-len(challenge) % 4)
    decoded = base64.urlsafe_b64decode(challenge + padding)
    assert decoded == hashlib.sha256(verifier.encode("ascii")).digest()
