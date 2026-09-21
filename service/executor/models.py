from dataclasses import dataclass, field
from typing import Any

from service.traces.models import TraceEvent


@dataclass
class ExecutionResult:
    status: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 0
    duration_ms: float = 0.0
    events: list[TraceEvent] = field(default_factory=list)
