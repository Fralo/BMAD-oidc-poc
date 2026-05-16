#!/usr/bin/env python3
"""Remove Dummy CRUD demo boilerplate from the resource-server project.

Run from the project root:  python3 scripts/remove_demo.py

Requires a clean git working tree (no uncommitted changes).
Uses only the Python standard library.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FILES_TO_DELETE = [
    "src/resource_server/models/entities/dummy.py",
    "src/resource_server/models/dto/v1/dummy.py",
    "src/resource_server/factories/dummy.py",
    "src/resource_server/api/v1/dummy_routes.py",
    "src/resource_server/api/v2/dummy_routes.py",
    "src/resource_server/services/v1/dummy.py",
    "src/resource_server/services/v1/mock_dummy.py",
    "src/resource_server/services/v1/dummy_service.py",
    "src/resource_server/services/v2/dummy.py",
    "src/resource_server/services/v2/mock_dummy.py",
    "src/resource_server/services/v2/dummy_service.py",
    "src/resource_server/services/factory.py",
    "tests/api/test_dummy_routes.py",
    "tests/api/test_v2_dummy_routes.py",
    "tests/api/test_profile_service_selection.py",
    "tests/services/v1/test_dummy_service.py",
    "tests/services/v2/test_dummy_service.py",
]


def _git_tree_is_clean() -> bool:
    try:
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "diff", "--cached", "--quiet", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _collapse_blank_lines(text: str) -> str:
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text


def _edit_constants(path: Path) -> None:
    content = _read(path)
    block = (
        "\n\n"
        "DUMMIES = ResourceDefinition(\n"
        '    path="/dummies",\n'
        '    name="Dummies",\n'
        '    description="Dummy resources for demonstrating CRUD patterns",\n'
        ")\n"
    )
    content = content.replace(block, "")
    _write(path, _collapse_blank_lines(content))


def _edit_errors(path: Path) -> None:
    content = _read(path)
    content = content.replace(
        '    DUMMY_NOT_FOUND = ("DUMMY_NOT_FOUND", "Dummy not found", 404)\n', ""
    )
    _write(path, content)


def _edit_services_init(path: Path) -> None:
    _write(path, "")


def _edit_api_v1_init(path: Path) -> None:
    content = 'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/v1")\n'
    _write(path, content)


def _edit_api_v2_init(path: Path) -> None:
    content = 'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/v2")\n'
    _write(path, content)


def _edit_prometheus(path: Path) -> None:
    content = _read(path)
    content = content.replace("from dataclasses import dataclass\n", "")
    content = content.replace("from prometheus_client import Counter\n", "")
    block = (
        "\n\n"
        "@dataclass(frozen=True)\n"
        "class Counters:\n"
        "    dummies_created_total: Counter\n"
        "\n\n"
        "@dataclass(frozen=True)\n"
        "class Metrics:\n"
        "    counters: Counters\n"
        "\n\n"
        "metrics = Metrics(\n"
        "    counters=Counters(\n"
        "        dummies_created_total=Counter(\n"
        '            "dummies_created_total",\n'
        '            "Total number of dummy resources created",\n'
        '            labelnames=["api_version"],\n'
        "        ),\n"
        "    ),\n"
        ")\n"
    )
    content = content.replace(block, "")
    _write(path, _collapse_blank_lines(content))


def _edit_tests_conftest(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    _skip_prefixes = (
        "from resource_server.services.v1.dummy_service",
        "from resource_server.services.v2.dummy_service",
    )
    filtered: list[str] = [ln for ln in lines if not ln.startswith(_skip_prefixes)]
    content = "".join(filtered)
    fixture_start = "@pytest.fixture(autouse=True)\ndef _clear_service_caches"
    if fixture_start in content:
        result_lines = content.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        while i < len(result_lines):
            line = result_lines[i]
            if line.startswith("@pytest.fixture(autouse=True)") and i + 1 < len(
                result_lines
            ):
                next_line = result_lines[i + 1]
                if next_line.startswith("def _clear_service_caches"):
                    i += 2
                    while i < len(result_lines):
                        if result_lines[i] and not result_lines[i][0].isspace():
                            break
                        i += 1
                    continue
            out.append(line)
            i += 1
        content = "".join(out)
    _write(path, _collapse_blank_lines(content))


def _edit_main(path: Path) -> None:
    content = _read(path)
    content = content.replace("import uuid as uuid_module\n", "")
    content = content.replace(
        "from resource_server.models.entities.dummy import Dummy\n", ""
    )
    # Remove _backfill_dummy_uuids function and its call in lifespan.
    lines = content.splitlines(keepends=True)
    new_lines: list[str] = []
    in_backfill_fn = False
    for line in lines:
        if line.startswith("async def _backfill_dummy_uuids("):
            in_backfill_fn = True
            continue
        if in_backfill_fn:
            if line and not line[0].isspace() and line.strip():
                in_backfill_fn = False
            else:
                continue
        if "_backfill_dummy_uuids" in line:
            continue
        new_lines.append(line)
    _write(path, _collapse_blank_lines("".join(new_lines)))


_EDIT_DISPATCH: list[tuple[str, Callable[[Path], None]]] = [
    ("src/resource_server/main.py", _edit_main),
    ("src/resource_server/core/constants.py", _edit_constants),
    ("src/resource_server/core/errors.py", _edit_errors),
    ("src/resource_server/services/__init__.py", _edit_services_init),
    ("src/resource_server/api/v1/__init__.py", _edit_api_v1_init),
    ("src/resource_server/api/v2/__init__.py", _edit_api_v2_init),
    ("src/resource_server/observability/prometheus.py", _edit_prometheus),
    ("tests/conftest.py", _edit_tests_conftest),
]


def main() -> int:
    if not _git_tree_is_clean():
        print(
            "ERROR: Git working tree has uncommitted changes.\n"
            "Please commit or stash your changes before running this script.",
            file=sys.stderr,
        )
        return 1

    print("Removing Dummy CRUD demo boilerplate...")

    for rel_path in FILES_TO_DELETE:
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            full_path.unlink()
            print(f"  Deleted: {rel_path}")
        else:
            print(f"  Skipped (not found): {rel_path}")

    for rel_path, edit_fn in _EDIT_DISPATCH:
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            edit_fn(full_path)
            print(f"  Edited:  {rel_path}")
        else:
            print(f"  Skipped (not found): {rel_path}")

    print("\nDone! The Dummy demo has been removed.")
    print("Next steps:")
    print("  1. Review the changes: git diff")
    print("  2. Run the test suite: pytest")
    print("  3. Commit: git add -A && git commit -m 'chore: remove demo boilerplate'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
