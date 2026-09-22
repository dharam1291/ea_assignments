"""
Agent protocol — the contract every agent implementation must satisfy.

WHY MOCK AGENTS INSTEAD OF LANGCHAIN / LANGGRAPH
─────────────────────────────────────────────────
The assessment explicitly prohibits outbound network access:
  • ASSESSMENT.md line 38:  "No real MCP server, model, browser ... is required."
  • ASSESSMENT.md line 153: "No token counts are expected because no LLM is called."
  • ASSESSMENT.md line 183: "no outbound network access once dependencies are installed"
  • Docker test contract:   `docker run --rm --network none ...`

A real LangChain/LangGraph agent would call an LLM API (OpenAI, Anthropic, etc.)
on every invocation, which violates all four constraints. Therefore agents use
fixture data through the MockToolAdapter instead of an LLM chain.

PRODUCTION MIGRATION TO LANGGRAPH
──────────────────────────────────
The protocol is deliberately shaped so that swapping to LangGraph requires
no changes outside this package:

  1. SYSTEM PROMPTS are already externalized in YAML (agents/prompts/*.yaml),
     ready to be passed to ChatModel as the system message.

  2. TOOLS follow a protocol (agents/tools/base.py) that maps 1:1 to
     LangChain's BaseTool interface — add @tool decorator or subclass.

  3. Each agent exposes `system_prompt` + `tools` — a LangGraph StateGraph
     node would consume both:

         from langgraph.graph import StateGraph
         graph = StateGraph(AgentState)
         graph.add_node("agent", create_react_agent(llm, agent.tools))

  4. The ToolAdapter layer (adapter/) is the ONLY integration point.
     Replace MockToolAdapter with a LangGraphAdapter that calls
     `graph.invoke({"messages": [system_prompt, user_message]})`.

  5. The execution engine, retry policy, trace store, identity resolution,
     and API layer remain completely untouched.

This design keeps the gateway's execution harness (retry, timeout, tracing,
auth) fully testable and deterministic while making the LLM integration a
single-adapter swap when network access is available.
"""

from typing import Any, Protocol

from service.agents.tools.base import Tool


class BaseAgent(Protocol):
    """
    Structural typing contract for agents.

    Any class with these four properties satisfies the protocol — no
    inheritance required. This enables both mock agents (fixture-backed)
    and future LLM-backed agents (LangGraph StateGraph) to be used
    interchangeably by the registry and adapter layers.
    """

    @property
    def name(self) -> str: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def capabilities(self) -> list[str]: ...

    @property
    def tools(self) -> dict[str, Tool]: ...
