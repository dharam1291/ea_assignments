# Implementation Plan: Observable Agent Gateway

**Branch**: `001-agent-gateway` | **Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-agent-gateway/spec.md`

## Summary

Build a Python/FastAPI agent gateway with a modular, production-grade package structure. The gateway resolves identity from bearer tokens, routes to first-class Agent objects by capability, invokes agents' registered tools through a mock adapter (with failure simulation), orchestrates retries/timeouts/backoff via an async execution engine, and records structured execution traces. Three HTTP endpoints (`/health`, `/invoke`, `/traces/{request_id}`) expose the system. Each architectural layer is an independent subpackage with its own models, protocols, and implementations — enabling unit testing without the HTTP server and swapping any layer (e.g., demo tokens → OIDC, mock adapter → remote MCP client) by implementing one interface.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, uvicorn, pydantic (v2), httpx (test client)

**Storage**: In-memory dictionaries with TTL-based trace expiration (default 1 hour)

**Testing**: pytest with httpx AsyncClient/TestClient, asyncio fixtures. Both pytest source-level tests AND the provided `tools/acceptance_check.py` are required — the assessment explicitly states the acceptance checker alone is not sufficient.

**Target Platform**: Linux/macOS server (Docker container, single uvicorn worker)

**Project Type**: Web service (API gateway)

**Performance Goals**: 250 ms per-attempt timeout enforcement; full pytest suite < 30 seconds

**Constraints**: No outbound network; single worker; no database; read-only operations; 4-hour time box

**Scale/Scope**: 3 demo principals, 2 agents, 2 capabilities, 6 simulation modes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Layered Service Architecture | PASS | Six subpackages: `identity/`, `registry/`, `agents/`, `adapter/`, `executor/`, `traces/`. Each independently importable. Dependencies flow inward. |
| II. Secure by Default | PASS | Token-only identity; authz before adapter invocation; no sensitive data in errors/logs/traces. |
| III. Test-First Verification | PASS | pytest with DI per layer; injected clock for retries; barriers for concurrency; acceptance checker as supplementary. |
| IV. Observable Execution | PASS | Structured traces with canonical events; Python `logging` with structured JSON formatter. |
| V. Resilient Failure Handling | PASS | Deterministic retry policy; local attempt state; 4 error codes; timeout cancellation via asyncio. |
| VI. Scalability-Ready Design | PASS | Protocol-based interfaces; async-native; injectable config; agents as first-class objects with swappable tool adapters. |
| VII. Simplicity and Explicitness | PASS | Minimal deps; Pydantic models; modular but not over-abstracted. |

All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-gateway/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.md           # HTTP API contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
service/
├── __init__.py                 # Package root, version
├── main.py                     # FastAPI app factory, lifespan, uvicorn entry
├── config.py                   # Centralized config: timeouts, retries, TTL, limits
│
├── identity/                   # Layer 1: Authentication
│   ├── __init__.py
│   ├── models.py               # Principal Pydantic model
│   ├── protocol.py             # IdentityResolver protocol (for swapping to OIDC)
│   └── token_resolver.py       # Demo token → Principal exact-lookup implementation
│
├── registry/                   # Layer 2: Capability routing + authorization
│   ├── __init__.py
│   ├── models.py               # AgentRegistration model
│   └── capability_registry.py  # Capability → Agent lookup, scope enforcement
│
├── agents/                     # Layer 3: Agent abstractions
│   ├── __init__.py
│   ├── base.py                 # BaseAgent protocol: name, capabilities, tools
│   ├── billing_agent.py        # BillingAgent: owns billing_summary tool
│   ├── sales_agent.py          # SalesAgent: owns sales_offers tool
│   └── tools/                  # Agent tools (MCP-inspired, not MCP-compliant)
│       ├── __init__.py
│       ├── base.py             # Tool protocol: name, invoke(), result schema
│       ├── billing_summary.py  # billing_summary tool implementation
│       └── sales_offers.py     # sales_offers tool implementation
│
├── adapter/                    # Layer 4: Tool adapter (invocation + simulation)
│   ├── __init__.py
│   ├── protocol.py             # ToolAdapter protocol (swappable to remote MCP)
│   ├── mock_adapter.py         # Mock implementation: fixture results + 6 simulation modes
│   └── validators.py           # Per-capability Pydantic result validators
│
├── executor/                   # Layer 5: Execution policy
│   ├── __init__.py
│   ├── engine.py               # Retry loop, backoff, timeout, cancellation
│   └── models.py               # ExecutionResult, attempt tracking
│
├── traces/                     # Layer 6: Observability
│   ├── __init__.py
│   ├── models.py               # ExecutionTrace, TraceEvent models
│   └── store.py                # TTL-based in-memory store with access control
│
├── api/                        # HTTP layer: thin, delegates everything
│   ├── __init__.py
│   ├── routes.py               # Endpoint definitions (health, invoke, traces)
│   ├── dependencies.py         # FastAPI Depends: auth, registry, adapter injection
│   └── schemas.py              # Request/Response Pydantic models (API envelope)
│
├── errors.py                   # Custom exceptions + unified error envelope handlers
└── logging_config.py           # Structured JSON logging setup, sensitive-field filter

fixtures/
└── scenario.json               # Demo identities, agents, tool results (read-only)

tests/
├── __init__.py
├── conftest.py                 # Shared fixtures: app client, tokens, spy helpers
├── unit/
│   ├── __init__.py
│   ├── test_identity.py        # Token resolution: valid, invalid, missing
│   ├── test_registry.py        # Capability routing: known, unknown, scope check
│   ├── test_agents.py          # Agent tool invocation, result schemas
│   ├── test_adapter.py         # All 6 simulation modes at adapter level
│   ├── test_executor.py        # Retry count, backoff delays (injected clock), timeout
│   ├── test_traces.py          # Store, TTL expiry, access control
│   └── test_validators.py      # Per-capability result validation
└── integration/
    ├── __init__.py
    ├── test_health.py           # GET /health
    ├── test_invoke.py           # POST /invoke: all 6 simulations end-to-end
    ├── test_auth.py             # 401/403 integration, prove adapter not called
    ├── test_isolation.py        # Tenant/user isolation + concurrent barriers
    ├── test_timeout.py          # Timeout cancellation, late result rejection
    └── test_sanitization.py     # Secret string not in logs/traces/errors

tools/
└── acceptance_check.py          # Provided HTTP acceptance checker (supplementary)

Dockerfile
requirements.txt
README.md
SUBMISSION_NOTES.md
ASSESSMENT.md
```

### Structure Decision

**Modular subpackage layout** — each architectural layer is its own Python subpackage under `service/`. This provides:

- **Namespace isolation**: Each layer's models, protocols, and implementations live together. No name collisions.
- **Import discipline**: `from service.identity.protocol import IdentityResolver` makes the dependency explicit. Circular imports are structurally prevented by the inward dependency flow.
- **Testability**: Each subpackage is independently importable and testable without the HTTP server.
- **Swappability**: Replace `service.identity.token_resolver` with `service.identity.oidc_resolver` by implementing the same protocol — no changes to any other subpackage.

**Agents as first-class entities** — `service/agents/` contains concrete agent classes (`BillingAgent`, `SalesAgent`) that each:
- Declare their `name` and `capabilities`
- Own their `tools/` (e.g., `billing_summary`, `sales_offers`)
- Each tool declares its result schema for validation

This mirrors a real agent platform where agents are registered, discovered by capability, and invoke their own tools. Adding a new agent means: (1) add the agent class with its tool, (2) add a fixture entry — zero changes to the API routes, execution engine, or retry loop.

**Tests split into unit + integration** — unit tests cover each layer in isolation with mocks/DI; integration tests cover the full HTTP request lifecycle. Both are required by the assessment.

## Agent Architecture

```text
┌──────────────────────────────────────────────────┐
│                  POST /invoke                     │
│               (api/routes.py)                     │
└──────────┬───────────────────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Identity Layer  │───▶│  Principal (user, tenant, │
│  (token_resolver)│    │  scopes)                  │
└──────────────────┘    └──────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Registry Layer  │───▶│  AgentRegistration        │
│  (capability_    │    │  + scope enforcement      │
│   registry)      │    │  (403 if insufficient)    │
└──────────────────┘    └──────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Agent Layer     │───▶│  BillingAgent             │
│  (resolved by    │    │    └─ billing_summary tool│
│   registry)      │    │  SalesAgent               │
│                  │    │    └─ sales_offers tool    │
└──────────────────┘    └──────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Adapter Layer   │───▶│  MockToolAdapter          │
│  (protocol-based)│    │  (simulation modes,       │
│                  │    │   fixture results)         │
└──────────────────┘    └──────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Executor Layer  │───▶│  Retry (3 max), backoff   │
│  (engine.py)     │    │  (50ms/100ms), timeout    │
│                  │    │  (250ms), cancellation     │
└──────────────────┘    └──────────────────────────┘
           │
           ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Trace Layer     │───▶│  Structured trace stored  │
│  (store.py)      │    │  before HTTP response,    │
│                  │    │  TTL-based expiration      │
└──────────────────┘    └──────────────────────────┘
```

### Agent–Tool Relationship

Each agent is a concrete class that owns one or more tools:

```text
BaseAgent (Protocol)
  ├─ name: str
  ├─ capabilities: list[str]
  └─ tools: dict[str, Tool]

Tool (Protocol)
  ├─ name: str
  ├─ result_schema: type[BaseModel]   # Pydantic model for validation
  └─ invoke(tenant_id, simulation) → dict

BillingAgent
  ├─ name = "billing-agent"
  ├─ capabilities = ["billing.summary"]
  └─ tools = {"billing_summary": BillingSummaryTool}

SalesAgent
  ├─ name = "sales-agent"
  ├─ capabilities = ["sales.offers"]
  └─ tools = {"sales_offers": SalesOffersTool}
```

The registry maps capability → agent. The adapter invokes the agent's tool through the Protocol interface. The executor wraps this with retry/timeout policy. This means:
- **Adding a new agent**: Create the agent class + tool, add fixture entry. No other code changes.
- **Replacing mock with remote**: Implement the `ToolAdapter` protocol with an MCP client. No agent or executor changes.

## Complexity Tracking

No constitution violations. Table not applicable.
