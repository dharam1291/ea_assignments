"""
Agent protocol — the contract every agent implementation must satisfy.

In production, agents would wrap an LLM chain (e.g. LangGraph StateGraph)
that uses the system_prompt to steer generation and the tools for
structured function-calling.  The gateway invokes the agent through the
ToolAdapter layer; the agent protocol is the internal contract between
the registry and the adapter that knows how to execute the agent's tools.

Extension points for LLM integration:
  1. Add an `async def run(self, message: str, context: dict) -> dict`
     method that passes system_prompt + message to the LLM.
  2. Register tools as LangChain BaseTool instances for function-calling.
  3. Swap the MockToolAdapter for a chain-based adapter that calls
     `agent.run()` instead of directly invoking fixture data.
"""

from typing import Any, Protocol

from service.agents.tools.base import Tool


class BaseAgent(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def capabilities(self) -> list[str]: ...

    @property
    def tools(self) -> dict[str, Tool]: ...
