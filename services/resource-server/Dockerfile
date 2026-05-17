# ── Stage 0: Python dependency builder ─────────────────────────────────────
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Build context is the repo root (compose/app.yml sets context: ..) for
# consistency with the BFF post-1.14 posture (closes D4 for the RS). All
# bind-mount paths below are relative to the repo root.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=services/resource-server/uv.lock,target=uv.lock \
    --mount=type=bind,source=services/resource-server/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=services/resource-server/.python-version,target=.python-version \
    uv sync --locked --no-install-project --no-dev --no-editable

COPY services/resource-server/ /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ── Stage 1: Final runtime image ───────────────────────────────────────────
FROM python:3.14-slim

# /data is the mount point for the rs_data named volume (architecture §I5 /
# AR6). Create it with app ownership so SQLite can write its file there
# regardless of host UID mapping. Mirrors the BFF Dockerfile.
RUN groupadd --system app && useradd --system --gid app app \
    && mkdir -p /data && chown app:app /data

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Story 3.1: the RS is JSON-API-only — no SPA bundle, no Node builder
# stage. Unlike the BFF (Story 1.14), this image is Python-only,
# single-language, multi-stage on python:3.14-slim only.

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=1

USER app
EXPOSE 8000

# HEALTHCHECK uses the stdlib (no curl in python:3.14-slim) so we don't pull
# in an extra package layer just for a probe. The compose-level healthcheck
# (compose/app.yml) overrides this at runtime, but the image-level one keeps
# `docker run` standalone-usable and informative.
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=15s \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)" \
    || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
