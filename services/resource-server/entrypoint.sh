#!/bin/sh
# Resource Server container entrypoint.
#
# 1) Runs Alembic to head so the database schema is up-to-date BEFORE
#    uvicorn starts. Per architecture §"Operational Details / Migrations on
#    startup": the container's "ready" state must coincide with "schema at
#    head", which the /health probe then reports.
# 2) `exec` replaces the shell process with uvicorn so signal handling
#    (SIGTERM from docker stop) reaches the application correctly.
#
# Story 3.1 ships zero migrations; `alembic upgrade head` on an empty
# versions/ directory is a no-op that exits 0. Story 3.3 lands the first
# migration (ReadingSpeed) and this step becomes load-bearing.

set -e

alembic upgrade head

exec uvicorn resource_server.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
