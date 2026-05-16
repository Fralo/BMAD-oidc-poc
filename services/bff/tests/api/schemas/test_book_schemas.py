"""Tests for the books Pydantic boundary models.

Story 2.1 ACs covered here: AC4 (BookCreate/BookUpdate validation
rules), AC9 (full enumeration of accepted/rejected inputs and the
ORM round-trip semantics that hide `sub` from `BookOut`).
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bff.api.schemas import BookCreate, BookOut, BookUpdate
from bff.models.entities.book import Book


def test_book_create_happy_path() -> None:
    bc = BookCreate(title="Dune", pages=688, status="reading")
    assert bc.title == "Dune"
    assert bc.pages == 688
    assert bc.status == "reading"

    # `status` defaults to "to-read" when omitted.
    default_status = BookCreate(title="Dune", pages=688)
    assert default_status.status == "to-read"


def test_book_create_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        BookCreate(title="", pages=10)


def test_book_create_rejects_whitespace_title() -> None:
    with pytest.raises(ValidationError):
        BookCreate(title="   ", pages=10)


def test_book_create_rejects_missing_title() -> None:
    with pytest.raises(ValidationError):
        BookCreate(pages=10)  # type: ignore[call-arg]


def test_book_create_rejects_nonpositive_pages() -> None:
    with pytest.raises(ValidationError):
        BookCreate(title="OK", pages=0)
    with pytest.raises(ValidationError):
        BookCreate(title="OK", pages=-1)


def test_book_create_rejects_missing_pages() -> None:
    with pytest.raises(ValidationError):
        BookCreate(title="OK")  # type: ignore[call-arg]


def test_book_create_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        BookCreate(title="OK", pages=10, status="archived")  # type: ignore[arg-type]


def test_book_update_all_fields_optional() -> None:
    # Empty patch is OK at the model layer — handler decides what to
    # do with it (see story scope note on AC3).
    bu = BookUpdate()
    assert bu.title is None
    assert bu.pages is None
    assert bu.status is None


def test_book_update_partial_status_only() -> None:
    bu = BookUpdate(status="finished")
    assert bu.title is None
    assert bu.pages is None
    assert bu.status == "finished"


def test_book_update_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        BookUpdate(pages=0)
    with pytest.raises(ValidationError):
        BookUpdate(status="archived")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BookUpdate(title="")
    with pytest.raises(ValidationError):
        BookUpdate(title="   ")


def test_book_out_roundtrips_from_orm() -> None:
    now = datetime.now(UTC)
    orm = Book(
        id=42,
        sub="user-sub-1",
        title="Dune",
        pages=688,
        status="reading",
        created_at=now,
        updated_at=now,
    )
    out = BookOut.model_validate(orm)
    dumped = out.model_dump()
    assert set(dumped.keys()) == {
        "id",
        "title",
        "pages",
        "status",
        "created_at",
        "updated_at",
    }
    assert "sub" not in dumped
    assert dumped["id"] == 42
    assert dumped["title"] == "Dune"
    assert dumped["pages"] == 688
    assert dumped["status"] == "reading"


def test_book_out_serializes_datetime_iso8601_utc() -> None:
    now = datetime.now(UTC)
    orm = Book(
        id=1,
        sub="user-sub-1",
        title="Dune",
        pages=688,
        status="to-read",
        created_at=now,
        updated_at=now,
    )
    out = BookOut.model_validate(orm)
    jsonable = out.model_dump(mode="json")

    assert isinstance(jsonable["created_at"], str)
    assert isinstance(jsonable["updated_at"], str)
    # Exact Z-suffix shape is Story 2.2's concern; here, just confirm
    # the string round-trips through ISO 8601 parsing.
    datetime.fromisoformat(jsonable["created_at"])
    datetime.fromisoformat(jsonable["updated_at"])
