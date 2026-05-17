"""Request/response DTOs for the Resource Server's `/v1/*` API.

Distinct from the SQLModel ORM classes under ``resource_server.models.entities``
per architecture §C7 line 418 — keeps internal columns (``created_at``,
``updated_at``, ``sub``) out of responses by construction.
"""
