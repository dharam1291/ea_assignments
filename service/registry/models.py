from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRegistration:
    agent: Any
    capability: str
    required_scope: str
    tool_name: str
