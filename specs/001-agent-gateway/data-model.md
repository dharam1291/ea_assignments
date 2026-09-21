# Data Model: Observable Agent Gateway

**Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

## Entities

### Principal

Represents an authenticated identity resolved from a bearer token.

| Field | Type | Constraints |
|-------|------|-------------|
| user_id | string | Non-empty, from fixture |
| tenant_id | string | Non-empty, from fixture |
| scopes | list[string] | Non-empty, each scope non-empty |

**Source**: Loaded from `fixtures/scenario.json` → `principals` map.
**Lifecycle**: Immutable after startup. Looked up by exact token match.

### Agent (first-class entity)

A registered agent that owns one or more tools and handles one or more capabilities.

| Field | Type | Constraints |
|-------|------|-------------|
| name | string | Non-empty, unique agent identifier (e.g., `billing-agent`) |
| capabilities | list[string] | Non-empty, each maps to one tool |
| tools | dict[str, Tool] | Tool name → Tool instance |

**Concrete agents**:
- `BillingAgent`: name=`billing-agent`, capabilities=`[billing.summary]`, tools=`{billing_summary: BillingSummaryTool}`
- `SalesAgent`: name=`sales-agent`, capabilities=`[sales.offers]`, tools=`{sales_offers: SalesOffersTool}`

**Source**: Instantiated at startup from `fixtures/scenario.json` → `agents` list.
**Lifecycle**: Immutable after startup. Registered in the capability registry.

### Tool (owned by an Agent)

A discrete operation an agent can perform. Each tool declares its result schema.

| Field | Type | Constraints |
|-------|------|-------------|
| name | string | Non-empty, matches fixture `tool` field |
| result_schema | type[BaseModel] | Pydantic model for validating output |
| invoke(tenant_id, simulation) | async method | Returns tenant-specific fixture data or simulated failure |

**Concrete tools**:
- `BillingSummaryTool`: result_schema=`BillingSummaryResult`, returns `{amount_due, currency}` for the tenant
- `SalesOffersTool`: result_schema=`SalesOffersResult`, returns `{offers: [{id, name}]}` for the tenant

### AgentRegistration

Maps a capability to an agent and its required scope in the registry.

| Field | Type | Constraints |
|-------|------|-------------|
| agent | Agent | The resolved agent instance |
| capability | string | Non-empty, unique capability key |
| required_scope | string | Non-empty, must exist in at least one principal's scopes |
| tool_name | string | Key into the agent's `tools` dict |

**Source**: Built at startup from `fixtures/scenario.json` → `agents` list + agent instances.
**Lifecycle**: Immutable after startup. Indexed by `capability`.

### InvokeRequest (HTTP input)

The inbound request body for `POST /invoke`.

| Field | Type | Constraints |
|-------|------|-------------|
| conversation_id | string | Non-blank, max 256 chars |
| capability | string | Non-blank, max 256 chars |
| message | string | Non-blank, max 2048 chars |
| simulation | enum | Optional, default `ok`. Values: `ok`, `transient_then_ok`, `transient_always`, `permanent_error`, `malformed_result`, `timeout` |

**Validation**: Pydantic model with `model_config = ConfigDict(extra="ignore")`. Unknown fields silently discarded + warning logged.

### InvokeResponse (HTTP output — success)

| Field | Type | Source |
|-------|------|--------|
| request_id | string | Generated: `req-<uuid4>` |
| conversation_id | string | Echo from request |
| tenant_id | string | From authenticated principal |
| agent | string | From registry lookup |
| status | literal | `"completed"` |
| result | dict | Tenant-specific tool result from fixture |

### InvokeErrorResponse (HTTP output — failure)

| Field | Type | Source |
|-------|------|--------|
| request_id | string | Generated: `req-<uuid4>` |
| conversation_id | string | Echo from request |
| tenant_id | string | From authenticated principal |
| agent | string | From registry lookup |
| status | literal | `"failed"` |
| error | object | `{"code": "<ERROR_CODE>", "message": "<human-readable>"}` |

### ErrorEnvelope (HTTP output — auth/validation errors)

| Field | Type | Source |
|-------|------|--------|
| error | object | `{"code": "<ERROR_CODE>", "message": "<human-readable>"}` |

**Error codes by status**:
- 401: `UNAUTHORIZED`
- 403: `FORBIDDEN`
- 404: `CAPABILITY_NOT_FOUND`
- 422: `VALIDATION_ERROR`

### ExecutionTrace

A record of one invocation's execution lifecycle.

| Field | Type | Constraints |
|-------|------|-------------|
| request_id | string | Matches the invocation's request_id |
| conversation_id | string | From request |
| tenant_id | string | From principal — used for access control |
| user_id | string | From principal — used for access control (not exposed in HTTP response; internal only) |
| agent | string | From registry |
| capability | string | From request |
| status | enum | `completed` or `failed` |
| attempts | int | 1–3 |
| duration_ms | float | Wall-clock time of execution |
| events | list[TraceEvent] | Ordered by occurrence |
| created_at | datetime | UTC timestamp for TTL expiration |

**Access control**: Read allowed only when requester's `user_id` AND `tenant_id` both match the trace's stored values.
**TTL**: Auto-expired after configurable duration (default: 1 hour). Expiration checked on read (lazy).

### TraceEvent

| Field | Type | Constraints |
|-------|------|-------------|
| event | enum | `attempt_started`, `attempt_failed`, `attempt_succeeded`, `retry_scheduled` |
| attempt | int | 1-indexed |
| code | string | Only on `attempt_failed`: `TRANSIENT`, `PERMANENT`, `INVALID_RESULT`, `TIMEOUT` |
| delay_ms | int/float | Only on `retry_scheduled`: 50 or 100 (plus optional jitter) |

### ToolResult (per-capability validation)

**billing.summary**:

| Field | Type | Constraints |
|-------|------|-------------|
| amount_due | float | Required |
| currency | string | Required |

**sales.offers**:

| Field | Type | Constraints |
|-------|------|-------------|
| offers | list[object] | Required, each with `id` (string) and `name` (string) |

## Relationships

```text
Bearer Token ──(exact lookup)──→ Principal
                                    │
InvokeRequest.capability ──(registry lookup)──→ AgentRegistration
                                                    │
Principal.scopes ──(must include)──→ AgentRegistration.required_scope
                                                    │
                                        AgentRegistration.agent
                                                    │
                                        Agent.tools[tool_name] ──→ Tool
                                                    │
                              ToolAdapter.invoke(agent, tool, tenant_id, simulation)
                                                    │
                                                    ▼
                                     Tool.result_schema.model_validate(output)
                                                    │
                                                    ▼
                                        InvokeResponse + ExecutionTrace
```

## State Transitions

### Invocation Lifecycle

```text
RECEIVED → AUTHENTICATED → AUTHORIZED → EXECUTING → COMPLETED
                                            │
                                            ├──→ RETRY (transient) → EXECUTING
                                            │
                                            └──→ FAILED (permanent/malformed/timeout/max retries)
```

### Trace Lifecycle

```text
CREATED (at invocation end) → READABLE (within TTL) → EXPIRED (after TTL, lazy removal on read)
```
