import asyncio
from typing import Any

from service.core.errors import PermanentError, TransientError


class MockToolAdapter:
    def __init__(
        self,
        tool_results: dict[str, dict[str, Any]],
        agents: dict[str, Any],
    ) -> None:
        self._tool_results = tool_results
        self._agents = agents

    async def invoke(
        self,
        agent_name: str,
        tool_name: str,
        tenant_id: str,
        simulation: str,
        attempt: int,
    ) -> dict[str, Any]:
        if simulation == "transient_then_ok":
            if attempt < 3:
                raise TransientError("Transient failure (simulated).")
            return self._get_result(agent_name, tenant_id)

        if simulation == "transient_always":
            raise TransientError("Transient failure (simulated).")

        if simulation == "permanent_error":
            raise PermanentError("Permanent failure (simulated).")

        if simulation == "malformed_result":
            return {"unexpected": True}

        if simulation == "timeout":
            await asyncio.sleep(2.0)
            return self._get_result(agent_name, tenant_id)

        return self._get_result(agent_name, tenant_id)

    def _get_result(self, agent_name: str, tenant_id: str) -> dict[str, Any]:
        agent = self._agents.get(agent_name)
        if agent is None:
            raise PermanentError(f"Agent not found.")
        capability = agent.capabilities[0]
        tenant_data = self._tool_results.get(tenant_id, {})
        result = tenant_data.get(capability)
        if result is None:
            raise PermanentError(f"No fixture data for tenant.")
        return dict(result)
