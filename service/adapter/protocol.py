from typing import Any, Protocol


class ToolAdapter(Protocol):
    async def invoke(
        self,
        agent_name: str,
        tool_name: str,
        tenant_id: str,
        simulation: str,
        attempt: int,
    ) -> dict[str, Any]: ...
