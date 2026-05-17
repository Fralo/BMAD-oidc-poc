"""Request-layer tests for ``POST /v1/estimate``.

Mirrors the structure of ``test_reading_speed.py`` (Story 3.3): synthetic-IdP
harness from ``tests.auth.synthetic_idp`` mints signed JWTs with arbitrary
scope/sub combinations, every test validates the full HTTP envelope
(``errorCode``, status, detail shape).

Covered ACs:
    AC4  — happy path 200 with ``{minutes, formatted}``
    AC5  — 403 ``forbidden_scope`` on write-only scope
    AC6  — 412 ``reading_speed_unset`` on missing row
    AC7  — 422 ``invalid_input`` on non-positive / missing / wrong-type / non-object
    AC8  — 401 ``session_expired`` on no / expired / wrong-audience JWT
    AC9  — 422 ``invalid_input`` + ``extra_forbidden`` on body-level ``sub`` injection
    AC10 — cross-user isolation
    AC11 — speed-change yields different estimate
    AC12 — float-coercion mirror (Story 3.3 CR2)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.auth.synthetic_idp import SyntheticRsIdp, build_synthetic_rs_idp


@pytest.fixture(name="synthetic_rs_idp")
def synthetic_rs_idp_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticRsIdp:
    return build_synthetic_rs_idp(monkeypatch)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_token(
    idp: SyntheticRsIdp,
    *,
    sub: str = "test-sub-001",
    scope: str = "openid reading-speed:read",
    **kwargs: object,
) -> str:
    return idp.make_access_token(sub=sub, scope=scope, **kwargs)  # ty: ignore[invalid-argument-type]


async def _seed_reading_speed(
    idp: SyntheticRsIdp,
    client: AsyncClient,
    *,
    sub: str,
    pages_per_hour: int,
) -> None:
    """Helper: PUT a ``reading_speeds`` row via the write-scoped endpoint.

    Mirrors the seed pattern in ``test_reading_speed.py::test_get_returns_200``
    so the estimate tests don't reach into the ORM directly.
    """
    write_token = _make_token(idp, sub=sub, scope="openid reading-speed:write")
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": pages_per_hour},
        headers=_auth_header(write_token),
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# AC4 — Happy path
# ---------------------------------------------------------------------------


async def test_post_estimate_200_with_minutes_and_formatted(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC4: ``pages_per_hour=30`` + ``pages=600`` → ``{1200, "≈ 20 h"}``."""
    await _seed_reading_speed(
        synthetic_rs_idp, client, sub="user-happy", pages_per_hour=30
    )

    read_token = _make_token(synthetic_rs_idp, sub="user-happy")
    response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(read_token)
    )

    assert response.status_code == 200
    assert response.json() == {"minutes": 1200, "formatted": "≈ 20 h"}


# ---------------------------------------------------------------------------
# AC6 — 412 ``reading_speed_unset`` on missing row
# ---------------------------------------------------------------------------


async def test_post_estimate_412_when_reading_speed_unset(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC6: no PUT, post estimate with read scope → 412 full envelope."""
    token = _make_token(synthetic_rs_idp, sub="orphan-sub")
    response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(token)
    )

    assert response.status_code == 412
    assert response.json() == {
        "errorCode": "reading_speed_unset",
        "message": "Reading speed not set for this user",
        "detail": None,
    }


# ---------------------------------------------------------------------------
# AC5 — 403 ``forbidden_scope`` when only write scope present
# ---------------------------------------------------------------------------


async def test_post_estimate_403_when_only_write_scope(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC5: ``reading-speed:write`` alone is rejected by the read-scope gate."""
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:write")
    response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(token)
    )

    assert response.status_code == 403
    assert response.json()["errorCode"] == "forbidden_scope"


# ---------------------------------------------------------------------------
# AC7 — 422 ``invalid_input`` on bad bodies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [0, -1, -100])
async def test_post_estimate_422_on_non_positive_pages(
    synthetic_rs_idp: SyntheticRsIdp,
    client: AsyncClient,
    bad_value: int,
) -> None:
    """AC7: ``Field(ge=1)`` rejects 0 and negatives at the boundary."""
    token = _make_token(synthetic_rs_idp)
    response = await client.post(
        "/v1/estimate", json={"pages": bad_value}, headers=_auth_header(token)
    )

    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "invalid_input"
    assert isinstance(body["detail"], list)
    # Sanitization mirror (Story 3.3 CR2 / BFF Story 1.3 P3): no ``input``
    # field leaks into 422 responses.
    for entry in body["detail"]:
        assert "input" not in entry, f"input leaked: {entry}"


async def test_post_estimate_422_when_pages_missing(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC7: empty body → 422 ``invalid_input``."""
    token = _make_token(synthetic_rs_idp)
    response = await client.post("/v1/estimate", json={}, headers=_auth_header(token))

    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_post_estimate_422_when_pages_wrong_type(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC7: ``pages: "thirty"`` → 422 ``invalid_input``."""
    token = _make_token(synthetic_rs_idp)
    response = await client.post(
        "/v1/estimate", json={"pages": "thirty"}, headers=_auth_header(token)
    )

    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


@pytest.mark.parametrize("bad_float", [1.5, 30.5, 0.5])
async def test_post_estimate_422_rejects_non_integer_float_pages(
    synthetic_rs_idp: SyntheticRsIdp,
    client: AsyncClient,
    bad_float: float,
) -> None:
    """AC7 + Story 3.3 CR2 mirror: Pydantic v2's strict-int default rejects
    JSON floats with a non-zero fractional part."""
    token = _make_token(synthetic_rs_idp)
    response = await client.post(
        "/v1/estimate", json={"pages": bad_float}, headers=_auth_header(token)
    )

    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


@pytest.mark.parametrize("bad_body", [[], "hello", 42])
async def test_post_estimate_422_when_body_not_object(
    synthetic_rs_idp: SyntheticRsIdp,
    client: AsyncClient,
    bad_body: object,
) -> None:
    """AC7: non-object bodies are rejected by Pydantic model validation."""
    token = _make_token(synthetic_rs_idp)
    response = await client.post(
        "/v1/estimate", json=bad_body, headers=_auth_header(token)
    )

    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


# ---------------------------------------------------------------------------
# AC8 — 401 ``session_expired`` on missing / expired / wrong-audience JWT
# ---------------------------------------------------------------------------


async def test_post_estimate_401_when_no_authorization_header(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC8: no ``Authorization`` header → 401."""
    response = await client.post("/v1/estimate", json={"pages": 600})

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_post_estimate_401_when_token_expired(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC8: expired JWT → 401."""
    token = _make_token(synthetic_rs_idp, exp_offset_seconds=-1)
    response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(token)
    )

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_post_estimate_401_when_wrong_audience(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC8: JWT with wrong ``aud`` → 401."""
    token = _make_token(synthetic_rs_idp, aud="wrong-audience")
    response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(token)
    )

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


# ---------------------------------------------------------------------------
# AC9 — Sub-injection via body is rejected as 422 with ``extra_forbidden``
# ---------------------------------------------------------------------------


async def test_post_estimate_422_rejects_unknown_field_sub_injection(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC9: ``EstimateIn.extra="forbid"`` rejects body-level ``sub`` injection
    as 422 with an ``extra_forbidden`` entry. Defends against client typos
    AND privilege-escalation attempts — identity must always come from the
    JWT.

    Mirror of Story 3.3 CR1 test at ``test_reading_speed.py:267``.
    """
    # Seed user-a's row so the request would otherwise succeed under
    # a hypothetical ``extra="ignore"`` config — pinning the 422 here
    # ensures the defense kicks in BEFORE the seeded row is reached.
    await _seed_reading_speed(synthetic_rs_idp, client, sub="user-a", pages_per_hour=30)

    token = _make_token(synthetic_rs_idp, sub="user-a")
    response = await client.post(
        "/v1/estimate",
        json={"pages": 600, "sub": "victim-sub"},
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "invalid_input"
    assert any(entry.get("type") == "extra_forbidden" for entry in body["detail"]), (
        f"expected an extra_forbidden entry in detail; got {body['detail']}"
    )


# ---------------------------------------------------------------------------
# AC10 — Cross-user isolation
# ---------------------------------------------------------------------------


async def test_cross_user_isolation_estimate(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC10: each user's estimate uses their own row — verified through
    the full request path (JWT ``sub`` → service → DB lookup → DTO)."""
    await _seed_reading_speed(
        synthetic_rs_idp, client, sub="user-fast", pages_per_hour=60
    )
    await _seed_reading_speed(
        synthetic_rs_idp, client, sub="user-slow", pages_per_hour=30
    )

    fast_token = _make_token(synthetic_rs_idp, sub="user-fast")
    slow_token = _make_token(synthetic_rs_idp, sub="user-slow")

    fast_response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(fast_token)
    )
    slow_response = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(slow_token)
    )

    assert fast_response.json() == {"minutes": 600, "formatted": "≈ 10 h"}
    assert slow_response.json() == {"minutes": 1200, "formatted": "≈ 20 h"}


# ---------------------------------------------------------------------------
# AC11 — Speed change yields different estimate
# ---------------------------------------------------------------------------


async def test_speed_change_yields_different_estimate(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """AC11: PUT new ``pages_per_hour`` between two estimates → different
    ``minutes``. Pins Story 4.4's J3 "speed change yields different
    estimate" assertion at the RS layer."""
    sub = "user-changer"
    await _seed_reading_speed(synthetic_rs_idp, client, sub=sub, pages_per_hour=30)

    read_token = _make_token(synthetic_rs_idp, sub=sub)
    r1 = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(read_token)
    )
    assert r1.json()["minutes"] == 1200

    # Bump pages_per_hour and re-estimate.
    await _seed_reading_speed(synthetic_rs_idp, client, sub=sub, pages_per_hour=60)
    r2 = await client.post(
        "/v1/estimate", json={"pages": 600}, headers=_auth_header(read_token)
    )

    assert r2.json()["minutes"] == 600
    assert r2.json()["minutes"] < r1.json()["minutes"]
    assert r1.json()["formatted"] != r2.json()["formatted"]


# ---------------------------------------------------------------------------
# AC12 — Pydantic v2 lax-int-coercion of whole-number floats (Story 3.3 CR2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("whole_float", [600.0, 1.0, 60.0])
async def test_post_estimate_accepts_whole_number_floats_as_int(
    synthetic_rs_idp: SyntheticRsIdp,
    client: AsyncClient,
    whole_float: float,
) -> None:
    """AC12 / Story 3.3 CR2 mirror: JSON ``600.0`` is a float at the wire
    level; Pydantic v2's ``int`` field accepts whole-number floats via
    lax coercion (``600.0`` → ``600``). Pin the behavior so a future
    tightening to ``Field(strict=True)`` surfaces as a contract change
    rather than silently breaking SPA clients that send ``Number`` values
    (JS has no native int)."""
    await _seed_reading_speed(
        synthetic_rs_idp, client, sub="user-floats", pages_per_hour=60
    )

    token = _make_token(synthetic_rs_idp, sub="user-floats")
    response = await client.post(
        "/v1/estimate", json={"pages": whole_float}, headers=_auth_header(token)
    )

    assert response.status_code == 200
    assert response.json()["minutes"] == int(whole_float * 60 / 60)
