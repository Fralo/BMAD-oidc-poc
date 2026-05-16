"""Resource Server SQLModel entity declarations.

Importing this package triggers SQLModel.metadata registration for every
entity below — that's what makes them visible to Alembic autogenerate
(`alembic/env.py` does `from resource_server.models import entities`) and to
test fixtures' `SQLModel.metadata.create_all` calls.

Story 3.1 ships zero entities. Story 3.3 introduces ReadingSpeed.
"""

__all__: list[str] = []
