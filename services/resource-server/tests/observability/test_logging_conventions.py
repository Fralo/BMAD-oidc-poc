import logging

import structlog
from httpx import AsyncClient

from resource_server.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _current_span_ids,
)


class TestExistingConventions:
    def test_getlogger_pattern_works(self) -> None:
        lgr = logging.getLogger(__name__)
        assert lgr.name == __name__

    def test_structlog_getlogger_works(self) -> None:
        lgr = structlog.get_logger(__name__)
        assert lgr is not None

    def test_aop_compatibility(self) -> None:
        from resource_server.aop.logging_decorator import log_io

        @log_io
        def sample(x: int) -> int:
            return x * 2

        assert sample(3) == 6


class TestTraceCorrelationDuringRequest:
    async def test_request_emits_no_trace_ids_when_otel_disabled(
        self, client: AsyncClient
    ) -> None:
        """Story 3.1: OTEL exporter wiring + FastAPIInstrumentor are
        intentionally excised from `resource_server.main` per the
        2026-05-14 sprint-change cut and AR1 archetype-mandate note.

        Without `instrument_app(...)`, no span is opened on each request
        and `_current_span_ids()` returns the placeholder sentinels. This
        test pins the deliberate posture — a future story re-enabling
        OTEL will need to flip this expectation and add the wiring back.
        """
        captured: list[tuple[str, str]] = []

        class _Capture(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                captured.append(_current_span_ids())
                return True

        stub_logger = logging.getLogger("resource_server.test_stubs")
        capture = _Capture()
        stub_logger.addFilter(capture)
        original_level = stub_logger.level
        stub_logger.setLevel(logging.DEBUG)
        try:
            await client.get("/test/open")
        finally:
            stub_logger.removeFilter(capture)
            stub_logger.setLevel(original_level)

        assert len(captured) > 0, "Expected stub log during the request"
        assert all(tid == NO_TRACE_ID and sid == NO_SPAN_ID for tid, sid in captured), (
            f"Expected placeholder trace/span IDs (OTEL is disabled per "
            f"Story 3.1), got: {captured}"
        )
