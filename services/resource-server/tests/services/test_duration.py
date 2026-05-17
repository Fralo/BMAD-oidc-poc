"""Boundary-table tests for ``resource_server.services.duration.format_duration``.

The boundary outputs are pinned in Story 4.1 AC2; the surrounding tests defend
the helper's contract:

- Purity (same input → same output).
- Defensive ``0`` return (``"≈ 0 m"`` — not a happy-path input; defended so
  a future coverage gap-fill doesn't trigger an unhandled-branch crash).
- ``ValueError`` on negative input (a bug upstream, not something the
  formatter should paper over).

The ``≈`` character is U+2248 ALMOST EQUAL TO — pinned via the helper's
module-level ``_PREFIX`` constant; this test compares the rendered string
verbatim so a look-alike (``≃`` / ``~``) regression is caught.
"""

from __future__ import annotations

import pytest

from resource_server.services.duration import format_duration


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (1, "≈ 1 m"),
        (12, "≈ 12 m"),
        (60, "≈ 1 h"),
        (61, "≈ 1 h 1 m"),
        (260, "≈ 4 h 20 m"),
        (1440, "≈ 1 d"),
        (1441, "≈ 1 d 1 m"),
        (1500, "≈ 1 d 1 h"),
        (2780, "≈ 1 d 22 h 20 m"),
    ],
)
def test_format_duration_boundary_table(minutes: int, expected: str) -> None:
    """AC2 boundary table — pinned outputs across m / h / d boundaries.

    The ``2780`` row pins the include-minutes-when-days-present rule
    (Story 4.1 AC2 explicit choice); a future flip to omit-minutes would
    fail this assertion loud and clear.
    """
    assert format_duration(minutes) == expected


def test_format_duration_zero_defensive() -> None:
    """``format_duration(0)`` is not a happy-path input — the endpoint's
    ``ge=1`` on ``pages`` + the ceiling rule guarantee ``minutes ≥ 1`` for
    every legal request. Still, pin the defensive return so a future caller
    (e.g., a coverage gap-fill) doesn't trigger an unhandled-branch crash.
    """
    assert format_duration(0) == "≈ 0 m"


@pytest.mark.parametrize("bad", [-1, -60, -1440])
def test_format_duration_raises_on_negative(bad: int) -> None:
    """Negative inputs indicate an upstream bug; raise rather than emit
    a nonsense duration string."""
    with pytest.raises(ValueError, match="non-negative"):
        format_duration(bad)


def test_format_duration_is_pure() -> None:
    """Two calls with the same input return identical strings — pins
    purity so a future implementation that stashes state on a module-level
    cache (and accidentally mutates it) is caught."""
    first = format_duration(260)
    second = format_duration(260)
    assert first == second == "≈ 4 h 20 m"
