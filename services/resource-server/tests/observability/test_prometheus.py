"""Prometheus client primitives are exercised here, but the /metrics
endpoint is intentionally NOT mounted on the RS app.

Per Story 3.1 / AC #4 and the 2026-05-14 sprint-change cut, the
observability stack is excised from the runtime — no /metrics endpoint,
no OTEL exporter wiring. The archetype-emitted observability/* modules
remain on disk for documentation parity and so a future re-introduction
is a one-line wiring change, but they are not invoked from
resource_server.main. The four tests that previously asserted on
/metrics response shape and prometheus_client auto-instrumentation are
removed; the remaining tests exercise the prometheus_client library's
Counter API in isolation, which is still useful as a sanity check that
the dependency is installed and importable.
"""

from prometheus_client import Counter

_test_counter = Counter(
    "test_operations_total",
    "Test counter for prometheus infrastructure validation",
    labelnames=["operation"],
)


def _op_value(operation: str) -> float:
    # noinspection PyProtectedMember
    return _test_counter.labels(operation=operation)._value.get()


def test_counter_increments_on_call() -> None:
    before = _op_value("create")
    _test_counter.labels(operation="create").inc()
    assert _op_value("create") == before + 1


def test_counter_increments_multiple() -> None:
    before = _op_value("create")
    _test_counter.labels(operation="create").inc()
    _test_counter.labels(operation="create").inc()
    assert _op_value("create") == before + 2


def test_labels_are_independent() -> None:
    create_before = _op_value("create")
    read_before = _op_value("read")
    _test_counter.labels(operation="create").inc()
    assert _op_value("create") == create_before + 1
    assert _op_value("read") == read_before
