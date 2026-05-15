import json
import logging
import sys
from collections.abc import MutableMapping
from typing import Any

from bff.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _extract_exc_info,
    _json_renderer,
    _plain_renderer,
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


class TestExceptionPlainMode:
    def test_plain_exception_includes_message(self) -> None:
        try:
            raise ValueError("something broke")
        except ValueError:
            ei = sys.exc_info()

        ed = _base_event("op failed", exc_info=ei)
        output = _plain_renderer(None, "error", ed)
        assert "ValueError: something broke" in output

    def test_plain_exception_no_full_traceback(self) -> None:
        try:
            raise RuntimeError("bad state")
        except RuntimeError:
            ei = sys.exc_info()

        ed = _base_event("op failed", exc_info=ei)
        output = _plain_renderer(None, "error", ed)
        assert "Traceback" not in output
        assert "RuntimeError: bad state" in output


class TestExceptionJsonMode:
    def test_json_exception_structured_fields(self) -> None:
        try:
            raise TypeError("wrong type")
        except TypeError:
            ei = sys.exc_info()

        ed = _base_event("op failed", exc_info=ei)
        parsed = json.loads(_json_renderer(None, "error", ed))
        assert parsed["exceptionType"] == "TypeError"
        assert parsed["exceptionMessage"] == "wrong type"
        assert isinstance(parsed["stackTrace"], list)
        assert len(parsed["stackTrace"]) > 0

    def test_json_no_exception_no_extra_fields(self) -> None:
        ed = _base_event("normal msg")
        parsed = json.loads(_json_renderer(None, "info", ed))
        assert "exceptionType" not in parsed
        assert "stackTrace" not in parsed


class TestExcInfoExtraction:
    def test_extract_exc_info_from_log_record(self) -> None:
        try:
            raise ValueError("test error")
        except ValueError:
            ei = sys.exc_info()

        record = logging.LogRecord("test", logging.ERROR, "test.py", 1, "msg", (), None)
        record.exc_info = ei
        ed: MutableMapping[str, Any] = {"event": "msg", "_record": record}
        _extract_exc_info(None, "error", ed)

        assert "exc_info" in ed
        assert ed["exc_info"][1] is ei[1]
        assert record.exc_info is None

    def test_extract_exc_info_no_exception(self) -> None:
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1, "no exc", (), None
        )
        record.exc_info = None
        ed: MutableMapping[str, Any] = {"event": "no exc", "_record": record}
        _extract_exc_info(None, "info", ed)
        assert "exc_info" not in ed
