# New Requirements — Post-Review Polish

## Context

After epics 20–25 were implemented, a review of the current codebase against the
original [FEEDBACK.md](./FEEDBACK.md) surfaced nine residual issues: incomplete
deliverables, internal inconsistencies, and small-but-visible quality gaps. None
are architectural; all are completion-quality items that should be resolved before
the feedback round can be considered closed.

The issues are grouped into two epics: one for code changes, one for documentation
and naming alignment.

---

## Epic 26 — Code Completeness & Consistency

Small, targeted code fixes that close gaps left by epics 20–25.

### 26.1: Replace remaining `type: ignore` in `main.py`

**Problem:** Epic 21 Story 21.2 required zero `# type: ignore` comments. One
remains at `main.py` line 42 (`Dummy.__table__.update()  # type: ignore[union-attr]`).
There is also a `# ty: ignore[invalid-argument-type]` on the CORSMiddleware call
(line 73).

**Action:** Investigate and resolve both suppressions. For the `__table__` access,
use `cast()` or restructure the query to avoid the union ambiguity. For the
CORSMiddleware suppression, resolve the type mismatch or use `cast()` if it is a
genuine library typing gap (and document why in a brief inline comment).

**Acceptance criteria:**
- Zero `# type: ignore` comments in `src/`.
- Any remaining `# ty: ignore` has a brief inline comment explaining the library
  typing limitation it works around.
- All quality checks pass.

### 26.2: Add coverage exclusion for mock implementation files

**Problem:** Epic 23 Story 23.2 required mock implementation files excluded from
coverage measurement. The `[tool.coverage.report]` section in `pyproject.toml` has
no `omit` configuration.

**Action:** Add an `omit` list to `[tool.coverage.run]` (or `exclude_lines` /
`omit` under `[tool.coverage.report]`) that excludes mock service modules
(`**/mock_dummy.py` or the equivalent pattern).

**Acceptance criteria:**
- `pyproject.toml` coverage config excludes mock implementation files.
- `uv run pytest --cov` does not report coverage for mock modules.
- All quality checks pass.

### 26.3: Remove duplicated `identity_role_mapper` from `entra.py`

**Problem:** `identity_role_mapper` is defined in `auth/role_mapping.py` (the
canonical location) and again locally in `auth/entra.py` (line 176). This is
exactly the kind of duplication the original feedback flagged.

**Action:** Delete the local `identity_role_mapper` definition from `entra.py` and
import it from `auth.role_mapping` instead.

**Acceptance criteria:**
- `identity_role_mapper` is defined only in `auth/role_mapping.py`.
- `entra.py` imports it from `auth.role_mapping`.
- All quality checks pass.

### 26.4: Make auth factory a true dict-dispatch

**Problem:** `auth/factory.py` docstring says "dict-dispatch" but the
implementation is `if/else` with a lazy `try/except` import. The service factory
uses genuine dict-dispatch (`modules = {"default": ..., "mock": ...}`), making the
inconsistency visible.

**Action:** Restructure `get_auth()` to use a dict mapping from `auth_type` to a
callable that produces `AuthFunctions`. The lazy import for `httpx` (needed by
Entra) can be preserved by wrapping the Entra branch in a factory callable within
the dict. Example shape:

```python
def get_auth(settings: AppSettings) -> AuthFunctions:
    def _build_none() -> AuthFunctions:
        return AuthFunctions(
            authenticate_bearer_token=none_auth.authenticate_bearer_token,
            ...
            role_mapper=identity_role_mapper,
        )

    def _build_entra() -> AuthFunctions:
        try:
            from resource_server.auth.entra import make_entra_auth
        except ModuleNotFoundError as exc:
            ...
        return make_entra_auth(settings)

    builders: dict[str, Callable[[], AuthFunctions]] = {
        "none": _build_none,
        "entra": _build_entra,
    }
    return builders[settings.auth_type]()
```

**Acceptance criteria:**
- `get_auth()` uses a dict mapping from `auth_type` to a builder callable.
- Lazy `httpx` import is preserved for the Entra branch.
- All quality checks pass.

### 26.5: Cache service DI shims (consistency with auth DI)

**Problem:** The auth dependency `get_auth_functions()` uses `@lru_cache` so the
`AuthFunctions` dataclass is built once. The service DI shims
(`get_dummy_service_v1()`, `get_dummy_service_v2()`) rebuild the `DummyServiceV*`
dataclass on every call. The inconsistency contradicts the singleton-config
philosophy established in Epic 22.

**Action:** Add `@lru_cache` to `get_dummy_service_v1()` and
`get_dummy_service_v2()` in `services/v1/dummy_service.py` and
`services/v2/dummy_service.py`, matching the auth approach.

**Acceptance criteria:**
- Both service DI shims are decorated with `@lru_cache`.
- All quality checks pass.

### 26.6: Add parentheses to `except ValueError, TypeError:` in `logging_decorator.py`

**Problem:** Line 34 of `aop/logging_decorator.py` uses the bare-comma form
`except ValueError, TypeError:`, which is valid Python 3.14 (PEP 758) but reads
as a Python 2 bug to anyone unaware of PEP 758. Every other `except` with
multiple types in the codebase uses parentheses.

**Action:** Change to `except (ValueError, TypeError):` for clarity and
consistency.

**Acceptance criteria:**
- The `except` clause uses parenthesized tuple form.
- All quality checks pass.

---

## Epic 27 — Documentation, Naming & Script Alignment

Bring documentation, test file names, and scaffolding scripts into alignment with
the post-epic-25 codebase.

### 27.1: Fix PROJECT_CONTEXT.md internal contradictions

**Problem:** Several lines in `PROJECT_CONTEXT.md` reference patterns that no
longer exist:

| Line | Stale content | Should be |
|------|---------------|-----------|
| 92 | `PlainFormatter, JsonFormatter, SpanFilter, secret redaction` | `configure_logging(settings), structlog processor pipeline, secret redaction` (or equivalent reflecting the current structlog-based implementation) |
| 171 | `Models use alias_generator=_to_camel and populate_by_name=True` | `DTOs inherit from CamelCaseModel which uses pydantic.alias_generators.to_camel` (or remove the sentence, since line 176 already says this correctly) |

**Action:** Audit `PROJECT_CONTEXT.md` for any remaining references to
`PlainFormatter`, `JsonFormatter`, `SpanFilter`, `_to_camel` (as a custom
function), `AuthFacade`, `AuthProvider` ABC, `DummyServiceV*Contract`, or
`implementations/` subdirectory — and correct or remove them. Ensure no internal
contradictions remain.

**Acceptance criteria:**
- Zero references to the removed custom formatter classes, custom `_to_camel`
  function, facade, or ABC patterns in `PROJECT_CONTEXT.md`.
- The project structure tree and inline descriptions match the actual codebase.
- No internal contradictions (i.e. two sections describing the same thing
  differently).

### 27.2: Rename facade-named test files

**Problem:** `tests/auth/test_facade.py` and `tests/auth/test_facade_role_mapper.py`
reference the `AuthFacade` concept that was removed in Epic 24. The content is
correct (testing factory and `AuthFunctions`), but the filenames are misleading.

**Action:** Rename the files to reflect what they actually test:

| Current | Proposed |
|---------|----------|
| `tests/auth/test_facade.py` | `tests/auth/test_auth_functions.py` (or `test_get_auth.py`) |
| `tests/auth/test_facade_role_mapper.py` | `tests/auth/test_role_mapper.py` |

Update `PROJECT_CONTEXT.md`'s test structure tree to match the new names.

**Acceptance criteria:**
- No test file names reference "facade".
- `PROJECT_CONTEXT.md` test structure tree reflects the renamed files.
- All quality checks pass.

### 27.3: Update scaffolding scripts for current patterns

**Problem:** `scripts/build_template.py` and `scripts/remove_demo.py` still use
patterns from before epics 20–25:

- `from __future__ import annotations` (lines 14, 355 in `build_template.py`;
  line 10 in `remove_demo.py`).
- Custom `_to_camel` function definition and `alias_generator=_to_camel` in
  template output (`build_template.py` lines 644, 650).

This means newly scaffolded projects start with stale patterns that the archetype
itself has moved away from.

**Action:**
1. Remove `from __future__ import annotations` from both scripts.
2. Update `build_template.py` so that generated projects use `CamelCaseModel` with
   `pydantic.alias_generators.to_camel` instead of a custom `_to_camel` function.
3. Verify that `scripts/remove_demo.py` still works correctly against the current
   codebase structure (flat `services/v*/`, no `contracts/`, no `implementations/`,
   async patterns).
4. Verify that `scripts/build_template.py` produces a project that reflects the
   current conventions (async, structlog, functional patterns, `CamelCaseModel`).

**Acceptance criteria:**
- Zero `from __future__ import annotations` in `scripts/`.
- Generated template uses `CamelCaseModel` + `pydantic.alias_generators.to_camel`,
  not a custom `_to_camel`.
- `python3 scripts/remove_demo.py` runs successfully against the current codebase
  and all remaining tests pass afterward.
- `python3 scripts/build_template.py -n "Test Service" -o /tmp` produces a project
  that passes `ruff check` and `ruff format --check`.
- All quality checks pass on the archetype itself.

---

## Execution order

```
26 → 27
```

Epic 26 (code fixes) should go first because some changes (e.g. removing the
`type: ignore`) may affect the `PROJECT_CONTEXT.md` content updated in Epic 27.
Within each epic, stories are independent and may be executed in any order.
