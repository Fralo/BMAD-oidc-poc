"""Pydantic boundary models for the BFF v1 API.

Boundary models live here (separate from `bff.models.entities`, which
owns the persistence schemas) so the wire-format contract stays
explicit and can diverge from the DB schema without leaking internal
columns (architecture §C7). Re-exports for ergonomics: handlers import
from `bff.api.schemas`, not from the submodule directly.
"""

from bff.api.schemas.book import BookCreate, BookOut, BookUpdate

__all__ = ["BookCreate", "BookOut", "BookUpdate"]
