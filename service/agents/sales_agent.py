import yaml
from pathlib import Path

from service.agents.tools.base import Tool
from service.agents.tools.sales_offers import SalesOffersTool

_PROMPT_PATH = Path(__file__).parent / "prompts" / "sales_agent.yaml"


class SalesAgent:
    def __init__(self, fixture_data: dict[str, dict]) -> None:
        self._tool = SalesOffersTool(fixture_data)
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
        return {"sales_offers": self._tool}
