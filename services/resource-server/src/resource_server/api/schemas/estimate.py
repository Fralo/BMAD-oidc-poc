"""API DTOs for ``POST /v1/estimate``.

Distinct from any SQLModel ORM class per architecture §C7 line 418 — keeps
internal columns out of responses by construction and lets Pydantic enforce
the ``ge=1`` invariant at the request boundary.

``EstimateIn`` mirrors ``ReadingSpeedUpsert``'s defenses (Story 3.3): the
``extra="forbid"`` config rejects body-level ``sub`` injection attempts at
the boundary as 422 ``invalid_input`` rather than silently dropping unknown
fields. Identity is always read from the JWT ``sub`` claim, never from the
request body.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EstimateIn(BaseModel):
    """Request body for ``POST /v1/estimate`` — Pydantic enforces ``ge=1``.

    Non-positive values yield 422 ``invalid_input`` before reaching the
    handler; the service layer never sees them.

    ``extra="forbid"`` rejects unknown fields so a client posting
    ``{"pages": 600, "sub": "victim"}`` is surfaced as 422 ``invalid_input``
    (with an ``extra_forbidden`` entry in ``detail``) rather than silently
    dropping the unknown ``sub`` field — identity is always read from
    ``principal.subject`` (JWT claim), never from the request body.
    """

    model_config = ConfigDict(extra="forbid")

    pages: int = Field(ge=1)


class EstimateOut(BaseModel):
    """Response body for ``POST /v1/estimate``.

    Two fields side by side per architecture §"Format Patterns" line 696:
    ``minutes`` (integer, for tests + numeric assertions) and ``formatted``
    (UX-DR18 string the SPA renders verbatim).
    """

    minutes: int
    formatted: str
