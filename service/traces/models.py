from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: str
    attempt: int
    code: str | None = None
    delay_ms: float | None = None


class ExecutionTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    conversation_id: str
    tenant_id: str
    user_id: str
    agent: str
    capability: str
    status: str
    attempts: int
    duration_ms: float
    events: list[TraceEvent]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
