FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --locked --no-install-project --no-dev --no-editable

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14-slim

RUN groupadd --system app && useradd --system --gid app app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=1

USER app
EXPOSE 8000

CMD ["sh", "-c", "uvicorn resource_server.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
