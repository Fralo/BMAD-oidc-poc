"""Route-level tests for /v1/books CRUD (Story 2.2).

Covers session auth, CSRF, cross-user isolation, validation, and the
five verbs (LIST, CREATE, READ, UPDATE, DELETE). Service-layer
behavior is exercised separately in tests/services/test_books_service.py.

The `_seed_session` helper is duplicated from tests/api/test_me.py per
the project's "small redundancy over abstraction" stance — keeping
test files self-contained outweighs the 30-line copy.
"""

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.core.config import settings
from bff.models import entities
from bff.models.entities.session import Session as SessionRow
from bff.services.session_service import SessionService


async def _seed_session(
    session: AsyncSession,
    *,
    sub: str = "test-sub-1",
    preferred_username: str = "testuser",
    expires_offset_seconds: int = 3600,
) -> entities.Session:
    """Insert a `sessions` row with a self-signed id_token (no verification).

    Copied from tests/api/test_me.py::_seed_session — duplicated rather
    than imported per the project's test-file self-containment stance.
    """
    service = SessionService()
    now_ts = int(datetime.now(UTC).timestamp())
    id_token = jwt.encode(
        {
            "sub": sub,
            "preferred_username": preferred_username,
            "iss": "http://idp.test/realms/test",
            "aud": "test-client",
            "exp": now_ts + expires_offset_seconds,
            "iat": now_ts,
            "nonce": "n",
        },
        "test-secret-only-used-for-encoding",  # noqa: S106 -- not a real secret
        algorithm="HS256",
    )
    return await service.create_session(
        session,
        sub=sub,
        access_token="at",
        refresh_token="rt",
        id_token=id_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_offset_seconds),
    )


async def _seed_book(
    session: AsyncSession,
    *,
    sub: str,
    title: str = "Some Book",
    pages: int = 200,
    status_: str = "to-read",
    created_at: datetime | None = None,
) -> entities.Book:
    """Insert a `books` row directly. `created_at` may be passed to
    construct deterministic ordering for LIST tests."""
    kwargs: dict[str, object] = {
        "sub": sub,
        "title": title,
        "pages": pages,
        "status": status_,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
        kwargs["updated_at"] = created_at
    row = entities.Book(**kwargs)  # type: ignore[arg-type]
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Authentication — every endpoint
# ---------------------------------------------------------------------------


async def test_list_books_returns_401_when_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/v1/books")
    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "session_expired",
        "message": "Session expired or not present",
        "detail": None,
    }


async def test_create_book_returns_401_when_no_cookie(
    client_with_csrf: AsyncClient,
) -> None:
    # client_with_csrf so CSRF middleware doesn't short-circuit with 403.
    response = await client_with_csrf.post(
        "/v1/books", json={"title": "x", "pages": 10}
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_read_book_returns_401_when_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/v1/books/1")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_update_book_returns_401_when_no_cookie(
    client_with_csrf: AsyncClient,
) -> None:
    response = await client_with_csrf.patch("/v1/books/1", json={"status": "reading"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_delete_book_returns_401_when_no_cookie(
    client_with_csrf: AsyncClient,
) -> None:
    response = await client_with_csrf.delete("/v1/books/1")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_list_books_returns_401_for_unknown_session_id(
    client: AsyncClient,
) -> None:
    response = await client.get("/v1/books", cookies={"bff_session": "never-existed"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_list_books_returns_401_and_deletes_expired_session(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="expired-sub", expires_offset_seconds=-60)
    response = await client.get("/v1/books", cookies={"bff_session": row.id})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"

    # Expired session was deleted as a side effect.
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is None


# ---------------------------------------------------------------------------
# CSRF — POST / PATCH / DELETE without the header/cookie
# ---------------------------------------------------------------------------


async def test_create_book_without_csrf_returns_403(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="csrf-sub")
    response = await client.post(
        "/v1/books",
        json={"title": "Dune", "pages": 688},
        cookies={"bff_session": row.id},
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"


async def test_update_book_without_csrf_returns_403(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="csrf-sub")
    response = await client.patch(
        "/v1/books/1",
        json={"status": "reading"},
        cookies={"bff_session": row.id},
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"


async def test_delete_book_without_csrf_returns_403(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="csrf-sub")
    response = await client.delete(
        "/v1/books/1",
        cookies={"bff_session": row.id},
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"


# ---------------------------------------------------------------------------
# LIST happy + isolation
# ---------------------------------------------------------------------------


async def test_list_books_returns_only_own_books(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess_a = await _seed_session(session, sub="user-A")
    base = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    await _seed_book(session, sub="user-A", title="A1", pages=100, created_at=base)
    await _seed_book(
        session,
        sub="user-A",
        title="A2",
        pages=200,
        created_at=base + timedelta(seconds=1),
    )
    await _seed_book(
        session,
        sub="user-A",
        title="A3",
        pages=300,
        created_at=base + timedelta(seconds=2),
    )
    await _seed_book(session, sub="user-B", title="B1", pages=400)
    await _seed_book(session, sub="user-B", title="B2", pages=500)

    response = await client.get("/v1/books", cookies={"bff_session": sess_a.id})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 3
    titles = [b["title"] for b in body]
    assert titles == ["A1", "A2", "A3"]
    # `sub` MUST NOT leak into the response (BookOut excludes it per
    # Story 2.1 AC3 / architecture §C7).
    for b in body:
        assert "sub" not in b


async def test_list_books_returns_empty_array_when_no_books(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="empty-sub")
    response = await client.get("/v1/books", cookies={"bff_session": sess.id})
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# CREATE happy + error paths
# ---------------------------------------------------------------------------


async def test_create_book_returns_201_with_location_header(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="create-sub")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "Dune", "pages": 688, "status": "reading"},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Dune"
    assert body["pages"] == 688
    assert body["status"] == "reading"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body
    assert "sub" not in body
    assert response.headers["Location"] == f"/v1/books/{body['id']}"

    # DB has the row with the correct `sub`.
    db_row = (
        (
            await session.execute(
                select(entities.Book).where(entities.Book.id == body["id"])
            )
        )
        .scalars()
        .first()
    )
    assert db_row is not None
    assert db_row.sub == "create-sub"


async def test_create_book_defaults_status_to_to_read_when_omitted(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="default-status")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "Dune", "pages": 688},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "to-read"


async def test_create_book_with_empty_body_returns_422(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="bad-body")
    response = await client_with_csrf.post(
        "/v1/books",
        json={},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_create_book_with_empty_title_returns_422(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="empty-title")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "", "pages": 100},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_create_book_with_whitespace_title_returns_422(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="ws-title")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "   ", "pages": 100},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_create_book_with_zero_pages_returns_422(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="zero-pages")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "Dune", "pages": 0},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


async def test_create_book_with_unknown_status_returns_422(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="bad-status")
    response = await client_with_csrf.post(
        "/v1/books",
        json={"title": "Dune", "pages": 100, "status": "archived"},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


# ---------------------------------------------------------------------------
# READ happy + isolation
# ---------------------------------------------------------------------------


async def test_read_book_returns_200_for_owned_id(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="read-sub")
    book = await _seed_book(session, sub="read-sub", title="Owned", pages=50)
    response = await client.get(
        f"/v1/books/{book.id}", cookies={"bff_session": sess.id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == book.id
    assert body["title"] == "Owned"
    assert "sub" not in body


async def test_read_book_returns_404_for_unknown_id(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="read-sub")
    response = await client.get("/v1/books/99999", cookies={"bff_session": sess.id})
    assert response.status_code == 404
    assert response.json() == {
        "errorCode": "book_not_found",
        "message": "Book not found",
        "detail": None,
    }


async def test_read_book_returns_404_for_other_users_book(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess_a = await _seed_session(session, sub="reader-A")
    await _seed_session(session, sub="reader-B")
    b_book = await _seed_book(session, sub="reader-B", title="B's book", pages=100)
    response = await client.get(
        f"/v1/books/{b_book.id}", cookies={"bff_session": sess_a.id}
    )
    # Cross-user existence MUST NOT be leaked — 404, not 403.
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"


async def test_read_book_with_non_integer_id_returns_422(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="path-sub")
    response = await client.get(
        "/v1/books/not-an-int", cookies={"bff_session": sess.id}
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"


# ---------------------------------------------------------------------------
# UPDATE happy + edge
# ---------------------------------------------------------------------------


async def test_update_book_partial_status_change_returns_200(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="upd-sub")
    book = await _seed_book(session, sub="upd-sub", title="Dune", pages=688)
    pre_updated_at = book.updated_at
    response = await client_with_csrf.patch(
        f"/v1/books/{book.id}",
        json={"status": "finished"},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finished"
    assert body["title"] == "Dune"
    assert body["pages"] == 688
    # updated_at advances. Parse the wire timestamp back into a datetime to
    # compare against the pre-patch value.
    post_updated_at = datetime.fromisoformat(body["updated_at"])
    if post_updated_at.tzinfo is None:
        post_updated_at = post_updated_at.replace(tzinfo=UTC)
    pre_aware = (
        pre_updated_at
        if pre_updated_at.tzinfo is not None
        else pre_updated_at.replace(tzinfo=UTC)
    )
    assert post_updated_at >= pre_aware


async def test_update_book_with_empty_body_returns_200_unchanged(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="empty-patch")
    book = await _seed_book(session, sub="empty-patch", title="Dune", pages=100)
    response = await client_with_csrf.patch(
        f"/v1/books/{book.id}",
        json={},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Dune"
    assert body["pages"] == 100
    assert body["status"] == "to-read"


async def test_update_book_with_zero_pages_returns_422_and_row_unchanged(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="upd-bad")
    book = await _seed_book(session, sub="upd-bad", title="Dune", pages=100)
    response = await client_with_csrf.patch(
        f"/v1/books/{book.id}",
        json={"pages": 0},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"
    # Re-fetch — DB row unchanged.
    await session.refresh(book)
    assert book.pages == 100


async def test_update_book_with_unknown_status_returns_422_and_row_unchanged(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="upd-bad-status")
    book = await _seed_book(session, sub="upd-bad-status", title="Dune", pages=100)
    response = await client_with_csrf.patch(
        f"/v1/books/{book.id}",
        json={"status": "archived"},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"
    await session.refresh(book)
    assert book.status == "to-read"


async def test_update_book_returns_404_for_unknown_id(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="upd-missing")
    response = await client_with_csrf.patch(
        "/v1/books/99999",
        json={"status": "reading"},
        cookies={"bff_session": sess.id},
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"


async def test_update_book_returns_404_for_other_users_book(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess_a = await _seed_session(session, sub="upd-A")
    await _seed_session(session, sub="upd-B")
    b_book = await _seed_book(session, sub="upd-B", title="B-original", pages=100)
    response = await client_with_csrf.patch(
        f"/v1/books/{b_book.id}",
        json={"title": "B-hijacked"},
        cookies={"bff_session": sess_a.id},
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"
    # Other user's row untouched.
    await session.refresh(b_book)
    assert b_book.title == "B-original"


# ---------------------------------------------------------------------------
# DELETE happy + edge
# ---------------------------------------------------------------------------


async def test_delete_book_returns_204_with_empty_body(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="del-sub")
    book = await _seed_book(session, sub="del-sub", title="Doomed", pages=10)
    book_id = book.id
    response = await client_with_csrf.delete(
        f"/v1/books/{book_id}", cookies={"bff_session": sess.id}
    )
    assert response.status_code == 204
    assert response.content == b""
    # Row is gone.
    found = (
        (
            await session.execute(
                select(entities.Book).where(entities.Book.id == book_id)
            )
        )
        .scalars()
        .first()
    )
    assert found is None


async def test_delete_book_returns_404_for_unknown_id(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess = await _seed_session(session, sub="del-missing")
    response = await client_with_csrf.delete(
        "/v1/books/99999", cookies={"bff_session": sess.id}
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"


async def test_delete_book_returns_404_for_other_users_book(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
) -> None:
    sess_a = await _seed_session(session, sub="del-A")
    await _seed_session(session, sub="del-B")
    b_book = await _seed_book(session, sub="del-B", title="B-keep", pages=10)
    response = await client_with_csrf.delete(
        f"/v1/books/{b_book.id}", cookies={"bff_session": sess_a.id}
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"
    # Other user's row still present.
    found = (
        (
            await session.execute(
                select(entities.Book).where(entities.Book.id == b_book.id)
            )
        )
        .scalars()
        .first()
    )
    assert found is not None
    assert found.title == "B-keep"


# ---------------------------------------------------------------------------
# Cross-user matrix (epic spec line 850)
# ---------------------------------------------------------------------------


async def test_two_distinct_sessions_cross_user_isolation(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    sess_a = await _seed_session(session, sub="matrix-A")
    sess_b = await _seed_session(session, sub="matrix-B")

    a_books = [
        await _seed_book(session, sub="matrix-A", title=f"A-{i}", pages=10 + i)
        for i in range(2)
    ]
    b_books = [
        await _seed_book(session, sub="matrix-B", title=f"B-{i}", pages=20 + i)
        for i in range(3)
    ]

    # Session A sees only A's two books.
    response = await client.get("/v1/books", cookies={"bff_session": sess_a.id})
    assert response.status_code == 200
    a_list = response.json()
    assert len(a_list) == 2
    assert {b["title"] for b in a_list} == {"A-0", "A-1"}

    # Session A → GET on B's id → 404.
    response = await client.get(
        f"/v1/books/{b_books[0].id}", cookies={"bff_session": sess_a.id}
    )
    assert response.status_code == 404

    # Session B sees only B's three books.
    response = await client.get("/v1/books", cookies={"bff_session": sess_b.id})
    assert response.status_code == 200
    b_list = response.json()
    assert len(b_list) == 3
    assert {b["title"] for b in b_list} == {"B-0", "B-1", "B-2"}

    # Session B → GET on A's id → 404.
    response = await client.get(
        f"/v1/books/{a_books[0].id}", cookies={"bff_session": sess_b.id}
    )
    assert response.status_code == 404

    # DB state unchanged: A still has 2, B still has 3.
    all_a = (
        (
            await session.execute(
                select(entities.Book).where(entities.Book.sub == "matrix-A")
            )
        )
        .scalars()
        .all()
    )
    all_b = (
        (
            await session.execute(
                select(entities.Book).where(entities.Book.sub == "matrix-B")
            )
        )
        .scalars()
        .all()
    )
    assert len(all_a) == 2
    assert len(all_b) == 3


# ===========================================================================
# Story 4.2 — POST /v1/books/{id}/estimate
# ===========================================================================
# Route-level coverage of the BFF→RS estimate proxy. Mirrors
# test_reading_speed_proxy.py's respx-based pattern.

_RS_BASE_URL = "http://rs.test"
_RS_ESTIMATE_URL = f"{_RS_BASE_URL}/v1/estimate"


@pytest.fixture
def rs_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the BFF's settings at the respx mock host (RS + Keycloak)."""
    monkeypatch.setattr(settings, "rs_base_url", _RS_BASE_URL)
    monkeypatch.setattr(settings, "oidc_issuer_url", "http://idp.test/realms/test")
    monkeypatch.setattr(settings, "oidc_client_id", "bmad-books-bff")
    monkeypatch.setattr(settings, "bff_client_secret", "test-secret")


async def _seed_session_row(
    db: AsyncSession,
    *,
    sub: str = "user-est-A",
    session_id: str = "sess-est-A",
    access_token: str = "initial-at",
    refresh_token: str = "initial-rt",
    expires_offset: int = 3600,
) -> SessionRow:
    """Insert a session row directly with deterministic access_token + id.

    The `_seed_session` helper above generates a random session id; this
    helper takes a fixed one so the cookie can be set in advance for the
    estimate tests that need to assert on the captured RS Authorization
    header.
    """
    row = SessionRow(
        id=session_id,
        sub=sub,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token="dummy-id-token",
        expires_at=(datetime.now(UTC) + timedelta(seconds=expires_offset)).replace(
            tzinfo=None
        ),
        csrf_secret="dummy-csrf-secret",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def test_estimate_happy_200_forwards_body(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-happy")
    book = await _seed_book(session, sub="est-happy", title="Dune", pages=688)
    client_with_csrf.cookies.set("bff_session", row.id)
    envelope = {"minutes": 1376, "formatted": "≈ 22 h 56 m"}
    with respx.mock() as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json=envelope)
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 200
    assert response.json() == envelope
    assert rs_route.call_count == 1


async def test_estimate_missing_book_id_returns_404_no_rs_call(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-miss")
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post("/v1/books/9999/estimate")
    assert response.status_code == 404
    assert response.json() == {
        "errorCode": "book_not_found",
        "message": "Book not found",
        "detail": None,
    }
    assert rs_route.call_count == 0  # RS never called.


async def test_estimate_cross_user_book_returns_404_no_rs_call(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """User A posts to user B's book id → 404 + no RS fanout (AC3 + NFR6)."""
    sess_a = await _seed_session_row(session, sub="est-A", session_id="sess-A")
    b_book = await _seed_book(session, sub="est-B", title="B-book", pages=100)
    client_with_csrf.cookies.set("bff_session", sess_a.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post(f"/v1/books/{b_book.id}/estimate")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "book_not_found"
    assert rs_route.call_count == 0


async def test_estimate_no_session_cookie_returns_401_no_clear(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    # Note: client_with_csrf carries the csrf header/cookie; we just don't set
    # `bff_session` so the session-resolution path 401s before any RS call.
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post("/v1/books/1/estimate")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    assert rs_route.call_count == 0
    # No clearing Set-Cookie on the missing-cookie path. (AC11.)
    set_cookie = response.headers.get_list("set-cookie")
    assert all("max-age=0" not in c.lower() for c in set_cookie)


async def test_estimate_unknown_session_id_returns_401(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    client_with_csrf.cookies.set("bff_session", "nonexistent-session-id")
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post("/v1/books/1/estimate")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    assert rs_route.call_count == 0


async def test_estimate_expired_session_returns_401_and_deletes_row(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(
        session, sub="est-exp", session_id="sess-exp", expires_offset=-60
    )
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post("/v1/books/1/estimate")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    # AC11 invariant: expired-session 401 short-circuits BEFORE any RS call.
    assert rs_route.call_count == 0
    # Expired row was lazy-deleted.
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is None


async def test_estimate_without_csrf_returns_403(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """No CSRF header → 403 csrf_invalid at the middleware before the handler."""
    row = await _seed_session_row(session, sub="est-csrf")
    book = await _seed_book(session, sub="est-csrf", title="x", pages=10)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client.post(
            f"/v1/books/{book.id}/estimate", cookies={"bff_session": row.id}
        )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"
    assert rs_route.call_count == 0


async def test_estimate_rs_412_forwarded(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-412")
    book = await _seed_book(session, sub="est-412", title="x", pages=200)
    client_with_csrf.cookies.set("bff_session", row.id)
    envelope = {
        "errorCode": "reading_speed_unset",
        "message": "Reading speed not set for this user",
        "detail": None,
    }
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(412, json=envelope)
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 412
    assert response.json() == envelope


async def test_estimate_rs_403_forwarded(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-403")
    book = await _seed_book(session, sub="est-403", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    envelope = {
        "errorCode": "forbidden_scope",
        "message": "Required scope is missing",
        "detail": None,
    }
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(403, json=envelope)
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 403
    assert response.json() == envelope


async def test_estimate_rs_422_forwarded(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-422")
    book = await _seed_book(session, sub="est-422", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    envelope = {
        "errorCode": "invalid_input",
        "message": "Request validation failed",
        "detail": [{"loc": ["body", "pages"], "msg": "ge", "type": "value_error"}],
    }
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(422, json=envelope)
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 422
    assert response.json() == envelope


@pytest.mark.parametrize("rs_status", [500, 503])
async def test_estimate_rs_5xx_returns_503(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    rs_status: int,
) -> None:
    row = await _seed_session_row(session, sub=f"est-{rs_status}")
    book = await _seed_book(session, sub=f"est-{rs_status}", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock() as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(rs_status)
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 503
    assert response.json() == {
        "errorCode": "resource_server_unavailable",
        "message": "The resource server is temporarily unavailable",
        "detail": None,
    }
    assert rs_route.call_count == 1  # No retry on 5xx.


async def test_estimate_rs_connect_error_returns_503(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-conn")
    book = await _seed_book(session, sub="est-conn", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock() as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            side_effect=httpx.ConnectError("refused")
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1


async def test_estimate_rs_read_timeout_returns_503(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-rt")
    book = await _seed_book(session, sub="est-rt", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"


async def test_estimate_refresh_failure_clears_cookies_and_returns_401(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-refresh-fail")
    book = await _seed_book(session, sub="est-refresh-fail", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(return_value=httpx.Response(401))
        mock.post("http://idp.test/realms/test/protocol/openid-connect/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) == 2
    lowered = [c.lower() for c in set_cookie_headers]
    assert any("bff_session=" in c for c in lowered)
    assert any("csrf_token=" in c for c in lowered)
    # Per-cookie max-age=0: a regression that clears only one of the two
    # cookies would slip past a joined-string check.
    for cookie in lowered:
        assert "max-age=0" in cookie
    # Session row was deleted by ResourceServerClient.
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is None


async def test_estimate_refresh_replay_happy_forwards_200(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-replay")
    book = await _seed_book(session, sub="est-replay", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    rs_call_seq: list[int] = []

    def _rs(request: httpx.Request) -> httpx.Response:
        rs_call_seq.append(1)
        token = request.headers.get("authorization", "")
        if token == "Bearer initial-at":
            return httpx.Response(401)
        return httpx.Response(200, json={"minutes": 100, "formatted": "≈ 1 h 40 m"})

    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(side_effect=_rs)
        mock.post("http://idp.test/realms/test/protocol/openid-connect/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 200
    assert response.json() == {"minutes": 100, "formatted": "≈ 1 h 40 m"}
    assert len(rs_call_seq) == 2
    await session.refresh(row)
    assert row.access_token == "new-at"


async def test_estimate_refresh_worked_retry_401_no_cookie_clear(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-retry401")
    book = await _seed_book(session, sub="est-retry401", title="x", pages=50)
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(return_value=httpx.Response(401))
        mock.post("http://idp.test/realms/test/protocol/openid-connect/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    # No Set-Cookie clearing — refresh worked, retry just 401'd.
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert set_cookie_headers == []
    # Row still present (rotated tokens, but not deleted).
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is not None


async def test_estimate_nfr6_captured_rs_request_shape(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    sub = "est-nfr6"
    row = await _seed_session_row(session, sub=sub, access_token="bearer-nfr6")
    book = await _seed_book(session, sub=sub, title="x", pages=688)
    client_with_csrf.cookies.set("bff_session", row.id)
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"minutes": 1376, "formatted": "≈ 22 h 56 m"})

    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(side_effect=_capture)
        await client_with_csrf.post(f"/v1/books/{book.id}/estimate")

    assert len(captured) == 1
    request = captured[0]
    assert request.url.path == "/v1/estimate"
    assert request.url.params == httpx.QueryParams()
    import json as _json

    body = _json.loads(request.content)
    assert body == {"pages": 688}
    # NFR6: sub MUST NOT leak via any header value either (e.g. a stray
    # `X-User-Sub` or sub embedded into an existing header). The body
    # equality above already pins "sub not in body".
    assert not any(sub in v for v in request.headers.values())
    assert request.headers["authorization"] == "Bearer bearer-nfr6"


async def test_estimate_uses_owner_pages_not_other_users(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """Two users with their own books — A's POST sends A's pages, not B's."""
    sess_a = await _seed_session_row(session, sub="est-iso-A", session_id="sess-iso-A")
    a_book = await _seed_book(session, sub="est-iso-A", title="A", pages=111)
    await _seed_book(session, sub="est-iso-B", title="B", pages=999)
    client_with_csrf.cookies.set("bff_session", sess_a.id)
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"minutes": 1, "formatted": "x"})

    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(side_effect=_capture)
        await client_with_csrf.post(f"/v1/books/{a_book.id}/estimate")
    import json as _json

    body = _json.loads(captured[0].content)
    assert body == {"pages": 111}


async def test_estimate_non_integer_book_id_returns_422(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session_row(session, sub="est-path")
    client_with_csrf.cookies.set("bff_session", row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.post(_RS_ESTIMATE_URL).mock(
            return_value=httpx.Response(200, json={"minutes": 1, "formatted": "x"})
        )
        response = await client_with_csrf.post("/v1/books/not-an-int/estimate")
    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_input"
    assert rs_route.call_count == 0


async def test_estimate_ignores_request_body(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """The handler does not consume a request body — `pages` is read from
    the seeded book row, not the request. A POST with `{}` succeeds with the
    book's stored pages forwarded to the RS.
    """
    row = await _seed_session_row(session, sub="est-body")
    book = await _seed_book(session, sub="est-body", title="x", pages=200)
    client_with_csrf.cookies.set("bff_session", row.id)
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"minutes": 400, "formatted": "≈ 6 h 40 m"})

    with respx.mock() as mock:
        mock.post(_RS_ESTIMATE_URL).mock(side_effect=_capture)
        response = await client_with_csrf.post(f"/v1/books/{book.id}/estimate", json={})
    assert response.status_code == 200
    import json as _json

    body = _json.loads(captured[0].content)
    assert body == {"pages": 200}  # book.pages, not the request body.


async def test_estimate_openapi_path_listed(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/v1/books/{book_id}/estimate" in paths
    assert "post" in paths["/v1/books/{book_id}/estimate"]
