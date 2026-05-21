"""Unit tests for the pure claim → role mapper (Story 7.1).

The mapper has no DB / network / I/O — every test is a single function call
against a literal claims dict. Exhaustive parametrization covers the empty /
unknown / single / multiple / mixed / repeated / mistyped paths declared in
the AC.
"""

from typing import Any

import pytest

from bff.auth.role_mapping import (
    Role,
    deserialize_roles,
    map_claims_to_roles,
    serialize_roles,
)


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        # AC2: empty / missing / non-list `groups` → empty role set
        pytest.param({}, frozenset(), id="empty_claims"),
        pytest.param({"sub": "x"}, frozenset(), id="missing_groups"),
        pytest.param({"groups": []}, frozenset(), id="empty_groups_list"),
        pytest.param({"groups": None}, frozenset(), id="none_groups"),
        pytest.param({"groups": "reader"}, frozenset(), id="bare_string_not_list"),
        pytest.param({"groups": {"reader"}}, frozenset(), id="set_not_list"),
        # AC2: unknown group → ignored
        pytest.param({"groups": ["unknown"]}, frozenset(), id="single_unknown"),
        # AC2: single known role
        pytest.param(
            {"groups": ["reader"]}, frozenset({Role.READER}), id="single_reader"
        ),
        pytest.param(
            {"groups": ["admin"]}, frozenset({Role.ADMIN}), id="single_admin"
        ),
        # AC2: multiple known roles (order-insensitive)
        pytest.param(
            {"groups": ["reader", "admin"]},
            frozenset({Role.READER, Role.ADMIN}),
            id="reader_then_admin",
        ),
        pytest.param(
            {"groups": ["admin", "reader"]},
            frozenset({Role.READER, Role.ADMIN}),
            id="admin_then_reader",
        ),
        # AC2: de-dup via set semantics
        pytest.param(
            {"groups": ["reader", "reader"]},
            frozenset({Role.READER}),
            id="duplicated_reader",
        ),
        # AC2: partial-known mix
        pytest.param(
            {"groups": ["reader", "unknown", "admin"]},
            frozenset({Role.READER, Role.ADMIN}),
            id="reader_unknown_admin",
        ),
        # Defensive: non-string entries inside an otherwise-valid list
        pytest.param(
            {"groups": ["reader", 42, None, "admin"]},
            frozenset({Role.READER, Role.ADMIN}),
            id="mixed_types_with_known_roles",
        ),
        # Case sensitivity is a documented expectation (AC1 failure-prevention)
        pytest.param(
            {"groups": ["Reader", "ADMIN"]},
            frozenset(),
            id="case_mismatch_no_roles",
        ),
    ],
)
def test_map_claims_to_roles(
    claims: dict[str, Any], expected: frozenset[Role]
) -> None:
    assert map_claims_to_roles(claims) == expected


def test_map_claims_to_roles_is_idempotent() -> None:
    """Calling the mapper twice on the same dict returns equal frozensets."""
    claims = {"groups": ["reader", "admin"]}
    first = map_claims_to_roles(claims)
    second = map_claims_to_roles(claims)
    assert first == second
    assert first is not second  # different frozenset instances, equal contents


def test_role_enum_values_are_lowercase() -> None:
    """Architecture / AC1 invariant: Role values match Keycloak group names byte-for-byte."""
    assert Role.READER.value == "reader"
    assert Role.ADMIN.value == "admin"


def test_role_enum_membership_roundtrip() -> None:
    """`Role("reader")` must round-trip — the mapper depends on this."""
    assert Role("reader") is Role.READER
    assert Role("admin") is Role.ADMIN
    with pytest.raises(ValueError):
        Role("unknown")


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        pytest.param(frozenset(), "", id="empty"),
        pytest.param(frozenset({Role.READER}), "reader", id="reader_only"),
        pytest.param(frozenset({Role.ADMIN}), "admin", id="admin_only"),
        pytest.param(
            frozenset({Role.READER, Role.ADMIN}),
            "admin,reader",
            id="both_sorted_alphabetically",
        ),
    ],
)
def test_serialize_roles(roles: frozenset[Role], expected: str) -> None:
    """Serialization is deterministic and alphabetically sorted."""
    assert serialize_roles(roles) == expected


@pytest.mark.parametrize(
    ("blob", "expected"),
    [
        pytest.param("", [], id="empty_string"),
        pytest.param("reader", ["reader"], id="single"),
        pytest.param("admin,reader", ["admin", "reader"], id="two_sorted"),
        # Defensive: deserialize never raises on unknown names — wire-side
        # consumers (`/api/me/roles`) emit raw strings.
        pytest.param("ghost", ["ghost"], id="unknown_passes_through"),
    ],
)
def test_deserialize_roles(blob: str, expected: list[str]) -> None:
    assert deserialize_roles(blob) == expected


def test_serialize_deserialize_roundtrip() -> None:
    """A serialize → deserialize round-trip preserves the role-name list."""
    roles = frozenset({Role.READER, Role.ADMIN})
    blob = serialize_roles(roles)
    parsed = deserialize_roles(blob)
    assert parsed == ["admin", "reader"]
    # Re-typing the strings back to Role members yields the original set.
    assert frozenset(Role(r) for r in parsed) == roles
