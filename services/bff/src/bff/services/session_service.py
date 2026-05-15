"""Owns the lifecycle of `auth_states` and `sessions` rows for the BFF's
cookie-session OIDC plugin (Story 1.5).

Single source of truth for opaque-id generation: every `auth_states.id`,
`sessions.id`, `state`, `nonce`, and `csrf_secret` is minted here via
`secrets.token_urlsafe(_OPAQUE_ID_BYTES)` (256 bits of entropy). Centralizing
the generator prevents call-site drift; consumers (the auth router) call
service methods and never reach for `secrets` themselves.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as _delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.auth import pkce
from bff.auth.keycloak_cookie_session import safe_return_to
from bff.models import entities

logger = logging.getLogger(__name__)

# 32 random bytes → 43-char URL-safe string ≈ 256 bits of entropy. Same
# generator contract Story 1.4 documented for `Session.id` / `AuthState.id`.
_OPAQUE_ID_BYTES = 32

# RFC 7636 PKCE flow allows ≤10 min for the auth-state TTL; the architecture
# spec (A3) pins 5 min explicitly. Short window narrows replay surface.
_AUTH_STATE_TTL = timedelta(minutes=5)

# Story 1.4 D40 resolution: state/nonce uniqueness is NOT enforced at the DB
# layer (256-bit entropy makes collisions astronomically unlikely). PK
# collisions on `id` are the only `IntegrityError` source possible; retry a
# few times before giving up.
_INSERT_RETRY_LIMIT = 3


def _new_opaque_id() -> str:
    return secrets.token_urlsafe(_OPAQUE_ID_BYTES)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _as_utc_aware(dt: datetime) -> datetime:
    """Normalize a possibly-naive DB roundtripped datetime to tz-aware UTC.

    SQLite (via `sa.DateTime()` per the 0001_init migration) strips tzinfo on
    storage — Story 1.4's D31 caveat. Comparisons between a naive roundtrip
    and a tz-aware `datetime.now(UTC)` would raise. Reattach UTC when missing.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SessionService:
    """Lifecycle owner for `auth_states` and `sessions` rows."""

    async def create_auth_state(
        self,
        db: AsyncSession,
        *,
        return_to: str | None,
    ) -> tuple[entities.AuthState, str]:
        """Persist a fresh `auth_states` row and return it alongside the
        `code_verifier` the caller will derive the PKCE challenge from.

        Retries up to `_INSERT_RETRY_LIMIT` times on PK `IntegrityError`
        (D40 collision retry; vanishingly unlikely at 256-bit entropy).
        """
        normalized_return_to = safe_return_to(return_to)
        last_exc: IntegrityError | None = None
        for attempt in range(_INSERT_RETRY_LIMIT):
            code_verifier = pkce.generate_code_verifier()
            row = entities.AuthState(
                id=_new_opaque_id(),
                code_verifier=code_verifier,
                state=_new_opaque_id(),
                nonce=_new_opaque_id(),
                return_to=normalized_return_to,
                expires_at=_now_utc() + _AUTH_STATE_TTL,
            )
            db.add(row)
            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                last_exc = exc
                logger.info(
                    "auth_state_insert_retry attempt=%d/%d",
                    attempt + 1,
                    _INSERT_RETRY_LIMIT,
                )
                continue
            await db.refresh(row)
            return row, code_verifier
        # Unreachable in practice (256-bit collision); fail loud if it ever fires.
        raise RuntimeError(
            f"auth_state insert collided {_INSERT_RETRY_LIMIT}x — entropy failure?"
        ) from last_exc

    async def consume_auth_state(
        self,
        db: AsyncSession,
        *,
        state: str,
    ) -> entities.AuthState | None:
        """Return the row matching `state`, deleting it as a side effect.

        Expired rows are deleted in the same call and `None` is returned;
        missing rows return `None` without DB writes. Caller cross-checks
        the row's id against the state-id cookie separately.
        """
        result = await db.execute(
            select(entities.AuthState).where(entities.AuthState.state == state)
        )
        row = result.scalars().first()
        if row is None:
            return None
        if _as_utc_aware(row.expires_at) < _now_utc():
            await db.delete(row)
            await db.commit()
            return None
        # Caller will compare row.id to the state-id cookie before trusting it.
        # We delete the row immediately so a replay can't succeed even if the
        # caller's later checks (cookie HMAC, PKCE exchange) fail and return.
        await db.delete(row)
        await db.commit()
        return row

    async def create_session(
        self,
        db: AsyncSession,
        *,
        sub: str,
        access_token: str,
        refresh_token: str,
        id_token: str,
        expires_at: datetime,
    ) -> entities.Session:
        """Persist a fresh `sessions` row. Retries on `IntegrityError` (PK)."""
        last_exc: IntegrityError | None = None
        for attempt in range(_INSERT_RETRY_LIMIT):
            row = entities.Session(
                id=_new_opaque_id(),
                sub=sub,
                access_token=access_token,
                refresh_token=refresh_token,
                id_token=id_token,
                expires_at=expires_at,
                csrf_secret=_new_opaque_id(),
            )
            db.add(row)
            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                last_exc = exc
                logger.info(
                    "session_insert_retry attempt=%d/%d",
                    attempt + 1,
                    _INSERT_RETRY_LIMIT,
                )
                continue
            await db.refresh(row)
            logger.info("session_created sub=%s id=%s...", sub, row.id[:8])
            return row
        raise RuntimeError(
            f"session insert collided {_INSERT_RETRY_LIMIT}x — entropy failure?"
        ) from last_exc

    async def get_session(
        self,
        db: AsyncSession,
        *,
        session_id: str,
    ) -> entities.Session | None:
        """Fetch a `sessions` row by id; caller validates `expires_at`.

        D32 caveat: bulk `update(Session).values(...)` paths skip the
        `updated_at` `onupdate` lambda. This story's call sites are
        point-mutations and DO trigger it; future bulk-rotation code (Story
        1.7) must set `updated_at` explicitly.
        """
        result = await db.execute(
            select(entities.Session).where(entities.Session.id == session_id)
        )
        return result.scalars().first()

    async def delete_expired_session(
        self,
        db: AsyncSession,
        *,
        session_id: str,
    ) -> None:
        """Single indexed DELETE WHERE id=:id AND expires_at < now."""
        # D31: SQLite stores datetimes as naive strings; strip tzinfo for the SQL
        # comparison.  synchronize_session=False skips the ORM in-memory evaluator
        # (which would raise on tz-aware vs naive) — safe because we commit next.
        now = _now_utc().replace(tzinfo=None)
        await db.execute(
            _delete(entities.Session)
            .where(entities.Session.id == session_id)  # type: ignore[arg-type]
            .where(entities.Session.expires_at < now),  # type: ignore[arg-type]
            execution_options={"synchronize_session": False},
        )
        await db.commit()
