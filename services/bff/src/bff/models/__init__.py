# Story 1.4 lands the first SQLModel entities (sessions, auth_states) under
# `bff.models.entities`; Story 2.1 adds `books`. This empty package exists
# now so `alembic/env.py` can do `from bff.models import entities` without
# crashing — see Story 1.3 Review Findings (Patch P1).
