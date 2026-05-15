# bff

BMAD_books Backend-for-Frontend (OAuth client, books domain)

## Usage

### Using `uv`

Install dependencies:

```bash
uv sync
```

Run the application (SQLite in-memory by default):

```bash
uv run uvicorn bff.main:app --reload
```

Set `DB_DRIVER=mysql+pymysql` in `.env` for MariaDB (see `.env.example`).

### Using Docker

```bash
docker build -t bff .
docker run -p 8000:8000 bff
```

With custom configuration:

```bash
docker run --env-file .env -p 8000:8000 bff
```

### Using Docker Compose

```bash
docker compose -f compose/docker-compose.yaml up --build
```

Starts the application with MariaDB and the observability stack.

| Service | Port | Purpose |
|---------|------|---------|
| Application | 8000 | FastAPI (connected to MariaDB) |
| MariaDB | 3306 | Persistent database |
| OTEL Collector | 4317 | Receives OTLP traces |
| Jaeger | 16686 | Trace visualization |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3001 | Dashboards |

## Capabilities

Integrated enterprise capabilities, working together out of the box:

- **REST API** with CRUD and OpenAPI docs at `/docs`, `/redoc`
- **SQLModel ORM** (SQLite in-memory or MariaDB)
- **Configuration** via pydantic-settings with `.env` support
- **Structured errors** with enum codes and JSON responses
- **API versioning** (`/v1`, `/v2`) with `APIRouter`
- **AOP function logging** at the module level
- **OpenTelemetry tracing** with optional OTLP export
- **Prometheus metrics** (HTTP + custom counters) at `/metrics`
- **Auth and RBAC** with external IdP bearer-token validation
- **Containerization** via multi-stage Dockerfile
- **pytest suite** with >90% coverage (SQLite in-memory)
- **Code quality** via Ruff (Python 3.14)

## Testing

```bash
uv run pytest
uv run pytest --cov=bff --cov-report=term-missing
```

## Code Quality

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

## Extension Guide

To add a new resource (e.g. `Widget`):

**1. Entity and DTO** — `models/entities/widget.py` (ORM entity)
and `models/dto/v1/widget.py` (API shapes):

```python
# models/entities/widget.py
from sqlmodel import Field, SQLModel

class Widget(SQLModel, table=True):
    __tablename__ = "WIDGET"
    id: int | None = Field(default=None, primary_key=True)
    label: str
    weight: float | None = None

# models/dto/v1/widget.py
from bff.models.dto import CamelCaseModel

class GetWidgetsResponse(CamelCaseModel):
    label: str
    weight: float | None = None

class PostWidgetsRequest(CamelCaseModel):
    label: str
    weight: float | None = None

class PostWidgetsResponse(CamelCaseModel):
    label: str
    weight: float | None = None
```

**2. Constant** — `core/constants.py`:

```python
WIDGETS = ResourceDefinition(
    path="/widgets",
    name="Widgets",
    description="Widget resources",
)
```

**3. Service** — `services/v1/widget.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from bff.models.entities.widget import Widget

async def get_all_widgets(session: AsyncSession) -> list[Widget]:
    result = await session.execute(select(Widget))
    return list(result.scalars().all())

async def create_widget(session: AsyncSession, widget: Widget) -> Widget:
    session.add(widget)
    await session.commit()
    await session.refresh(widget)
    return widget
```

**4. AOP logging** — `services/__init__.py`:

```python
from bff.services.v1 import widget as v1_widget
apply_logging(v1_widget)
```

**5. Routes** — `api/v1/widget_routes.py`:

```python
from fastapi import APIRouter, Depends, status
from bff.core.constants import WIDGETS
from bff.factories.widget import (
    entity_to_get_response,
    entity_to_post_response,
    post_dto_to_entity,
)
from bff.models.dto.v1.widget import (
    GetWidgetsResponse,
    PostWidgetsRequest,
    PostWidgetsResponse,
)
from bff.services.factory import WidgetServiceV1
from bff.services.v1.widget_service import (
    get_widget_service_v1,
)

router = APIRouter(prefix=WIDGETS.path, tags=[WIDGETS.name])

@router.get("", response_model=list[GetWidgetsResponse])
async def list_widgets(
    svc: WidgetServiceV1 = Depends(get_widget_service_v1),
) -> list[GetWidgetsResponse]:
    entities = await svc.get_all_widgets()
    return [entity_to_get_response(e) for e in entities]

@router.post(
    "",
    response_model=PostWidgetsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_widget(
    widget: PostWidgetsRequest,
    svc: WidgetServiceV1 = Depends(get_widget_service_v1),
) -> PostWidgetsResponse:
    entity = post_dto_to_entity(widget)
    created = await svc.create_widget(entity)
    return entity_to_post_response(created)
```

**6. Register router** — `api/v1/__init__.py`:

```python
from bff.api.v1.widget_routes import (
    router as widget_router,
)
router.include_router(widget_router)
```

**7. Tests** — mirror the existing structure under `tests/`.
The `conftest.py` fixtures work for any new model.

New resources inherit tracing, metrics, error handling,
and AOP logging automatically.
