"""Request-layer tests for `/v1/reading-speed` (GET + PUT).

Uses the synthetic-IdP harness from Story 3.2 to mint signed JWTs with
arbitrary scope/sub combinations — no real Keycloak needed. Every test
validates the full HTTP envelope (`errorCode`, status, detail shape).
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
) -> str:
    return idp.make_access_token(sub=sub, scope=scope)


# ---------------------------------------------------------------------------
# GET /v1/reading-speed
# ---------------------------------------------------------------------------


async def test_get_returns_200_with_pages_per_hour_when_row_exists(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    # Seed a row via PUT (with write scope) then read it back with read scope.
    write_token = _make_token(
        synthetic_rs_idp, sub="user-1", scope="openid reading-speed:write"
    )
    put = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 30},
        headers=_auth_header(write_token),
    )
    assert put.status_code == 200

    read_token = _make_token(
        synthetic_rs_idp, sub="user-1", scope="openid reading-speed:read"
    )
    response = await client.get("/v1/reading-speed", headers=_auth_header(read_token))
    assert response.status_code == 200
    assert response.json() == {"pages_per_hour": 30}


async def test_get_returns_412_reading_speed_unset_when_row_absent(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(synthetic_rs_idp, sub="orphan-sub")
    response = await client.get("/v1/reading-speed", headers=_auth_header(token))
    assert response.status_code == 412
    assert response.json() == {
        "errorCode": "reading_speed_unset",
        "message": "Reading speed not set for this user",
        "detail": None,
    }


async def test_get_returns_403_forbidden_scope_when_only_write_scope_present(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:write")
    response = await client.get("/v1/reading-speed", headers=_auth_header(token))
    assert response.status_code == 403
    assert response.json()["errorCode"] == "forbidden_scope"


async def test_get_returns_401_session_expired_when_no_authorization_header(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    response = await client.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


# ---------------------------------------------------------------------------
# PUT /v1/reading-speed
# ---------------------------------------------------------------------------


async def test_put_insert_path_creates_row_and_returns_200(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(
        synthetic_rs_idp, sub="fresh-user", scope="openid reading-speed:write"
    )
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 25},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json() == {"pages_per_hour": 25}


async def test_put_update_path_replaces_value_and_returns_200(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    write_token = _make_token(
        synthetic_rs_idp, sub="user-2", scope="openid reading-speed:write"
    )
    first = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 20},
        headers=_auth_header(write_token),
    )
    assert first.status_code == 200
    assert first.json() == {"pages_per_hour": 20}

    second = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 50},
        headers=_auth_header(write_token),
    )
    assert second.status_code == 200
    assert second.json() == {"pages_per_hour": 50}


async def test_put_returns_403_forbidden_scope_when_only_read_scope_present(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:read")
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 30},
        headers=_auth_header(token),
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "forbidden_scope"


@pytest.mark.parametrize("bad_value", [0, -1, -100])
async def test_put_returns_422_invalid_input_on_non_positive_value(
    synthetic_rs_idp: SyntheticRsIdp,
    client: AsyncClient,
    bad_value: int,
) -> None:
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:write")
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": bad_value},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "invalid_input"
    assert isinstance(body["detail"], list)
    # Sanitization (BFF Story 1.3 P3 mirror): no `input` field leaks into the response.
    for entry in body["detail"]:
        assert "input" not in entry, f"input leaked: {entry}"


async def test_put_returns_422_invalid_input_when_field_missing(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:write")
    response = await client.put(
        "/v1/reading-speed", json={}, headers=_auth_header(token)
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_put_returns_422_invalid_input_when_field_wrong_type(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    token = _make_token(synthetic_rs_idp, scope="openid reading-speed:write")
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": "thirty"},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_put_returns_401_session_expired_when_no_authorization_header(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    response = await client.put("/v1/reading-speed", json={"pages_per_hour": 30})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_put_accepts_boundary_value_one(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """`ge=1` means 1 is accepted; pins the boundary so a future tightening
    to `gt=1` is caught."""
    token = _make_token(
        synthetic_rs_idp, sub="boundary-user", scope="openid reading-speed:write"
    )
    response = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 1},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json() == {"pages_per_hour": 1}


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


async def test_cross_user_isolation_put_then_get(
    synthetic_rs_idp: SyntheticRsIdp, client: AsyncClient
) -> None:
    """User A's PUT does not affect User B's row; each GET returns their own
    value. Identity comes from the JWT sub, never from body/path/query."""
    a_write = _make_token(
        synthetic_rs_idp, sub="user-a-xyz", scope="openid reading-speed:write"
    )
    b_write = _make_token(
        synthetic_rs_idp, sub="user-b-xyz", scope="openid reading-speed:write"
    )
    a_read = _make_token(
        synthetic_rs_idp, sub="user-a-xyz", scope="openid reading-speed:read"
    )
    b_read = _make_token(
        synthetic_rs_idp, sub="user-b-xyz", scope="openid reading-speed:read"
    )

    pa = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 30},
        headers=_auth_header(a_write),
    )
    pb = await client.put(
        "/v1/reading-speed",
        json={"pages_per_hour": 50},
        headers=_auth_header(b_write),
    )
    assert pa.status_code == 200
    assert pb.status_code == 200

    ga = await client.get("/v1/reading-speed", headers=_auth_header(a_read))
    gb = await client.get("/v1/reading-speed", headers=_auth_header(b_read))

    assert ga.json() == {"pages_per_hour": 30}
    assert gb.json() == {"pages_per_hour": 50}
