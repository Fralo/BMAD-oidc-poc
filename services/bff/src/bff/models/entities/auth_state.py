"""SQLModel for the BFF's `auth_states` table.

An `auth_states` row is the server-side persistence of an in-flight
Authorization Code round-trip: the OAuth `state` parameter, OIDC `nonce`,
and post-login `return_to` path. The row id is the opaque value
referenced by the short-lived state-id cookie (Story 1.5). Rows are
created at ``/auth/login`` and deleted at ``/auth/callback`` (or pruned
by `expires_at` when the user abandons the flow).

No ``updated_at`` column — these rows are one-shot, never updated.

PKCE was removed from this flow on 2026-05-21 (see Pattern Amendments in
architecture.md). The `code_verifier` column remains in the schema as
nullable dead storage for backwards compatibility with the 0001_init
migration; it is no longer read or written and defaults to "".
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AuthState(SQLModel, table=True):
    __tablename__ = "auth_states"

    id: str = Field(primary_key=True)
    # Vestigial column kept for backwards-compat with the 0001_init schema.
    # No longer read or written; default-"" satisfies the NOT NULL constraint
    # without a follow-up migration. See Pattern Amendments in architecture.md.
    code_verifier: str = Field(default="", nullable=False)
    state: str = Field(nullable=False)
    nonce: str = Field(nullable=False)
    return_to: str | None = Field(default=None, nullable=True)
    expires_at: datetime = Field(index=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
