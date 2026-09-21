import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from service.api.dependencies import get_principal
from service.api.schemas import (
    ErrorDetail,
    HealthResponse,
    InvokeRequest,
    InvokeSuccessResponse,
)
from service.core.errors import AuthorizationError, CapabilityNotFoundError
from service.identity.models import Principal
from service.traces.models import ExecutionTrace

logger = logging.getLogger(__name__)

router = APIRouter()

_ERROR_STATUS_MAP = {
    "UPSTREAM_UNAVAILABLE": 503,
    "UPSTREAM_PERMANENT": 502,
    "INVALID_TOOL_RESULT": 502,
    "UPSTREAM_TIMEOUT": 504,
}


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


@router.post("/invoke", response_model=None)
async def invoke(
    body: InvokeRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
):
    request_id = f"req-{uuid.uuid4()}"
    registry = request.app.state.registry
    adapter = request.app.state.adapter
    engine = request.app.state.engine
    trace_store = request.app.state.trace_store

    logger.info(
        "Invoke started",
        extra={
            "extra_fields": {
                "request_id": request_id,
                "capability": body.capability,
                "user_id": principal.user_id,
                "tenant_id": principal.tenant_id,
            }
        },
    )

    registration = registry.resolve(body.capability)
    if registration is None:
        raise CapabilityNotFoundError()

    if not registry.check_scope(registration, principal):
        raise AuthorizationError()

    exec_result = await engine.execute(
        adapter=adapter,
        agent_name=registration.agent.name,
        tool_name=registration.tool_name,
        tenant_id=principal.tenant_id,
        capability=body.capability,
        simulation=body.simulation,
        request_id=request_id,
    )

    trace = ExecutionTrace(
        request_id=request_id,
        conversation_id=body.conversation_id,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        agent=registration.agent.name,
        capability=body.capability,
        status=exec_result.status,
        attempts=exec_result.attempts,
        duration_ms=exec_result.duration_ms,
        events=exec_result.events,
    )
    trace_store.store(trace)

    if exec_result.status == "completed":
        return InvokeSuccessResponse(
            request_id=request_id,
            conversation_id=body.conversation_id,
            tenant_id=principal.tenant_id,
            agent=registration.agent.name,
            status="completed",
            result=exec_result.result,
        )

    status_code = _ERROR_STATUS_MAP.get(exec_result.error_code, 502)
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": request_id,
            "conversation_id": body.conversation_id,
            "tenant_id": principal.tenant_id,
            "agent": registration.agent.name,
            "status": "failed",
            "error": {
                "code": exec_result.error_code,
                "message": exec_result.error_message,
            },
        },
    )


@router.get("/traces/{request_id}")
async def get_trace(
    request_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict:
    trace_store = request.app.state.trace_store
    trace = trace_store.get(request_id, principal.user_id, principal.tenant_id)
    if trace is None:
        from service.api.schemas import ErrorEnvelope

        raise CapabilityNotFoundError(message="Trace not found.")
    return trace.model_dump(mode="json")
