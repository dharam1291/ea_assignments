"""
Billing agent — fixture-backed implementation of the BaseAgent protocol.

Loads its identity, system prompt, and capability declaration from an
externalized YAML config (prompts/billing_agent.yaml). In production,
the system_prompt would be passed to a LangGraph ReAct node alongside
the user's message; here the MockToolAdapter invokes the tool directly
using fixture data because the assessment prohibits LLM/network calls.

See base.py for the full rationale and migration path.
"""

import yaml
from pathlib import Path

from service.agents.tools.base import Tool
from service.agents.tools.billing_summary import BillingSummaryTool

_PROMPT_PATH = Path(__file__).parent / "prompts" / "billing_agent.yaml"


class BillingAgent:
    def __init__(self, fixture_data: dict[str, dict]) -> None:
        self._tool = BillingSummaryTool(fixture_data)
        self._prompt_config = yaml.safe_load(_PROMPT_PATH.read_text())

    @property
    def name(self) -> str:
        return self._prompt_config["agent_name"]

    @property
    def system_prompt(self) -> str:
        return self._prompt_config["system_prompt"]

    @property
    def capabilities(self) -> list[str]:
        return self._prompt_config["capabilities"]

    @property
    def tools(self) -> dict[str, Tool]:
        return {"billing_summary": self._tool}
