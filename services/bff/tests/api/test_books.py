"""Route-level tests for /v1/books CRUD (Story 2.2).

Covers session auth, CSRF, cross-user isolation, validation, and the
five verbs (LIST, CREATE, READ, UPDATE, DELETE). Service-layer
behavior is exercised separately in tests/services/test_books_service.py.

The `_seed_session` helper is duplicated from tests/api/test_me.py per
the project's "small redundancy over abstraction" stance — keeping
test files self-contained outweighs the 30-line copy.
"""

from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.models import entities
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
