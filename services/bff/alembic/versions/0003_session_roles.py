"""add roles column to sessions

Revision ID: 0003_session_roles
Revises: 0002_add_books
Create Date: 2026-05-21 14:45:00.000000

Story 7.1: persist in-app roles mapped from the OIDC `groups` claim at
/auth/callback time. The column is NOT NULL with `server_default=sa.text("''")`
so that existing session rows (created before this migration ran) satisfy
the constraint without requiring a row-level backfill. The `sa.text("''")`
form is required — a bare `server_default=""` generates an empty SQL
expression (`DEFAULT` with no value) which fails on non-empty tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_session_roles"
down_revision: str | Sequence[str] | None = "0002_add_books"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sessions",
        sa.Column(
            "roles",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sessions", "roles")
