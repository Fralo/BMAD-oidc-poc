"""API DTOs for /v1/reading-speed.

Distinct from the ``ReadingSpeed`` SQLModel per architecture §C7 line 418 —
keeps internal columns (``created_at``, ``updated_at``, ``sub``) out of
responses by construction and lets Pydantic enforce the ``ge=1`` invariant
at the request boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReadingSpeedOut(BaseModel):
    """Response body for GET and PUT — exposes only ``pages_per_hour``."""

    pages_per_hour: int


class ReadingSpeedUpsert(BaseModel):
    """Request body for PUT — Pydantic enforces ``ge=1`` at the boundary.

    Non-positive values yield 422 ``invalid_input`` before reaching the
    handler; the service / DB layer never sees them.

    ``extra="forbid"`` rejects unknown fields so a client posting
    ``{"pages_per_hour": 30, "sub": "victim"}`` is surfaced as 422
    ``invalid_input`` rather than silently dropping the unknown ``sub``
    field (cf. architecture's "JSON snake_case in both directions" + the
    boundary-discipline norm). Identity is always read from
    ``principal.subject`` (JWT claim), never from the request body.
    """

    model_config = ConfigDict(extra="forbid")

    pages_per_hour: int = Field(ge=1)
