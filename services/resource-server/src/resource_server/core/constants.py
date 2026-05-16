from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ResourceDefinition:
    path: str
    name: str
    description: str


HEALTH_PATH = "/health"
