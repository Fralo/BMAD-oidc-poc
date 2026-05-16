from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelCaseModel(BaseModel):
    """Base class for all DTOs; provides camelCase aliases and name-based population."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
