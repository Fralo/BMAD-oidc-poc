"""Five-verb books CRUD surface mounted under `/v1/books` (Story 2.2).

Handlers:

* `GET    /v1/books`         → 200 + JSON array
* `POST   /v1/books`         → 201 + `Location: /v1/books/{id}`
* `GET    /v1/books/{id}`    → 200 | 404
* `PATCH  /v1/books/{id}`    → 200 | 404 | 422
* `DELETE /v1/books/{id}`    → 204 (empty body)

Every handler resolves `sub` from the session cookie BEFORE doing any
work (see `_resolve_session_sub`). The session-resolution + lazy-cleanup
pattern is duplicated from `api/me.py` rather than imported — the
project tolerates a third inline copy until a fourth consumer arrives
(see story 2.2 Dev Notes "Session extraction" for the deferred refactor).

Cross-user isolation: every BooksService method embeds the `sub`
predicate in SQL, so a 404 covers both "id does not exist" and "id
exists but is owned by someone else" — existence is not leaked across
users (architecture line 685 + epic spec lines 819–821).

The router's prefix is `/books`; the parent `v1_router` adds the `/v1`
segment. Final mount paths therefore are `/v1/books` and
`/v1/books/{book_id}`. The `Location` header value in `create_book`
still uses the public URL (`/v1/books/{id}`), independent of the
internal mount path.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bff.api.schemas.book import BookCreate, BookOut, BookUpdate
from bff.auth.oidc_discovery import OidcDiscovery, get_oidc_discovery
from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import AppException, ErrorCode
from bff.models.entities.session import Session as SessionRow
from bff.services.books_service import BooksService
from bff.services.resource_server_client import (
    RsSessionTerminated,
    RsUnavailable,
    resource_server_client,
)
from bff.services.session_service import SessionService

router = APIRouter(prefix="/books", tags=["Books"])

_session_service = SessionService()
_books_service = BooksService()

__all__ = ["router"]


def _settings_dep() -> AppSettings:
    return settings


def _as_utc_aware(dt: datetime) -> datetime:
    """Reattach UTC tzinfo on a possibly-naive datetime read back from SQLite.

    Duplicated (3 lines) from `api/me.py:47` deliberately — importing from
    `me.py` would introduce a circular-import risk and the helper is cheap.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _resolve_session_sub(
    request: Request,
    db: AsyncSession,
    cfg: AppSettings,
) -> str:
    """Return `sub` for a valid session cookie.

    Raises `AppException(ErrorCode.SESSION_EXPIRED)` if the cookie is
    missing, the session id is unknown, or the session has expired.
    Expired sessions are lazy-deleted as a side effect (mirrors
    `api/me.py:67`). Going through `AppException` rather than returning
    a `JSONResponse` directly lets each handler keep its declared
    `response_model` annotation intact.
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        await _session_service.delete_expired_session(db, session_id=session_id)
        raise AppException(ErrorCode.SESSION_EXPIRED)
    return row.sub


async def _resolve_session_row(
    request: Request,
    db: AsyncSession,
    cfg: AppSettings,
) -> SessionRow:
    """Return the full session row for a valid session cookie.

    Parallel helper to `_resolve_session_sub` — the estimate handler
    (Story 4.2) needs `row.access_token` to forward to the RS, so the
    sub-only return wouldn't suffice. The three 401 failure modes are
    identical: missing cookie / unknown id / expired row each map to
    `AppException(ErrorCode.SESSION_EXPIRED)` (expired rows are lazy-
    deleted). The architectural consolidation of `_resolve_session_sub`
    onto this helper is deferred until a fourth consumer arrives
    (Story 3.5 Dev Notes precedent).
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        await _session_service.delete_expired_session(db, session_id=session_id)
        raise AppException(ErrorCode.SESSION_EXPIRED)
    return row


# Inlined from api/reading_speed.py per Story 4.2 — extract to a shared
# module after a fourth consumer arrives (reading_speed.py + books.py are
# consumers two/three; the duplication is the conservative play to avoid
# the import-coupling the reading_speed.py docstring flagged).
def _session_terminated_response(
    cfg: AppSettings, *, clear_cookies: bool
) -> JSONResponse:
    """Emit a 401 ``session_expired`` response, optionally with cookies cleared.

    ``clear_cookies=True`` is the refresh-failure path: the sessions row
    has already been deleted by ``ResourceServerClient``; the response
    clears both the session cookie and ``csrf_token`` cookie via
    ``Max-Age=0`` so the browser drops them. ``clear_cookies=False`` is
    the refresh-worked-but-retry-still-401 path: the session stays in
    place; the SPA's redirect to ``/login`` will produce a fresh login.
    """
    response = JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )
    if clear_cookies:
        # Import lazily to avoid a circular import between api.auth and
        # api.books (both are pulled in by api/v1/__init__.py).
        from bff.api.auth import _clear_session_cookies

        _clear_session_cookies(response, cfg)
    return response


def _resource_server_unavailable_response() -> JSONResponse:
    """Emit the project-standard 503 ``resource_server_unavailable`` envelope."""
    return JSONResponse(
        status_code=ErrorCode.RESOURCE_SERVER_UNAVAILABLE.http_status,
        content={
            "errorCode": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.code,
            "message": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.message,
            "detail": None,
        },
    )


@router.get("", response_model=list[BookOut])
async def list_books(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> list[BookOut]:
    sub = await _resolve_session_sub(request, db, cfg)
    rows = await _books_service.list_for_user(db, sub=sub)
    return [BookOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=BookOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_book(
    request: Request,
    response: Response,
    payload: BookCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> BookOut:
    sub = await _resolve_session_sub(request, db, cfg)
    book = await _books_service.create(db, sub=sub, payload=payload)
    # Location header uses the public URL, NOT the internal mount path.
    response.headers["Location"] = f"/v1/books/{book.id}"
    return BookOut.model_validate(book)


@router.get("/{book_id}", response_model=BookOut)
async def read_book(
    request: Request,
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> BookOut:
    sub = await _resolve_session_sub(request, db, cfg)
    book = await _books_service.get_for_user(db, sub=sub, book_id=book_id)
    if book is None:
        raise AppException(ErrorCode.BOOK_NOT_FOUND)
    return BookOut.model_validate(book)


@router.patch("/{book_id}", response_model=BookOut)
async def update_book(
    request: Request,
    book_id: int,
    payload: BookUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> BookOut:
    sub = await _resolve_session_sub(request, db, cfg)
    book = await _books_service.update(db, sub=sub, book_id=book_id, payload=payload)
    if book is None:
        raise AppException(ErrorCode.BOOK_NOT_FOUND)
    return BookOut.model_validate(book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    request: Request,
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> Response:
    sub = await _resolve_session_sub(request, db, cfg)
    deleted = await _books_service.delete(db, sub=sub, book_id=book_id)
    if not deleted:
        raise AppException(ErrorCode.BOOK_NOT_FOUND)
    # Explicit empty Response per Story 1.12 idiom — `return None` would
    # emit a JSON `null` body; `JSONResponse({})` would emit `{}`. The
    # 204 contract requires zero bytes.
    return Response(status_code=204)


@router.post("/{book_id}/estimate")
async def estimate_for_book(
    request: Request,
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
    discovery: Annotated[OidcDiscovery, Depends(get_oidc_discovery)],
) -> JSONResponse:
    """Broker a reading-time estimate for the user's book against the RS.

    Story 4.2. Order of operations:
      1. Resolve session row (401 on missing/unknown/expired).
      2. Look up the book by `(sub, id)` BEFORE any RS call — cross-user
         and missing both collapse to 404 ``book_not_found``, and the RS
         is never called in that path (existence-leak guard + no fanout).
      3. Forward ``book.pages`` (from the row owned by the session sub —
         the request body is intentionally ignored) to ``compute_estimate``.
         The RS body is then forwarded verbatim (200 / 412 / 403 / 422).
      4. ``RsUnavailable`` → 503 ``resource_server_unavailable``;
         ``RsSessionTerminated`` → 401 with cookies optionally cleared.
    """
    session_row = await _resolve_session_row(request, db, cfg)

    book = await _books_service.get_for_user(db, sub=session_row.sub, book_id=book_id)
    if book is None:
        raise AppException(ErrorCode.BOOK_NOT_FOUND)

    try:
        rs_status, body = await resource_server_client.compute_estimate(
            db, session_row, pages=book.pages, token_url=discovery.token_endpoint
        )
    except RsSessionTerminated as exc:
        return _session_terminated_response(cfg, clear_cookies=exc.clear_cookies)
    except RsUnavailable:
        # WARN log already emitted inside ResourceServerClient.
        return _resource_server_unavailable_response()

    return JSONResponse(status_code=rs_status, content=body)
