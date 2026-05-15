"""SQLModel for the BFF's `sessions` table.

A `sessions` row holds the server-side state for an authenticated browser
session: the user's OIDC subject claim and the access/refresh/id-token
bundle the BFF presents to Keycloak / the Resource Server on the browser's
behalf, plus the per-session `csrf_secret` used by the double-submit CSRF
middleware (Story 1.6). The row id is the opaque value placed in the
HttpOnly session cookie; Story 1.5's OIDC plugin generates it via
``secrets.token_urlsafe(32)`` (256 bits of entropy).

Plaintext token storage is the documented accepted risk for this
educational reference (architecture §Operational Details).
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(primary_key=True)
    sub: str = Field(max_length=255, index=True, nullable=False)
    # `repr=False` keeps cryptographic material out of __repr__ / debug logs.
    access_token: str = Field(nullable=False, repr=False)
    refresh_token: str = Field(nullable=False, repr=False)
    id_token: str = Field(nullable=False, repr=False)
    expires_at: datetime = Field(index=True, nullable=False)
    csrf_secret: str = Field(nullable=False, repr=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
