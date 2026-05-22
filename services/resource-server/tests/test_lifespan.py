"""Story 7.2 AC3 — lifespan fail-fast on discovery error (RS mirror).

Covers the lifespan-raises path that the AsyncClient-based test surface
cannot exercise (ASGITransport does not auto-invoke lifespan). We drive
`app.router.lifespan_context(app)` directly and assert:

1. A `DiscoveryFetchError` raised by `fetch_discovery` during startup
   propagates out of the lifespan context manager.
2. The ERROR log line carries the classifier (`discovery_unreachable: ...`).
3. After a failed startup, the RS app is unusable.

The stub from `tests/conftest.py` is replaced for these tests so the
lifespan sees a raising loader; monkeypatch restores it between tests.
"""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from resource_server import main as _rs_main
from resource_server.auth.oidc_discovery import DiscoveryFetchError
from resource_server.main import app


@pytest.fixture
def raising_fetch_discovery(monkeypatch: pytest.MonkeyPatch):
    """Replace `resource_server.main.fetch_discovery` with one that raises."""

    async def _raise(*_args: object, **_kwargs: object) -> object:
        raise DiscoveryFetchError("http_404")

    # Patch the name as bound inside `resource_server.main` (the lifespan
    # calls `fetch_discovery(...)` via that module-level reference, captured
    # at `from ... import fetch_discovery` time). Patching the source module
    # has no effect here because `resource_server.main` already holds a
    # direct reference.
    monkeypatch.setattr(_rs_main, "fetch_discovery", _raise)
    return _raise


async def test_lifespan_raises_when_discovery_fails(
    raising_fetch_discovery,
) -> None:
    """Discovery failure during startup propagates out of `lifespan_context`.

    The ERROR log line MUST contain the classifier verbatim so operators
    can grep `discovery_unreachable:` and see the failure mode without
    the URL or response body leaking. `configure_logging` installs its
    own root handlers that pytest's `caplog` does not see; attach a
    local handler for the assertion.
    """
    rs_main_logger = logging.getLogger("resource_server.main")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.setLevel(logging.ERROR)
    handler.emit = records.append  # type: ignore[method-assign]
    rs_main_logger.addHandler(handler)
    try:
        with pytest.raises(DiscoveryFetchError) as exc_info:
            async with app.router.lifespan_context(app):
                pass  # never reached — startup must raise first
    finally:
        rs_main_logger.removeHandler(handler)
    assert exc_info.value.classifier == "http_404"
    matching = [
        r
        for r in records
        if r.levelno == logging.ERROR and "discovery_unreachable" in r.getMessage()
    ]
    assert matching, "expected discovery_unreachable ERROR log"
    assert "http_404" in matching[0].getMessage()


async def test_app_unusable_after_lifespan_failure(
    raising_fetch_discovery,
) -> None:
    """After a failed startup, route handlers cannot be exercised."""
    with pytest.raises(DiscoveryFetchError):
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.get("/health")
                msg = "lifespan must have raised before reaching this point"
                raise AssertionError(msg)
