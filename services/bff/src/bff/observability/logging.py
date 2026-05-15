import json
import logging
import re
import traceback
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry import trace

from bff.core.config import AppSettings

NO_TRACE_ID = "NO_TRACE_ID"
NO_SPAN_ID = "NO_SPAN_ID"

_REDACTED = "***"
_AUTH_HEADER_RE = re.compile(
    r"(?i)((?:authorization|bearer)\s*[=:\s]+)(\S+(?:\s+\S+)?)",
)
_SECRET_KEY_RE = re.compile(
    r"(?i)"
    r"(password|passwd|pwd|secret|token|api[_-]?key|apikey|credential)"
    r"([=:\s]+)"
    r"(\S+)",
)


def _redact_secrets(text: str) -> str:
    text = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{_REDACTED}", text)
    return _SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)


def _current_span_ids() -> tuple[str, str]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    return NO_TRACE_ID, NO_SPAN_ID


def _inject_trace_context(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor: inject OTEL traceId and spanId into every log event."""
    trace_id, span_id = _current_span_ids()
    event_dict["traceId"] = trace_id
    event_dict["spanId"] = span_id
    return event_dict


def _add_timestamp(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor: attach a UTC ISO-8601 timestamp from the LogRecord."""
    record = event_dict.get("_record")
    if isinstance(record, logging.LogRecord):
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        event_dict["timestamp"] = ts
    else:
        event_dict["timestamp"] = datetime.now(tz=UTC).isoformat()
    return event_dict


def _extract_exc_info(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor: lift exc_info from the LogRecord before it is stripped."""
    record = event_dict.get("_record")
    if (
        isinstance(record, logging.LogRecord)
        and record.exc_info
        and record.exc_info[1] is not None
    ):
        event_dict["exc_info"] = record.exc_info
        record.exc_info = None
        record.exc_text = None
    return event_dict


def _plain_renderer(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> str:
    """Structlog renderer: plain text format matching the documented format contract."""
    timestamp = event_dict.get("timestamp", "")
    trace_id = event_dict.get("traceId", NO_TRACE_ID)
    span_id = event_dict.get("spanId", NO_SPAN_ID)
    level = str(event_dict.get("level", _method)).upper()
    logger_name = event_dict.get("logger", "")
    event = str(event_dict.get("event", ""))

    line = f"{timestamp} [{trace_id}] [{span_id}] {level} {logger_name} {event}"

    exc_info = event_dict.get("exc_info")
    if exc_info and isinstance(exc_info, tuple) and exc_info[1] is not None:
        exc_type, exc_val, _ = exc_info
        name = exc_type.__qualname__ if exc_type else "Exception"
        line = f"{line}\n{name}: {exc_val}"

    return _redact_secrets(line)


def _json_renderer(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> str:
    """Structlog renderer: JSON format matching the documented format contract."""
    entry: dict[str, object] = {
        "timestamp": event_dict.get("timestamp", ""),
        "level": event_dict.get("level", _method),
        "logger": event_dict.get("logger", ""),
        "message": _redact_secrets(str(event_dict.get("event", ""))),
        "traceId": event_dict.get("traceId", NO_TRACE_ID),
        "spanId": event_dict.get("spanId", NO_SPAN_ID),
    }

    exc_info = event_dict.get("exc_info")
    if exc_info and isinstance(exc_info, tuple) and exc_info[1] is not None:
        exc_type, exc_val, exc_tb = exc_info
        entry["exceptionType"] = exc_type.__qualname__ if exc_type else "Exception"
        entry["exceptionMessage"] = _redact_secrets(str(exc_val))
        entry["stackTrace"] = [
            _redact_secrets(line)
            for line in traceback.format_exception(exc_type, exc_val, exc_tb)
        ]

    return json.dumps(entry, default=str)


def configure_logging(settings: AppSettings) -> None:
    renderer = _plain_renderer if settings.log_mode == "plain" else _json_renderer

    pre_chain: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_timestamp,
        _inject_trace_context,
        _extract_exc_info,
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
