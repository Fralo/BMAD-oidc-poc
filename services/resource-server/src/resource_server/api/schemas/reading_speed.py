"""API DTOs for /v1/reading-speed.

Distinct from the ``ReadingSpeed`` SQLModel per architecture §C7 line 418 —
keeps internal columns (``created_at``, ``updated_at``, ``sub``) out of
responses by construction and lets Pydantic enforce the ``ge=1`` invariant
at the request boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReadingSpeedOut(BaseModel):
    """Response body for GET and PUT — exposes only ``pages_per_hour``."""

    pages_per_hour: int


class ReadingSpeedUpsert(BaseModel):
    """Request body for PUT — Pydantic enforces ``ge=1`` at the boundary.

    Non-positive values yield 422 ``invalid_input`` before reaching the
    handler; the service / DB layer never sees them.
    """

    pages_per_hour: int = Field(ge=1)
