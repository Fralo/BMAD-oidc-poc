"""Story 7.1 integration tests for `/api/me/roles` and `/api/admin/ping`.

Exercises the role-gated demo surface against the same fixture pattern
established by Story 1.5 + 1.6: seed a `sessions` row with the desired
`roles` blob, call the endpoint with the session cookie, assert wire shape.
The synthetic-IdP harness is not needed here because the role decision
reads from `sessions.roles` (the BFF's own column), not from the live
id_token. The /auth/callback wiring that populates that column is
exercised separately in `test_auth.py` (Story 7.1 AC5 #4).
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bff.auth.role_mapping import Role
from bff.models import entities
from bff.services.session_service import SessionService


async def _seed_session(
    session: AsyncSession,
    *,
    sub: str,
    roles: frozenset[Role] = frozenset(),
    expires_offset_seconds: int = 3600,
) -> entities.Session:
    service = SessionService()
    return await service.create_session(
        session,
        sub=sub,
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_offset_seconds),
        roles=roles,
    )


# ---------------------------------------------------------------------------
# GET /api/me/roles
# ---------------------------------------------------------------------------


async def test_me_roles_returns_401_when_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/me/roles")
    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "session_expired",
        "message": "Session expired or not present",
        "detail": None,
    }


async def test_me_roles_returns_401_when_unknown_session(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/me/roles", cookies={"bff_session": "never-existed"}
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_me_roles_returns_empty_array_for_session_without_roles(
    client: AsyncClient, session: AsyncSession
) -> None:
    row = await _seed_session(session, sub="nobody", roles=frozenset())
    response = await client.get("/api/me/roles", cookies={"bff_session": row.id})
    assert response.status_code == 200
    assert response.json() == {"roles": []}


async def test_me_roles_returns_reader_only_for_testuser(
    client: AsyncClient, session: AsyncSession
) -> None:
    """testuser is seeded with `reader` group in the realm (AC1)."""
    row = await _seed_session(
        session, sub="testuser-sub", roles=frozenset({Role.READER})
    )
    response = await client.get("/api/me/roles", cookies={"bff_session": row.id})
    assert response.status_code == 200
    assert response.json() == {"roles": ["reader"]}


async def test_me_roles_returns_both_sorted_for_freshuser(
    client: AsyncClient, session: AsyncSession
) -> None:
    """freshuser is seeded with `reader` + `admin` groups (AC1). Wire order
    is alphabetical: `admin` precedes `reader`."""
    row = await _seed_session(
        session, sub="freshuser-sub", roles=frozenset({Role.READER, Role.ADMIN})
    )
    response = await client.get("/api/me/roles", cookies={"bff_session": row.id})
    assert response.status_code == 200
    assert response.json() == {"roles": ["admin", "reader"]}


async def test_me_roles_returns_401_for_expired_session(
    client: AsyncClient, session: AsyncSession
) -> None:
    row = await _seed_session(
        session,
        sub="expired-sub",
        roles=frozenset({Role.ADMIN}),
        expires_offset_seconds=-60,
    )
    response = await client.get("/api/me/roles", cookies={"bff_session": row.id})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"

    # Lazy-delete side effect.
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is None


# ---------------------------------------------------------------------------
# GET /api/admin/ping
# ---------------------------------------------------------------------------


async def test_admin_ping_returns_401_when_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/admin/ping")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_admin_ping_returns_401_when_unknown_session(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": "never-existed"}
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_admin_ping_returns_403_for_reader_only(
    client: AsyncClient, session: AsyncSession
) -> None:
    """testuser → reader only → 403 forbidden_scope on /api/admin/ping."""
    row = await _seed_session(
        session, sub="testuser-sub", roles=frozenset({Role.READER})
    )
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == 403
    assert response.json() == {
        "errorCode": "forbidden_scope",
        "message": "Required role missing",
        "detail": None,
    }


async def test_admin_ping_returns_403_when_session_has_no_roles(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A session with `roles=""` is denied — the 403 path doesn't special-case
    the empty list; absence-of-admin is the only check."""
    row = await _seed_session(session, sub="nobody", roles=frozenset())
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "forbidden_scope"


async def test_admin_ping_returns_200_for_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    """freshuser → reader + admin → 200 ok."""
    row = await _seed_session(
        session, sub="freshuser-sub", roles=frozenset({Role.READER, Role.ADMIN})
    )
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_admin_ping_returns_200_for_admin_only(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Admin alone (no reader) also passes — the check is admin presence."""
    row = await _seed_session(
        session, sub="admin-only-sub", roles=frozenset({Role.ADMIN})
    )
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_admin_ping_returns_401_for_expired_session_with_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The 401 (no session) check precedes the 403 (no role) check — an
    expired session row carrying admin must NOT leak the role decision."""
    row = await _seed_session(
        session,
        sub="expired-admin-sub",
        roles=frozenset({Role.ADMIN}),
        expires_offset_seconds=-60,
    )
    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


@pytest.mark.parametrize(
    ("stored_blob", "expected_status"),
    [
        pytest.param("", 403, id="empty"),
        pytest.param("reader", 403, id="reader_only"),
        pytest.param("admin", 200, id="admin_only"),
        pytest.param("admin,reader", 200, id="both"),
        # Defensive: an unsorted blob still works because the membership
        # check is order-insensitive (read via `deserialize_roles`).
        pytest.param("reader,admin", 200, id="both_unsorted"),
    ],
)
async def test_admin_ping_membership_check_is_string_based(
    client: AsyncClient,
    session: AsyncSession,
    stored_blob: str,
    expected_status: int,
) -> None:
    """The admin check reads the stored blob via `deserialize_roles` — pin
    the through-the-wire behavior for representative blob shapes. This is
    a regression guard against future refactors that try to short-circuit
    on the raw string (e.g., `"admin" in row.roles` would mis-match
    `"administrator"` if a future role name appeared)."""
    service = SessionService()
    row = await service.create_session(
        session,
        sub=f"probe-{stored_blob or 'empty'}",
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    # Bypass the serialize_roles path to set the blob byte-for-byte.
    row.roles = stored_blob
    session.add(row)
    await session.commit()

    response = await client.get(
        "/api/admin/ping", cookies={"bff_session": row.id}
    )
    assert response.status_code == expected_status
