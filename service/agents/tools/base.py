from typing import Any, Protocol

from pydantic import BaseModel


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def result_schema(self) -> type[BaseModel]: ...

    def get_fixture_result(self, tenant_id: str) -> dict[str, Any]: ...
