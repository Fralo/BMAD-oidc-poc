# PROJECT_CONTEXT

This document is the authoritative reference for LLM agents contributing to resource-server. It describes every capability, pattern, convention, and constraint in the project. Agents must not introduce technologies, libraries, or patterns that are not documented here without explicit human approval.

## Identity

- **Name:** resource-server
- **Version:** 0.1.0
- **Python:** >=3.14
- **Purpose:** Production-grade FastAPI reference implementation. The domain (a `/dummies` CRUD resource) is intentionally trivial; the value is in the proven integration of enterprise cross-cutting concerns. Designed as a copy-and-adapt template for new microservices.

## Technology Stack

All dependencies are declared in `pyproject.toml`. Do not add or replace dependencies without human approval.

### Runtime

| Library | Version constraint | Role |
|---|---|---|
| fastapi | >=0.135.1 | Web framework |
| uvicorn | >=0.41.0 | ASGI server |
| sqlmodel | >=0.0.37 | ORM for entities; Pydantic for DTOs (see Data Persistence) |
| aiosqlite | >=0.22 | Async SQLite driver (dev/test) |
| aiomysql | >=0.3 | Async MariaDB driver (production) |
| greenlet | >=3.0 | Required by SQLAlchemy async engine |
| pymysql | >=1.1.2 | MariaDB driver (pure Python, used transitively) |
| pydantic-settings | >=2.13.1 | Typed configuration from env / .env |
| opentelemetry-api, opentelemetry-sdk, opentelemetry-exporter-otlp, opentelemetry-instrumentation-fastapi | >=1.39.1 / >=0.60b1 | Distributed tracing |
| prometheus-fastapi-instrumentator | >=7.1.0 | HTTP metrics auto-instrumentation |
| prometheus_client | (transitive) | Custom metrics |
| PyJWT[crypto] | >=2.9.0 | JWT validation (Entra auth) |
| httpx | (transitive at runtime via auth) | Outbound HTTP for JWKS/token endpoints |

### Dev

| Library | Role |
|---|---|
| pytest >=8.0 | Test runner |
| pytest-asyncio >=0.25 | Async test support (`asyncio_mode = "auto"`) |
| pytest-cov >=6.0 | Coverage reporting |
| httpx >=0.28.1 | AsyncClient transport for tests |
| nest-asyncio | Async REPL support for interactive debugging |
| ruff >=0.15.4 | Linting and formatting |
| ty (version per lock file) | Type checking |

### Build and Tooling

| Tool | Role |
|---|---|
| uv | Dependency management, lock file, virtualenv, build backend (`uv_build`) |
| Docker (python:3.14-slim) | Multi-stage container image |
| Docker Compose | Local testing only (compose/ directory); not part of the product. |

## Project Structure

```
src/resource_server/
├── main.py                          # FastAPI app, lifespan, exception handlers, router registration, OTEL instrumentation
├── aop/
│   └── logging_decorator.py         # log_io decorator + apply_logging(module)
├── api/
│   ├── v1/
│   │   ├── __init__.py              # APIRouter(prefix="/v1"), includes resource routers
│   │   └── dummy_routes.py          # GET/POST/PUT /v1/dummies
│   └── v2/
│       ├── __init__.py              # APIRouter(prefix="/v2"), includes resource routers
│       └── dummy_routes.py          # GET/POST /v2/dummies (admin role on POST)
├── auth/
│   ├── contracts.py                 # Error types only (AuthError, UnauthorizedError, etc.)
│   ├── dependencies.py              # require_auth, require_role(Role), get_auth_functions DI shim
│   ├── entra.py                     # make_entra_auth(settings) -> AuthFunctions (closure factory)
│   ├── factory.py                   # get_auth(settings) -> AuthFunctions (dict-dispatch)
│   ├── models.py                    # Principal dataclass, Role StrEnum, AuthFunctions dataclass
│   ├── none.py                      # Plain async functions for AUTH_TYPE=none (dev bypass)
│   └── role_mapping.py              # identity_role_mapper(role) -> role (plain function)
├── core/
│   ├── config.py                    # AppSettings(BaseSettings) — all env vars
│   ├── constants.py                 # ResourceDefinition dataclass, DUMMIES, HEALTH_PATH
│   ├── database.py                  # get_engine(settings), get_session() generator
│   └── errors.py                    # ErrorCode enum, AppException, exception handlers
├── models/
│   ├── entities/                    # ORM-only: one file per entity (SQLModel, table=True)
│   │   └── dummy.py                 # Dummy entity
│   └── dto/                         # API request/response only; versioned by API version
│       └── v1/
│           └── dummy.py             # PostDummiesRequest, GetDummiesResponse, PostDummiesResponse, PutDummiesRequest (Pydantic, camelCase)
├── factories/                       # Entity ↔ DTO mapping (Pydantic-only: model_validate, model_dump)
│   └── dummy.py                    # entity_to_get_response, entity_to_post_response, post_dto_to_entity, put_dto_to_entity
├── observability/
│   ├── logging.py                   # configure_logging(settings), structlog processor pipeline, secret redaction
│   ├── otel.py                      # setup_otel(app, settings) -> TracerProvider
│   └── prometheus.py                # Metrics dataclass, dummies_created_total counter, setup_prometheus(app)
└── services/
    ├── __init__.py                  # Imports all service modules and calls apply_logging() on each
    ├── factory.py                   # DummyServiceV1/V2 dataclasses; build_*_service(settings) dict-dispatch
    ├── v1/
    │   ├── dummy.py                 # Plain functions: get_all_dummies, create_dummy, update_dummy, …
    │   ├── mock_dummy.py            # Plain mock functions returning static data (no DB)
    │   └── dummy_service.py        # get_dummy_service_v1() DI shim
    └── v2/
        ├── dummy.py                 # Plain functions: get_all_dummies, create_dummy
        ├── mock_dummy.py            # Plain mock functions returning static data (no DB)
        └── dummy_service.py         # get_dummy_service_v2() DI shim

tests/
├── conftest.py                      # SQLite in-memory engine, session, TestClient with DI override
├── aop/
│   └── test_logging_decorator.py
├── api/
│   ├── test_health.py
│   ├── test_dummy_routes.py         # v1 endpoints
│   └── test_v2_dummy_routes.py      # v2 endpoints
├── auth/
│   ├── conftest.py                  # RSA keypair, JWKS, JWT signing fixtures (synthetic IdP)
│   ├── test_external_provider.py
│   ├── test_auth_functions.py       # Tests for get_auth factory / AuthFunctions
│   ├── test_role_mapper.py          # Tests for role_mapper in AuthFunctions
│   ├── test_factory_and_none_provider.py
│   ├── test_entra_integration.py    # Full Entra flow with intercepted HTTP
│   └── test_role_mapping_providers.py
├── core/
│   ├── test_config.py
│   └── test_errors.py
├── observability/
│   ├── test_logging.py
│   └── test_prometheus.py
└── services/
    ├── v1/
    │   └── test_dummy_service.py
    └── v2/
        └── test_dummy_service.py

compose/
├── .env                             # Service-level env vars for Docker Compose
├── docker-compose.yaml              # Local testing only: mariadb, resource-server, grafana, jaeger, otel-collector, prometheus
├── mariadb/
│   └── init/                        # MariaDB native init (runs on first start only)
│       └── schema.sql               # DUMMY and other app tables; DB name must match .env DATABASE_NAME
└── observability/
    ├── otel-collector-config.yaml
    └── prometheus.yaml

scripts/
├── remove_demo.py                   # Strip Dummy CRUD demo boilerplate
└── build_template.py                # Generate Cookiecutter template from reference implementation
```

## Capabilities and Implementation Details

### 1. REST API

Endpoints are defined in route modules under `api/v1/` and `api/v2/`. Each version has its own `APIRouter` with a prefix (`/v1`, `/v2`). Infrastructure endpoints (`/health`, `/metrics`, `/docs`, `/redoc`) remain at the root, unversioned.

Current endpoints:

| Method | Path | Auth |
|---|---|---|
| GET | `/health` | None |
| GET | `/metrics` | None |
| GET | `/docs` | None |
| GET | `/redoc` | None |
| GET | `/v1/dummies` | None |
| POST | `/v1/dummies` | `require_auth` |
| PUT | `/v1/dummies/{uuid}` | None |
| GET | `/v2/dummies` | None |
| POST | `/v2/dummies` | `require_role(Role.ADMIN)` |

All request/response payloads are JSON. DTOs inherit from `CamelCaseModel` which uses `pydantic.alias_generators.to_camel` and `populate_by_name=True` for camelCase serialization.

### 2. Data Persistence

- **Entities:** SQLModel classes with `table=True` live in `models/entities/` (one file per entity). They are used only for persistence and service-layer logic; they are not used as FastAPI request/response models.
- **DTOs:** Plain Pydantic models (no `table=True`) live in `models/dto/<version>/` (e.g. `v1/`). They define API request/response shapes with camelCase serialization and are used only at the route boundary. All DTOs inherit from `CamelCaseModel` (defined in `models/dto/__init__.py`), which sets `alias_generator=pydantic.alias_generators.to_camel` and `populate_by_name=True`. Do not add `model_config` directly to individual DTO classes; inherit from `CamelCaseModel` instead. Entity classes must **not** carry `alias_generator` — that is a DTO/serialization concern only.
- **Factories:** The `factories/` package (one module per entity) provides entity ↔ DTO conversion using only Pydantic: `model_validate()` and `model_dump()`. No separate mapping library. Routes call factory functions at the boundary; services accept and return entities only.
- **Client identity (UUID vs ID):** Entities that need a stable, client-facing identifier have a `uuid` property (string, UUID format). Response DTOs expose `uuid` and **never** expose the internal persistence `id`. This keeps persistence details hidden and gives clients a stable reference for updates and links.
- **Update-by-UUID pattern (PUT):** For `PUT /v1/<resource>/{uuid}` with a body that includes `uuid` and updatable fields, follow this split so the route stays thin and the service owns resolution (IMPORTANT: this applies to mutations targeting entities-with-id in general, not just PUTs):
  - **Route:** Validate that path `uuid` and body `uuid` match (return **400 Bad Request** if not). Convert the request DTO to an entity via the factory, call the service update function with that entity, then map the returned entity to the response DTO. The route must **not** fetch by UUID or handle 404; the service does that.
  - **Factory:** The PUT request → entity factory function takes only the DTO (e.g. `put_dto_to_entity(dto: PutXxxRequest) -> Entity`). It returns an entity with `uuid`, and updatable fields (e.g. `name`, `description`) but **no** `id` (leave `id` unset / `None`). The factory must not take a session or existing entity; it only maps DTO → entity.
  - **Service:** The update function (e.g. `update_dummy(session, entity)`) accepts an entity. If the entity has **no** `id`, the service fetches the existing row by `entity.uuid`; if not found, it raises `AppException(ErrorCode.<RESOURCE>_NOT_FOUND)` so the app handler returns **404**. If found, the service builds an entity with the resolved `id` and `uuid` plus the incoming updatable fields, then performs the update (e.g. merge and commit). If the entity already has an `id`, the service performs the update as usual. This keeps "resolve by UUID or fail" inside the service; the route stays validation + convert + call + respond.
- **Database connection:** Configured by an optional `DATABASE_URL` environment variable. When unset or empty/whitespace, the application uses SQLite in-memory (`sqlite+aiosqlite://`). When set, the URL is automatically rewritten to use the async driver (`mysql+aiomysql://` for MariaDB, `sqlite+aiosqlite://` for SQLite) at engine creation. Special characters (e.g. `@`, `:`, `/`, `%`) used within any component of `DATABASE_URL` must be percent-encoded where applicable.
- **Async engine and session:** `core/database.py` uses `create_async_engine`, `async_sessionmaker`, and `AsyncSession` from `sqlalchemy.ext.asyncio`. The module-level `get_engine()` returns an `AsyncEngine`; `get_session()` is an async generator yielding `AsyncSession` instances, injected into routes via `Depends(get_session)`. All service functions and route handlers are `async def` and `await` session operations (`await session.execute(...)`, `await session.commit()`, `await session.refresh(...)`).
- **Schema management:** Table creation is a **local/dev-only** feature. The application runs `SQLModel.metadata.create_all` via `conn.run_sync()` inside the async lifespan **only when the effective database is SQLite**. For any other backend (e.g. MariaDB in Compose or production), the app does not create or alter tables; schema is provided by the environment (e.g. MariaDB’s native init via `compose/mariadb/init/schema.sql`). No migration tool (Alembic) is in scope.

### 3. Configuration Management

`core/config.py` defines `AppSettings(BaseSettings)` using pydantic-settings. All settings load from environment variables with `.env` file fallback. The application validates at startup and fails fast on invalid values.

Every configurable value is a field on `AppSettings`. New settings must be added as fields on this class. See `.env.example` for the complete reference.

### 4. Structured Error Handling

`core/errors.py` defines:

- `ErrorCode` enum — each member carries `(code, message, http_status)`. This is the single source of truth for all error codes.
- `AppException(error_code, detail)` — raised anywhere in the application.
- Two global exception handlers registered in `main.py`: `AppException` and `RequestValidationError`.

All error responses use the shape `{"errorCode": str, "message": str, "detail": any}`.

New error codes must be added to the `ErrorCode` enum. Raise `AppException(ErrorCode.XXX)` — never return raw `JSONResponse` for errors.

### 5. API Versioning

Versioning uses URL prefixes via `APIRouter(prefix="/v1")` and `APIRouter(prefix="/v2")`. Each version has its own routes module and service module. Version routers are included in `main.py`.

To add a new version: create `api/v3/`, `services/v3/`, register the router in `main.py`, and wire AOP logging in `services/__init__.py`.

### 6. AOP Function Logging

`aop/logging_decorator.py` provides:

- `log_io(func)` — decorator that logs inputs at DEBUG, return values at DEBUG, and exceptions at ERROR. Detects coroutine functions via `inspect.iscoroutinefunction` and returns an async wrapper for `async def` functions, a sync wrapper for regular functions. Exception-path logging ensures failures surface in production logs without requiring DEBUG verbosity.
- `apply_logging(module)` — programmatically wraps all public functions defined in a module with `log_io` at import time. Only functions whose `__module__` matches the target are wrapped (re-exported imports are skipped). Works transparently with both sync and async functions. Individual service functions carry no decorator annotation.

`services/__init__.py` imports every service module and calls `apply_logging()` on each. New service modules must be added there.

### 7. OpenTelemetry Distributed Tracing

`observability/otel.py` configures a `TracerProvider` with an optional `OTLPSpanExporter` (gRPC). `FastAPIInstrumentor.instrument_app()` adds spans to all HTTP requests (the `/metrics` endpoint is excluded). The tracer provider is shut down in the lifespan exit.

Controlled by `OTEL_EXPORT_ENABLED` (default `false`) and `OTEL_EXPORTER_ENDPOINT`.

### 8. Prometheus Metrics

`observability/prometheus.py` provides:

- `Instrumentator().instrument(app).expose(app)` — auto-instruments HTTP request count, latency, and status at `/metrics`.
- `metrics.counters.dummies_created_total` — a custom `Counter` with `api_version` label, incremented in service functions after successful creation.

The `Metrics` and `Counters` dataclasses hold all custom metrics. New custom metrics must be added as fields on these dataclasses and instantiated at module level.

### 9. Authentication and Authorization

Architecture: plain function modules (`auth/none.py`, `auth/entra.py`) → `AuthFunctions` dataclass (returned by `auth/factory.py`) → FastAPI dependencies (`require_auth`, `require_role`).

**`AuthFunctions` dataclass** (defined in `auth/models.py`): holds four callable fields — `authenticate_bearer_token`, `get_client_credentials_access_token`, `get_on_behalf_of_access_token`, `role_mapper`. Created by `get_auth(settings)` and injected via `get_auth_functions()`.

**Auth modes** (controlled by `AUTH_TYPE`):

- `none`: `auth/none.py` exports plain async functions returning a synthetic principal with all roles. No token validation.
- `entra`: `auth/entra.py` exports `make_entra_auth(settings) -> AuthFunctions`. Uses a closure factory that captures JWKS cache and settings in closure scope. Validates bearer JWT (signature via JWKS, standard claims, issuer, optional audience) and supports client_credentials and OBO token acquisition.

**Role model:** `Role` is a `StrEnum` with members `ADMIN`, `WRITER`, `READER`. `auth/role_mapping.py` exports `identity_role_mapper(role: str) -> str` (identity mapping). The `AuthFunctions.role_mapper` field holds the active mapping function; custom mappers can be injected for testing by overriding `get_auth_functions`.

**Dependencies:**

- `require_auth` — ensures a valid `Principal` exists (any authenticated user).
- `require_role(Role.XXX)` — returns a dependency that additionally checks the principal has the required role via `auth_fns.role_mapper`.

**Error sanitization:** Auth failures raise `AppException(ErrorCode.UNAUTHORIZED)` or `AppException(ErrorCode.FORBIDDEN)`. Provider-specific details are logged server-side only, never exposed to clients.

**Factory:** `get_auth(settings)` in `auth/factory.py` uses dict-dispatch on `settings.auth_type` to return a configured `AuthFunctions` instance.

### 10. Profile and Service Dispatch

Service implementations are selected at runtime by a **profile** environment variable, enabling mock implementations for local or profile-based testing without touching the database or external systems.

**Profile:**

- **Environment variable:** `PROFILE` (optional). Values: `"default"` | `"mock"`. Default when unset: `"default"`.
- **Semantics:** `default` — wire the real (database-backed) functions for each service. `mock` — wire the mock functions for each service (static/hard-coded data; no database or external calls).
- **Configuration:** `profile` is a typed field on `AppSettings` (e.g. `Literal["default", "mock"]`). See `.env.example` for reference.

**Functional dispatch pattern:**

- **Service module:** For each logical service and version, one module exports plain functions (e.g. `services/v1/dummy.py` → `get_all_dummies(session, ...)`, `create_dummy(session, dummy)`, `update_dummy(session, entity)`). `AsyncSession` is the first parameter; this is an implementation detail hidden behind `functools.partial` at the DI boundary.
- **Mock module:** A sibling module exports session-free function signatures with static/hard-coded data and no database calls (e.g. `services/v1/mock_dummy.py`). Used when `profile == "mock"`. Mock functions do not accept `session` — they have no use for it.
- **Service dataclass:** `services/factory.py` defines a `@dataclass` (e.g. `DummyServiceV1`) with typed callable fields that are session-free (e.g. `get_all_dummies: Callable[[], Coroutine[Any, Any, list[Dummy]]]`). Routes type-annotate their `svc` parameter against this dataclass.
- **Factory:** `build_dummy_service_v1(settings, session=None) -> DummyServiceV1` accepts an optional `AsyncSession`. For `profile == "mock"` it assembles mock functions directly. For `profile == "default"` it uses `functools.partial(fn, session)` to bind the session into each real function, producing session-free callables. Function references are read at call time, so AOP wrapping applied at import time is preserved.
- **DI shim:** `services/v1/dummy_service.py` exports `async def get_dummy_service_v1(session: AsyncSession = Depends(get_session)) -> DummyServiceV1`. It is called per request via `Depends` and is not cached (`@lru_cache` is absent — the session is per-request).
- **AOP:** `services/__init__.py` imports all service modules and calls `apply_logging()` on each, wrapping their public functions with `log_io`.

**Application-wide rule:** Every service that encapsulates business logic or data access has (1) a plain-function default module, (2) a plain-function mock module, (3) a factory that assembles and selects by `profile`, and (4) a DI shim. New services must follow this pattern.

### 11. Containerization

**Dockerfile:** Multi-stage. Builder uses `uv` (copied from `ghcr.io/astral-sh/uv:0.10.7`) to resolve and install locked dependencies. Runtime uses `python:3.14-slim` with a non-root `app` user. No dev dependencies in the final image.

IMPORTANT: the **Docker Compose** project (`compose/docker-compose.yaml`) is merely for local testing purposes, its technologies and components are not to be considered part of the product itself - this application is meant to be installed _anywhere_ as a container.

### 12. Testing

- **Framework:** pytest with `testpaths=["tests"]`, `pythonpath=["src"]`, and `asyncio_mode = "auto"` (via pytest-asyncio). All test functions that use async fixtures are `async def`; the `auto` mode eliminates the need for `@pytest.mark.asyncio` on individual tests.
- **Database:** Async SQLite in-memory (`sqlite+aiosqlite://`) with `StaticPool`. The `engine` fixture uses `create_async_engine`; the `session` fixture uses `async_sessionmaker` yielding `AsyncSession`. Tests override `get_session` via `app.dependency_overrides` with an async generator.
- **Client:** Tests use `httpx.AsyncClient` with `ASGITransport(app=app)` instead of `TestClient`. All HTTP assertions use `await client.get(...)`, `await client.post(...)`, etc.
- **Auth in tests:** `AUTH_TYPE=none` is set via `os.environ.setdefault` in `tests/conftest.py`. Auth integration tests in `tests/auth/` use a synthetic IdP: test-generated RSA keypair, JWKS fixture, JWT signing helper, monkeypatched HTTP calls. Auth test fixtures use `AsyncClient` and async engine/session.
- **Coverage target:** >90%.
- **Test organization mirrors source:** `tests/api/`, `tests/auth/`, `tests/core/`, `tests/services/`, `tests/aop/`, `tests/observability/`.

### 13. Code Quality

Type checking is enforced with Astral's ty, targeting the project's Python version (3.14). Code quality is enforced by three commands: **ruff check**, **ruff format --check**, and **ty check**. Quality checks are defined as: running these three commands plus the full test suite; all must pass before commit.

**Ruff** is configured in `pyproject.toml`:

- `target-version = "py314"`
- `line-length = 88`
- Lint rules: `E`, `W`, `F`, `I`, `N`, `UP`, `B`, `SIM`
- `extend-immutable-calls = ["fastapi.Depends", "Depends"]`
- `known-first-party = ["resource_server"]`

**ty** is configured in `pyproject.toml` under `[tool.ty]` with `python-version = "3.14"` and `include = ["src", "tests"]`.

### 14. Cookiecutter Scaffolding

`scripts/build_template.py` generates a new project in one shot. Internally it builds a Cookiecutter template in a temporary directory (applying text substitutions, directory renames, and archetype-specific exclusions), invokes `cookiecutter --no-input`, and delivers the result to the user-specified output directory.

The generated template includes a `hooks/post_gen_project.py` that optionally strips the Dummy CRUD demo when `--no-demo` is passed, reusing the same removal logic as `scripts/remove_demo.py`.

**CLI flags:** `-n`/`--name` (required), `-o`/`--output` (required), `--description`, `--author`, `--email`, `--no-demo`, `--force`.

**Usage:**

```bash
python3 scripts/build_template.py -n "Order Service" -o ~/projects
```

## Conventions and Patterns

### DTO naming (mandatory)

Web DTOs **must** follow this pattern: **`<Method><Resource><Request | Response>`**

- **Method:** HTTP method in PascalCase (e.g. `Get`, `Post`, `Put`, `Patch`, `Delete`).
- **Resource:** Plural resource name in PascalCase, matching the API path (e.g. `Dummies` for `/dummies`).
- **Suffix:** `Request` for request bodies, `Response` for response bodies.

**Examples:** `PostDummiesRequest` (body for `POST /dummies`), `GetDummiesResponse` (item shape for `GET /dummies` or single-item response), `PostDummiesResponse` (body of `POST /dummies` response). Do not name DTOs after the entity (e.g. avoid `DummyCreate`, `DummyResponse`).

### Module organization

- One entity per file in `models/entities/` (SQLModel, table=True). Entity classes must **not** carry `alias_generator`. One resource’s DTOs per file in `models/dto/<version>/` (e.g. `v1/`), using the `<Method><Resource><Request|Response>` naming pattern; all DTO classes inherit from `CamelCaseModel` (in `models/dto/__init__.py`). One factory module per entity in `factories/` (entity ↔ DTO using Pydantic only).
- One resource's routes per file in `api/v{n}/`. Routes use DTOs for request/response and call factory functions to convert to/from entities. Routes depend on service dataclasses (e.g. `DummyServiceV1`) via DI (`Depends(get_dummy_service_v1)` / `Depends(get_dummy_service_v2)`).
- **Service modules (flat):** For each version and resource, one default module and one mock module directly in `services/v{n}/` (e.g. `dummy.py`, `mock_dummy.py`). No subdirectory nesting within `services/v{n}/`. Each module exports plain functions.
- **Service dataclass:** `services/factory.py` defines `DummyServiceV1` / `DummyServiceV2` as frozen `@dataclass` with typed callable fields. The factory functions assemble these by reading from the appropriate module based on `settings.profile`.
- DI shims in `services/v{n}/dummy_service.py` call the factory per request.
- The version router `__init__.py` aggregates resource routers.
- `services/__init__.py` imports all service modules and applies `apply_logging()` to each.

### Constants

- All resource paths, names, and descriptions are `ResourceDefinition` instances in `core/constants.py`.
- `HEALTH_PATH` is a plain string constant.
- No string literals for paths or resource names in route/service code.

### Configuration

- Every configurable value is a typed field on `AppSettings`.
- Environment variable names match field names in UPPER_CASE.
- Defaults are provided for all fields except auth-specific fields required when `AUTH_TYPE=entra`.
- **Profile:** Optional `PROFILE` with values `"default"` | `"mock"` (default `"default"`) drives which service functions are wired (see §11 Profile and Service Dispatch).

### Error handling

- All error codes live in the `ErrorCode` enum.
- Application code raises `AppException(ErrorCode.XXX, detail=...)`.
- Auth code raises `AuthError` subclasses internally; `dependencies.py` catches and translates them to `AppException`.
- Never return raw `JSONResponse` for error cases.

### Dependency injection

- Database sessions: `Depends(get_session)` yields `AsyncSession`. Routes no longer depend on the session directly — session injection happens in the DI shim, which binds it into the service via `functools.partial`.
- Auth: `Depends(require_auth)` or `Depends(require_role(Role.XXX))`. Auth functions injected via `Depends(get_auth_functions)` (returns `AuthFunctions` dataclass).
- **Services:** Routes depend on a service dataclass (e.g. `DummyServiceV1`) via a dependency that calls the factory (`Depends(get_dummy_service_v1)` or `Depends(get_dummy_service_v2)`). The DI shim receives the session via `Depends(get_session)` and passes it to the factory, which binds it with `functools.partial`. Routes call session-free service methods: `await svc.get_all_dummies()`, `await svc.create_dummy(entity)`, `await svc.update_dummy(entity)`.
- All DI-based dependencies are overridable in tests via `app.dependency_overrides`.

### Testing

- Every new route needs endpoint tests in `tests/api/`.
- Every new service needs unit tests in `tests/services/`.
- Use the existing `client` and `session` fixtures from `tests/conftest.py`.
- Auth-related tests go in `tests/auth/` and use the synthetic IdP fixtures from `tests/auth/conftest.py`.
- Service and route tests may override the service dependency (e.g. with the default function module and a session) or set `PROFILE`; see §11 Profile and Service Dispatch.

### Code style

- No `from __future__ import annotations` — the project targets Python >=3.14 where this is a no-op.
- All route handlers and service functions are `async def`. Use `await` for all session operations and service calls.
- All imports at module level; no `if TYPE_CHECKING:` guards.
- No code comments except where they explain non-obvious intent.
- No dead code or placeholder implementations.
- camelCase API responses via `CamelCaseModel` base class (see § Data Persistence / DTO conventions below).

### Logging

- `configure_logging(settings)` in `observability/logging.py` is called once in the lifespan. It configures the root logger with a structlog `ProcessorFormatter` and a pre-chain of processors: `add_log_level`, `add_logger_name`, timestamp injection, trace-context injection, and exc_info extraction.
- `LOG_MODE` (`plain`/`json`, default `plain`) selects the renderer; any value other than `plain` uses the JSON renderer.
- Plain format: UTC ISO-8601 timestamp, `[traceId]`, `[spanId]`, level, logger name, message. Exception rendering shows type and message only.
- JSON format: one NDJSON object per line with camelCase fields (`timestamp`, `level`, `logger`, `message`, `traceId`, `spanId`). Exceptions add `exceptionType`, `exceptionMessage`, `stackTrace`.
- The `_inject_trace_context` processor injects `traceId` and `spanId` from the current OpenTelemetry span context into every log event; `NO_TRACE_ID`/`NO_SPAN_ID` when no trace is active.
- Baseline secret redaction masks obvious sensitive values (passwords, tokens, API keys, authorization headers) in both modes.
- Modules obtain loggers via `logging.getLogger(__name__)`.
- AOP logging is at DEBUG level for I/O and ERROR level for exceptions (with `exc_info=True`); application-level logging in services uses INFO.

## Anti-Patterns to Avoid

- Do not add global middleware for auth — use explicit `Depends()` per route.
- Do not scatter string literals for paths or error codes — use `core/constants.py` and `ErrorCode`.
- Do not create new settings outside `AppSettings` — add fields there.
- Do not add Alembic or database migration tooling — local schema via `create_all` (SQLite only); other backends use their own init (e.g. `compose/mariadb/init/schema.sql`).
- Do not add a local token-issuance endpoint — auth is external IdP only.
- Do not add libraries not listed in the technology stack without human approval.
- Do not add code comments that merely narrate what the code does.
- Do not add `from __future__ import annotations` — it is a no-op on Python 3.14 and misleads contributors.
- Do not use synchronous `def` for route handlers or service functions — all must be `async def`. Use `await` for all session and service operations.
- Do not use synchronous `Session` or `create_engine` from SQLAlchemy/SQLModel — use `AsyncSession`, `async_sessionmaker`, and `create_async_engine` from `sqlalchemy.ext.asyncio`.
- Do not modify `tests/conftest.py` fixtures to be resource-specific — they are generic by design.
- Do not name web DTOs after the entity (e.g. `DummyCreate`, `WidgetResponse`) — use the mandatory pattern `<Method><Resource><Request|Response>` (e.g. `PostDummiesRequest`, `GetDummiesResponse`).
- Do not use ABCs or class hierarchies for service implementations — use plain function modules and a service dataclass.
- Do not add a new service without a default function module, a mock function module, and a factory that assembles and dispatches by profile — the pattern is mandatory for all services.

## Adding a New Resource

To add a new resource (e.g., `Widget`):

1. **Entity:** Create `models/entities/widget.py` with `class Widget(SQLModel, table=True)` and `__tablename__`. This is the ORM model only; it is not used as a FastAPI request/response model. Do **not** add `alias_generator` to entity classes. For resources that need a stable, client-facing identifier, add a `uuid` field (string, UUID format) on the entity.
2. **DTOs:** Create `models/dto/v1/widget.py` with Pydantic models inheriting from `CamelCaseModel` (imported from `resource_server.models.dto`), following the **`<Method><Resource><Request|Response>`** naming pattern (e.g. `PostWidgetsRequest`, `GetWidgetsResponse`, `PostWidgetsResponse`). `CamelCaseModel` provides camelCase serialization via `pydantic.alias_generators.to_camel` and `populate_by_name=True`. Response DTOs must include `uuid` (when the entity has one) and **must not** include the internal `id`.
3. **Factory:** Create `factories/widget.py` with `entity_to_dto(entity) -> GetWidgetsResponse` (or the appropriate response type) and `dto_to_entity(dto: PostWidgetsRequest) -> Widget` using only Pydantic (`model_validate`, `model_dump`). For update (PUT): add `put_dto_to_entity(dto: PutWidgetsRequest) -> Widget` that returns a `Widget` with `uuid` and updatable fields from the DTO but **no** `id` (see **Update-by-UUID pattern** in §2 Data Persistence). The service will resolve by UUID when `id` is missing.
4. **Constant:** Add `WIDGETS = ResourceDefinition(...)` to `core/constants.py`.
5. **Service dataclass:** Add a `@dataclass(frozen=True, kw_only=True)` class (e.g. `WidgetServiceV1`) to `services/factory.py` with session-free typed `Callable` fields (e.g. `get_all: Callable[[], Coroutine[Any, Any, list[Widget]]]`, `create: Callable[[Widget], Coroutine[Any, Any, Widget]]`). The session is bound at the DI boundary via `functools.partial`; it is not part of the contract.
6. **Default module:** Create `services/v1/widget.py` with `async def` functions implementing real database access using `AsyncSession` and `await`. For update: when `entity.id` is None, fetch by `entity.uuid`; if not found, raise `AppException(ErrorCode.WIDGET_NOT_FOUND)`; otherwise resolve and update (see **Update-by-UUID pattern** in §2 Data Persistence).
7. **Mock module:** Create `services/v1/mock_widget.py` with session-free `async def` function signatures and static/hard-coded return values (no database or external calls, no `session` parameter).
8. **Factory and DI:** Add `build_widget_service_v1(settings: AppSettings, session: AsyncSession | None = None) -> WidgetServiceV1` in `services/factory.py`. For `profile == "mock"` assemble with mock functions directly; for `profile == "default"` use `partial(widget.<fn>, session)` for each callable field. Expose a per-request DI shim `async def get_widget_service_v1(session: AsyncSession = Depends(get_session)) -> WidgetServiceV1` in `services/v1/widget_service.py` (no `@lru_cache`). Use `Depends(get_widget_service_v1)` in routes.
9. **AOP:** Import and `apply_logging()` the new modules in `services/__init__.py`.
10. **Routes:** Create `api/v1/widget_routes.py` with `APIRouter(prefix=WIDGETS.path, tags=[WIDGETS.name])`. All route handlers are `async def` and depend on the service dataclass via `Depends(get_widget_service_v1)`. Do **not** add `Depends(get_session)` to routes — the session is already bound in the DI shim. Use DTOs for request body and response model; call factory to convert request DTO → entity for service and `await` session-free service calls (e.g. `await svc.get_all()`, `await svc.create(entity)`), then entity → response DTO for responses. Add auth as needed. **If the resource supports PUT (update):** use a path like `PUT /v1/widgets/{uuid}` and a request body that includes `uuid` plus updatable fields. In the route: validate that path `uuid` and body `uuid` match (return **400 Bad Request** if not); call the factory to convert the body DTO to an entity (no `id`); `await svc.update(entity)`; map the returned entity to the response DTO. Do **not** fetch by UUID or handle 404 in the route — the service does that (see **Update-by-UUID pattern** in §2 Data Persistence).
11. **Router registration:** Include the widget router in `api/v1/__init__.py`.
12. **Tests:** Add `tests/api/test_widget_routes.py` and `tests/services/v1/test_widget_service.py` (and tests for mock vs default behaviour when appropriate) using existing async fixtures. All tests that use `client` or `session` are `async def`. Service tests call functions from the service module directly (e.g. `await widget.get_all(session)`).
13. **Custom metrics (if needed):** Add counters to the `Counters` dataclass in `observability/prometheus.py`.

The new resource automatically inherits OpenTelemetry tracing, Prometheus HTTP metrics, structured error handling, and the configured auth mode.
