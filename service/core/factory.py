"""
Application factory — wires all components and returns a configured FastAPI instance.

Swap any layer by passing an alternative implementation:
  - identity_resolver: OIDC-backed resolver in production
  - adapter:           MCP client adapter for remote tool servers
  - sleep_fn:          deterministic clock for tests
"""

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from service.adapter.mock_adapter import MockToolAdapter
from service.agents.billing_agent import BillingAgent
from service.agents.sales_agent import SalesAgent
from service.api.middleware import register_middleware
from service.api.routes import router
from service.api.schemas import ErrorDetail, ErrorEnvelope
from service.core.config import Settings, settings
from service.core.errors import GatewayError
from service.core.logging import setup_logging
from service.executor.engine import ExecutionEngine
from service.identity.token_resolver import TokenResolver
from service.registry.capability_registry import CapabilityRegistry
from service.registry.models import AgentRegistration
from service.traces.store import TraceStore

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, int] = {
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "CAPABILITY_NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "UPSTREAM_UNAVAILABLE": 503,
    "UPSTREAM_PERMANENT": 502,
    "INVALID_TOOL_RESULT": 502,
    "UPSTREAM_TIMEOUT": 504,
}


def _load_fixtures(fixture_path: Path | None = None) -> dict:
    if fixture_path is None:
        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "scenario.json"
    with open(fixture_path) as f:
        return json.load(f)


def _build_agents(fixtures: dict) -> dict:
    billing_agent = BillingAgent(
        fixture_data={
            tid: data.get("billing.summary", {})
            for tid, data in fixtures["tool_results"].items()
        }
    )
    sales_agent = SalesAgent(
        fixture_data={
            tid: data.get("sales.offers", {})
            for tid, data in fixtures["tool_results"].items()
        }
    )
    return {billing_agent.name: billing_agent, sales_agent.name: sales_agent}


def _build_registry(fixtures: dict, agents: dict) -> CapabilityRegistry:
    registrations = []
    for agent_def in fixtures["agents"]:
        agent = agents[agent_def["name"]]
        registrations.append(
            AgentRegistration(
                agent=agent,
                capability=agent_def["capability"],
                required_scope=agent_def["required_scope"],
                tool_name=agent_def["tool"],
            )
        )
    return CapabilityRegistry(registrations)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(GatewayError)
    async def gateway_error_handler(_request: Request, exc: GatewayError) -> JSONResponse:
        status_code = _STATUS_MAP.get(exc.code, 500)
        return JSONResponse(
            status_code=status_code,
            content=ErrorEnvelope(error=ErrorDetail(code=exc.code, message=exc.message)).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorEnvelope(
                error=ErrorDetail(code="VALIDATION_ERROR", message="Invalid request input.")
            ).model_dump(),
        )


def create_app(
    fixture_path: Path | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    app_settings: Settings | None = None,
) -> FastAPI:
    setup_logging()

    effective_settings = app_settings or settings

    app = FastAPI(title="Agent Gateway", version="0.1.0")

    fixtures = _load_fixtures(fixture_path)
    agents = _build_agents(fixtures)

    app.state.identity_resolver = TokenResolver(fixtures["principals"])
    app.state.registry = _build_registry(fixtures, agents)
    app.state.adapter = MockToolAdapter(
        tool_results=fixtures["tool_results"],
        agents=agents,
    )
    app.state.engine = ExecutionEngine(settings=effective_settings, sleep_fn=sleep_fn)
    app.state.trace_store = TraceStore(settings=effective_settings)

    register_middleware(app)
    app.include_router(router)
    _register_error_handlers(app)

    logger.info("Agent Gateway started", extra={"extra_fields": {"version": "0.1.0"}})
    return app
