import logging
from collections.abc import MutableMapping
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from bff.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _add_timestamp,
    _inject_trace_context,
    _plain_renderer,
)

_VALID_CTX = SpanContext(
    trace_id=0xABCDEF1234567890ABCDEF1234567890,
    span_id=0x1234567890ABCDEF,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
)


def _base_event(
    message: str = "test message", **extra: Any
) -> MutableMapping[str, Any]:
    ed: MutableMapping[str, Any] = {
        "event": message,
        "level": "info",
        "logger": "test.logger",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "traceId": NO_TRACE_ID,
        "spanId": NO_SPAN_ID,
    }
    ed.update(extra)
    return ed


class TestPlainRenderer:
    def test_plain_format_fields(self) -> None:
        ed = _base_event("hello world", logger="test.plain")
        output = _plain_renderer(None, "info", ed)
        assert f"[{NO_TRACE_ID}]" in output
        assert f"[{NO_SPAN_ID}]" in output
        assert "INFO" in output
        assert "test.plain" in output
        assert "hello world" in output

    def test_plain_trace_id_and_span_id_in_brackets(self) -> None:
        span = NonRecordingSpan(_VALID_CTX)
        with trace.use_span(span):
            ed = _base_event("with span")
            _inject_trace_context(None, "info", ed)
            output = _plain_renderer(None, "info", ed)
            assert f"[{ed['traceId']}]" in output
            assert f"[{ed['spanId']}]" in output

    def test_plain_format_utc_iso8601(self) -> None:
        record = logging.LogRecord(
            "test.ts", logging.INFO, "test.py", 1, "ts check", (), None
        )
        ts_dict: MutableMapping[str, Any] = {"event": "ts check", "_record": record}
        _add_timestamp(None, "info", ts_dict)
        ed = {**_base_event("ts check"), "timestamp": ts_dict["timestamp"]}
        output = _plain_renderer(None, "info", ed)
        timestamp = output.split(" ")[0]
        assert "+00:00" in timestamp or timestamp.endswith("Z")


class TestTraceCorrelation:
    def test_no_trace_context_yields_placeholders(self) -> None:
        ed: MutableMapping[str, Any] = {"event": "no span"}
        _inject_trace_context(None, "info", ed)
        assert ed["traceId"] == NO_TRACE_ID
        assert ed["spanId"] == NO_SPAN_ID

    def test_active_span_injects_both_ids(self) -> None:
        span = NonRecordingSpan(_VALID_CTX)
        with trace.use_span(span):
            ed: MutableMapping[str, Any] = {"event": "traced"}
            _inject_trace_context(None, "info", ed)
            assert ed["traceId"] != NO_TRACE_ID
            assert len(ed["traceId"]) == 32
            assert ed["spanId"] != NO_SPAN_ID
            assert len(ed["spanId"]) == 16

    def test_invalid_span_context_yields_placeholders(self) -> None:
        invalid_ctx = SpanContext(
            trace_id=0,
            span_id=0,
            is_remote=False,
            trace_flags=TraceFlags(0),
        )
        span = NonRecordingSpan(invalid_ctx)
        with trace.use_span(span):
            ed: MutableMapping[str, Any] = {"event": "invalid ctx"}
            _inject_trace_context(None, "info", ed)
            assert ed["traceId"] == NO_TRACE_ID
            assert ed["spanId"] == NO_SPAN_ID


class TestAddTimestamp:
    def test_timestamp_from_log_record(self) -> None:
        record = logging.LogRecord("test", logging.INFO, "test.py", 1, "msg", (), None)
        ed: MutableMapping[str, Any] = {"event": "msg", "_record": record}
        _add_timestamp(None, "info", ed)
        assert "timestamp" in ed
        ts = str(ed["timestamp"])
        assert "+00:00" in ts or ts.endswith("Z")

    def test_timestamp_without_record(self) -> None:
        ed: MutableMapping[str, Any] = {"event": "msg"}
        _add_timestamp(None, "info", ed)
        assert "timestamp" in ed
        ts = str(ed["timestamp"])
        assert "+00:00" in ts or ts.endswith("Z")
