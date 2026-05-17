# noinspection PyProtectedMember
from resource_server.aop.logging_decorator import (
    _format_arg,
    _format_call_args,
    _format_exc,
)


class _BrokenRepr:
    def __repr__(self) -> str:
        raise RuntimeError("cannot render")


def test_format_arg_falls_back_when_repr_raises() -> None:
    assert _format_arg(_BrokenRepr()) == "<_BrokenRepr>"


def test_format_call_args_falls_back_when_signature_fails(
    monkeypatch,
) -> None:
    def sample(a: int, b: int) -> int:
        return a + b

    def _raise_type_error(_func):  # noqa: ANN001
        raise TypeError("signature unavailable")

    monkeypatch.setattr(
        "resource_server.aop.logging_decorator.inspect.signature",
        _raise_type_error,
    )

    formatted = _format_call_args(sample, (1,), {"b": 2})
    assert formatted == "1, b=2"


def test_format_exc_returns_unknown_without_active_exception() -> None:
    assert _format_exc() == "Unknown exception"
