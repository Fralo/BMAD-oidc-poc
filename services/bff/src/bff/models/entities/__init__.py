"""BFF SQLModel entity declarations.

Importing this package triggers SQLModel.metadata registration for every
entity below — that's what makes them visible to Alembic autogenerate
(`alembic/env.py` does `from bff.models import entities`) and to the
test conftest's `SQLModel.metadata.create_all` call.
"""

from bff.models.entities.auth_state import AuthState
from bff.models.entities.book import Book
from bff.models.entities.session import Session

__all__ = ["AuthState", "Book", "Session"]
