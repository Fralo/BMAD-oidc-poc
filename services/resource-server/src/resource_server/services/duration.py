"""Duration-formatting helper for ``/v1/estimate`` response payloads.

Renders integer minutes as the UX-DR18 string the SPA emits verbatim — e.g.,
``"≈ 4 h 20 m"`` / ``"≈ 12 m"`` / ``"≈ 1 d 22 h 20 m"`` (ux-design-specification.md
lines 232, 250, 478). The leading character is U+2248 ALMOST EQUAL TO (``≈``),
not ``~`` or ``≃``; pinned via the module-level ``_PREFIX`` constant so a
look-alike substitution breaks the boundary tests rather than silently
emitting the wrong glyph.

Story 4.1 pins the include-minutes-when-days-present rule: inputs ``≥ 1440``
emit days + hours + minutes when any are non-zero (``format_duration(2780)``
→ ``"≈ 1 d 22 h 20 m"``). The epic AC offered the implementer a choice; this
project picked the include-minutes branch so the J3 E2E spec (Story 4.4)
asserts against a single deterministic output.

Naturally a one-file helper, ``services/duration.py`` is not in
architecture.md's directory listing but matches the architectural style
"one service module per domain concept" — ``duration`` is a formatting
domain colocated with ``estimate_service`` that consumes it.
"""

from __future__ import annotations

# U+2248 ALMOST EQUAL TO. Defined as a constant so a grep for the symbol
# lands in one place and a look-alike substitution (``≃`` U+2243 / ``~``
# U+007E / ``∼`` U+223C) trips the boundary tests, not silently emits the
# wrong glyph. Story 4.1 AC2.
_PREFIX = "≈"

_MINUTES_PER_HOUR = 60
_MINUTES_PER_DAY = 24 * _MINUTES_PER_HOUR


def format_duration(minutes: int) -> str:
    """Render an integer minute count as a UX-DR18 duration string.

    Args:
        minutes: Non-negative integer minute count. ``0`` is accepted (returns
            ``"≈ 0 m"``) as a defensive path even though no legal request
            produces it (``pages ≥ 1`` + ``pages_per_hour ≥ 1`` + ceiling
            rounding guarantee ``minutes ≥ 1``).

    Returns:
        A UX-DR18 string with the U+2248 prefix and non-zero d / h / m
        components joined by single spaces.

    Raises:
        ValueError: If ``minutes`` is negative.
    """
    if minutes < 0:
        raise ValueError(
            f"format_duration requires a non-negative integer; got {minutes!r}"
        )
    if minutes == 0:
        # Defensive — see module docstring; pinned in tests as intentional.
        return f"{_PREFIX} 0 m"

    days, remainder = divmod(minutes, _MINUTES_PER_DAY)
    hours, mins = divmod(remainder, _MINUTES_PER_HOUR)

    parts: list[str] = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if mins:
        parts.append(f"{mins} m")

    return f"{_PREFIX} " + " ".join(parts)
