"""SQLModel for the BFF's `auth_states` table.

An `auth_states` row is the server-side persistence of an in-flight
Authorization Code + PKCE round-trip: the `code_verifier`, OAuth `state`
parameter, OIDC `nonce`, and post-login `return_to` path. The row id is
the opaque value referenced by the short-lived state-id cookie (Story
1.5). Rows are created at ``/auth/login`` and deleted at
``/auth/callback`` (or pruned by `expires_at` when the user abandons the
flow).

No ``updated_at`` column — these rows are one-shot, never updated.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AuthState(SQLModel, table=True):
    __tablename__ = "auth_states"

    id: str = Field(primary_key=True)
    code_verifier: str = Field(nullable=False)
    state: str = Field(nullable=False)
    nonce: str = Field(nullable=False)
    return_to: str | None = Field(default=None, nullable=True)
    expires_at: datetime = Field(index=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
