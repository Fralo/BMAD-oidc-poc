import functools
import inspect
import logging
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)


def _format_arg(value: Any) -> str:
    """Return a compact, readable representation of a single argument."""
    try:
        r = repr(value)
    except Exception:  # noqa: BLE001
        r = f"<{type(value).__name__}>"
    if len(r) > 80 or r.startswith("<"):
        return f"<{type(value).__name__}>"
    return r


def _format_call_args(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Bind positional/keyword args to parameter names and format them."""
    try:
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        parts = [f"{name}={_format_arg(val)}" for name, val in bound.arguments.items()]
    except ValueError, TypeError:
        parts = [_format_arg(a) for a in args]
        parts.extend(f"{k}={_format_arg(v)}" for k, v in kwargs.items())
    return ", ".join(parts)


def _format_exc() -> str:
    """Return a compact ``ExcType: message`` string for the current exception."""
    exc_type, exc_val, _ = sys.exc_info()
    if exc_type is None:
        return "Unknown exception"
    name = exc_type.__qualname__
    return f"{name}: {exc_val}" if exc_val else name


def log_io(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that logs function I/O at DEBUG and exceptions at ERROR.

    Handles both sync and async (coroutine) functions transparently.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            qualname = getattr(func, "__qualname__", repr(func))
            formatted = _format_call_args(func, args, kwargs)
            logger.debug("%s invoked with args (%s)", qualname, formatted)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.error("%s raised %s", qualname, _format_exc(), exc_info=True)
                raise
            logger.debug("%s returned %s", qualname, _format_arg(result))
            return result

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        qualname = getattr(func, "__qualname__", repr(func))
        formatted = _format_call_args(func, args, kwargs)
        logger.debug("%s invoked with args (%s)", qualname, formatted)
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.error("%s raised %s", qualname, _format_exc(), exc_info=True)
            raise
        logger.debug("%s returned %s", qualname, _format_arg(result))
        return result

    return wrapper


def apply_logging(module: ModuleType) -> None:
    """Wrap all public functions defined in *module* with the :func:`log_io` decorator.

    Only functions whose ``__module__`` matches the target module are wrapped,
    so re-exported imports are left untouched.
    """
    for name in dir(module):
        if name.startswith("_"):
            continue
        attr = getattr(module, name)
        if (
            inspect.isfunction(attr)
            and getattr(attr, "__module__", None) == module.__name__
        ):
            setattr(module, name, log_io(attr))
