from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from service.core.config import settings


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str = Field(..., min_length=1, max_length=settings.max_conversation_id_length)
    capability: str = Field(..., min_length=1, max_length=settings.max_capability_length)
    message: str = Field(..., min_length=1, max_length=settings.max_message_length)
    simulation: str = Field(default="ok")

    @field_validator("conversation_id", "capability", "message")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must contain non-whitespace characters.")
        return v

    @field_validator("simulation")
    @classmethod
    def validate_simulation(cls, v: str) -> str:
        allowed = {"ok", "transient_then_ok", "transient_always", "permanent_error", "malformed_result", "timeout"}
        if v not in allowed:
            raise ValueError(f"simulation must be one of {sorted(allowed)}")
        return v


class InvokeSuccessResponse(BaseModel):
    request_id: str
    conversation_id: str
    tenant_id: str
    agent: str
    status: str
    result: dict[str, Any]


class ErrorDetail(BaseModel):
    code: str
    message: str


class InvokeErrorResponse(BaseModel):
    request_id: str
    conversation_id: str
    tenant_id: str
    agent: str
    status: str = "failed"
    error: ErrorDetail


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str = "ok"
