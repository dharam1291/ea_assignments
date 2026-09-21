# Feature Specification: Observable Agent Gateway

**Feature Branch**: `001-agent-gateway`

**Created**: 2026-09-21

**Status**: Draft

**Input**: Build a small, observable agent gateway — a FastAPI service that resolves identity from bearer tokens, routes requests to agents by capability, invokes mock tool adapters with failure simulation and retry policies, and exposes structured execution traces.

## Clarifications

### Session 2026-09-21

- Q: How should the gateway handle in-memory trace accumulation? → A: TTL-based expiration — auto-expire traces after a configurable duration (e.g., 1 hour).
- Q: When the request body contains unknown fields, should the gateway ignore or reject them? → A: Ignore unknown fields but log a structured warning.
- Q: What format should structured application logs use? → A: Python standard `logging` module with a structured formatter.
- Q: What error response envelope should auth/validation errors use? → A: Unified envelope — all errors use `{"error": {"code": "...", "message": "..."}}` matching the invocation failure format.
- Q: What format should server-generated request IDs use? → A: Prefixed UUID4 — `req-<uuid4>` for human readability in logs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Invoke a Capability Successfully (Priority: P1)

An API consumer sends a POST request with a valid bearer token and a known capability. The gateway resolves their identity, confirms they have the required scope, routes to the correct agent, invokes the mock tool, and returns the tenant-specific result.

**Why this priority**: This is the core happy path. Without successful capability invocation, the gateway has no value.

**Independent Test**: Can be fully tested by sending `POST /invoke` with `demo-alpha-full` token and `billing.summary` capability, then verifying the response contains `{"amount_due": 42.0, "currency": "USD"}` with status `completed`.

**Acceptance Scenarios**:

1. **Given** a valid token `demo-alpha-full` with `billing:read` scope, **When** invoking `billing.summary` with simulation `ok`, **Then** receive HTTP 200 with the tenant-a billing result, status `completed`, and a unique `request_id`.
2. **Given** a valid token `demo-beta-full` with both scopes, **When** invoking `billing.summary`, **Then** receive HTTP 200 with the tenant-b billing result (`amount_due: 99.0`), proving tenant isolation.
3. **Given** a valid token `demo-alpha-full`, **When** invoking `sales.offers`, **Then** receive HTTP 200 with the tenant-a sales result containing offer `a-starter`.

---

### User Story 2 - Reject Unauthorized Requests (Priority: P1)

The gateway enforces authentication and authorization boundaries. Missing, invalid, or insufficient credentials are rejected before the adapter is ever invoked.

**Why this priority**: Security is non-negotiable. Unauthorized access must be blocked at the boundary, not deeper in the stack.

**Independent Test**: Can be tested by sending requests with no token (expect 401), an unknown token (expect 401), and a valid token without the required scope (expect 403), then confirming no adapter invocation occurred.

**Acceptance Scenarios**:

1. **Given** no `Authorization` header, **When** invoking any capability, **Then** receive HTTP 401.
2. **Given** an unknown token `demo-fake`, **When** invoking any capability, **Then** receive HTTP 401.
3. **Given** token `demo-alpha-sales` (only `sales:read`), **When** invoking `billing.summary` (requires `billing:read`), **Then** receive HTTP 403 and the adapter is never called.
4. **Given** a valid token, **When** invoking unknown capability `unknown.thing`, **Then** receive HTTP 404.

---

### User Story 3 - Handle Transient Failures with Retries (Priority: P1)

When the tool adapter encounters a transient error, the execution layer retries with backoff. If the transient error resolves, the consumer receives a success. If it persists, the consumer receives a clear failure.

**Why this priority**: Retry logic is core to the failure-handling requirement and exercises the execution policy layer.

**Independent Test**: Can be tested by invoking with `simulation: transient_then_ok` and verifying exactly 3 attempts occurred with correct backoff delays, then with `transient_always` and verifying the gateway stops after 3 attempts with HTTP 503.

**Acceptance Scenarios**:

1. **Given** simulation `transient_then_ok`, **When** invoking a capability, **Then** receive HTTP 200 after exactly 3 attempts with backoff delays of 50 ms and 100 ms between them.
2. **Given** simulation `transient_always`, **When** invoking a capability, **Then** receive HTTP 503 with error code `UPSTREAM_UNAVAILABLE` after exactly 3 attempts.

---

### User Story 4 - Handle Permanent Errors and Malformed Results (Priority: P2)

When the adapter encounters a non-retryable error or returns an invalid schema, the gateway fails immediately without retrying and without exposing internal details.

**Why this priority**: Completes the failure classification matrix. Important for correctness but lower risk than transient retry logic.

**Independent Test**: Can be tested by invoking with `simulation: permanent_error` (expect HTTP 502, 1 attempt) and `simulation: malformed_result` (expect HTTP 502, 1 attempt, bad payload not exposed).

**Acceptance Scenarios**:

1. **Given** simulation `permanent_error`, **When** invoking a capability, **Then** receive HTTP 502 with error code `UPSTREAM_PERMANENT` after exactly 1 attempt.
2. **Given** simulation `malformed_result`, **When** invoking a capability, **Then** receive HTTP 502 with error code `INVALID_TOOL_RESULT` after exactly 1 attempt, and the malformed payload is not in the response.

---

### User Story 5 - Enforce Timeout and Cancel Slow Operations (Priority: P2)

When the adapter takes longer than 250 ms per attempt, the gateway enforces a timeout, cancels the operation, and returns a clear error. A late result must not overwrite the timeout outcome.

**Why this priority**: Timeout enforcement prevents unbounded waits and proves async cancellation works correctly.

**Independent Test**: Can be tested by invoking with `simulation: timeout` and verifying HTTP 504, 1 attempt, and that a late adapter result does not change the outcome or trace.

**Acceptance Scenarios**:

1. **Given** simulation `timeout` (adapter takes ~2 seconds), **When** invoking a capability, **Then** receive HTTP 504 with error code `UPSTREAM_TIMEOUT` after exactly 1 attempt, completed in under 500 ms.
2. **Given** a timed-out invocation, **When** the adapter eventually completes, **Then** the trace and response remain unchanged (timeout is terminal).

---

### User Story 6 - Retrieve Execution Traces (Priority: P2)

After an invocation (success or failure), the consumer retrieves a detailed trace showing the agent, attempt count, timing, and per-attempt events. Access is restricted to the same principal and tenant.

**Why this priority**: Traces are the observability deliverable. Required for debugging and auditing but depends on invocation working first.

**Independent Test**: Can be tested by invoking a capability, extracting the `request_id`, then calling `GET /traces/{request_id}` with the same token and verifying the trace structure matches the expected events.

**Acceptance Scenarios**:

1. **Given** a completed invocation by user-a in tenant-a, **When** user-a requests the trace, **Then** receive the full trace with correct attempt count, duration, and events.
2. **Given** a completed invocation by user-a in tenant-a, **When** user-b (tenant-b) requests the same trace, **Then** receive HTTP 404.
3. **Given** a completed invocation by user-a in tenant-a, **When** user-c (same tenant-a, different user) requests the same trace, **Then** receive HTTP 404.
4. **Given** a failed invocation (e.g., `transient_always`), **When** requesting the trace, **Then** the trace shows all 3 attempts with `attempt_failed` events using code `TRANSIENT` and `retry_scheduled` events with correct delays.

---

### User Story 7 - Concurrent Request Isolation (Priority: P3)

When multiple consumers invoke the gateway simultaneously with different principals, each request maintains independent attempt state, results, and traces. No cross-contamination occurs.

**Why this priority**: Concurrency correctness is critical for production but is an advanced concern after single-request flows work.

**Independent Test**: Can be tested by launching two overlapping invocations with different tokens using synchronization barriers, then verifying each receives its own tenant-specific result and an independent trace.

**Acceptance Scenarios**:

1. **Given** two concurrent invocations by different principals, **When** both complete, **Then** each receives its own tenant-specific result, a unique request_id, and an independent trace.
2. **Given** two concurrent invocations sharing the same `conversation_id`, **When** both complete, **Then** neither inherits the other's attempt state or result.

---

### Edge Cases

- What happens when `conversation_id`, `capability`, or `message` is blank or missing? → HTTP 422 with validation error.
- What happens when fields exceed reasonable length limits? → HTTP 422.
- What happens when the request body contains unknown fields like `tenant_id` or `scopes`? → Silently ignored (discarded) and a structured warning is logged; they must not influence behavior.
- What happens when `simulation` is an invalid value? → HTTP 422.
- What happens when `simulation` is omitted? → Defaults to `ok`.
- What happens when extra headers like `X-Tenant-ID` are sent? → Ignored; they must not change the principal.
- What happens when the bearer token format is `Bearer <token>` vs just `<token>`? → Only the `Bearer <token>` format is accepted.
- What happens when a secret string appears in the message? → It must not appear in traces, logs, or error responses.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose `GET /health` that returns HTTP 200 with `{"status": "ok"}` without authentication.
- **FR-002**: System MUST expose `POST /invoke` that accepts `Authorization: Bearer <token>` and a JSON body with `conversation_id`, `capability`, `message`, and optional `simulation` fields.
- **FR-003**: System MUST resolve bearer tokens to principals by exact lookup from `fixtures/scenario.json`. Missing, malformed, or unknown tokens return HTTP 401.
- **FR-004**: System MUST enforce scope-based authorization before invoking the adapter. A known principal without the required scope receives HTTP 403.
- **FR-005**: System MUST route requests to the correct agent based on the `capability` field using the agent registry loaded from fixtures. Unknown capabilities return HTTP 404.
- **FR-006**: System MUST invoke a local mock tool adapter that returns tenant-specific results from the fixture data and supports six simulation modes: `ok`, `transient_then_ok`, `transient_always`, `permanent_error`, `malformed_result`, `timeout`.
- **FR-007**: System MUST validate the adapter's result structure against the expected schema for each capability. Invalid results trigger `INVALID_TOOL_RESULT` failure.
- **FR-008**: System MUST retry transient errors up to 3 attempts total, with async backoff delays of 50 ms (before attempt 2) and 100 ms (before attempt 3). Delays must not exceed 250 ms including optional jitter.
- **FR-009**: System MUST enforce a 250 ms per-attempt timeout. Timed-out operations are cancelled. Timeout is terminal and not retried.
- **FR-010**: System MUST generate a unique `request_id` per HTTP invocation in the format `req-<uuid4>` (e.g., `req-550e8400-e29b-41d4-a716-446655440000`), even when the `conversation_id` is reused.
- **FR-011**: System MUST return correct tenant-specific results based on the authenticated principal's tenant.
- **FR-012**: System MUST expose `GET /traces/{request_id}` that returns the execution trace only to the same principal and tenant that created it. Unknown or inaccessible traces return HTTP 404.
- **FR-013**: System MUST store traces in memory before the `/invoke` response is sent, containing: request_id, conversation_id, tenant_id, agent, capability, status, attempts count, duration_ms, and an ordered events list. Traces MUST be auto-expired after a configurable TTL (default: 1 hour).
- **FR-014**: System MUST use canonical event names (`attempt_started`, `attempt_failed`, `attempt_succeeded`, `retry_scheduled`) with attempt numbers starting from 1.
- **FR-015**: System MUST use error codes `UPSTREAM_UNAVAILABLE`, `UPSTREAM_PERMANENT`, `INVALID_TOOL_RESULT`, and `UPSTREAM_TIMEOUT` for the respective failure modes.
- **FR-016**: System MUST produce structured application logs using Python's standard `logging` module with a structured formatter for execution start, retry, and completion/failure, including request_id, agent, attempt, and outcome.
- **FR-017**: System MUST NOT expose stack traces, bearer tokens, raw message text, or invalid tool payloads in error responses, traces, or logs.
- **FR-018**: System MUST validate input fields: nonblank strings for `conversation_id`, `capability`, `message` with documented length limits. `simulation` restricted to the six valid values. Invalid input returns HTTP 422.
- **FR-019**: System MUST silently ignore unknown body fields (e.g., `tenant_id`, `scopes`) and log a structured warning for each. Unknown fields must not influence behavior. Extra headers like `X-Tenant-ID` must not influence principal resolution.
- **FR-020**: System MUST maintain independent attempt state per invocation. Concurrent requests must not share retry counters, results, or traces.
- **FR-021**: System MUST use a unified error envelope for all error responses (401, 403, 404, 422, 502, 503, 504): `{"error": {"code": "<ERROR_CODE>", "message": "<human-readable message>"}}`. Auth errors use codes such as `UNAUTHORIZED`, `FORBIDDEN`; validation errors use `VALIDATION_ERROR`; routing errors use `CAPABILITY_NOT_FOUND`.

### Key Entities

- **Principal**: Represents an authenticated identity. Attributes: user_id, tenant_id, scopes. Resolved from bearer token via fixture lookup.
- **Agent Registration**: Maps a capability to an agent name, required scope, and tool identifier. Loaded from fixture at startup.
- **Invocation Request**: The inbound request containing conversation_id, capability, message, and simulation mode.
- **Invocation Result**: The response envelope containing request_id, conversation_id, tenant_id, agent, status, and either result data or error details.
- **Execution Trace**: A record of one invocation's execution: attempts, timing, per-attempt events, and final outcome. Scoped to the creating principal and tenant.
- **Tool Result**: The output from the mock adapter. Must be validated against a per-capability schema before acceptance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All six simulation modes produce the correct HTTP status code and attempt count on every invocation.
- **SC-002**: Unauthorized requests (invalid token, missing scope) are rejected before the adapter is called, verified by spy/counter assertions.
- **SC-003**: Tenant isolation holds: no request returns another tenant's data, verified across all three demo principals.
- **SC-004**: Trace isolation holds: no user can read another user's trace, even within the same tenant, verified by cross-principal lookups returning 404.
- **SC-005**: Concurrent overlapping invocations with different principals each receive independent, correct results and traces, verified with synchronization barriers.
- **SC-006**: A timed-out invocation completes in under 500 ms total, and a late adapter result does not alter the failed outcome.
- **SC-007**: Structured logs and traces contain no bearer tokens, raw message text, or tool-result bodies, verified by searching captured output for a distinctive secret string.
- **SC-008**: The acceptance checker (`tools/acceptance_check.py`) passes all checks against the running server.
- **SC-009**: The full pytest suite passes with `python -m pytest -q` in under 30 seconds.
- **SC-010**: Adding a new capability to the fixture requires zero changes to the API endpoint or execution loop.

## Assumptions

- The three demo bearer tokens and their principal mappings in `fixtures/scenario.json` are the complete, authoritative identity source. No additional tokens or dynamic registration is needed.
- The fixture file is loaded once at startup and treated as immutable during runtime.
- In-memory trace storage is sufficient; traces do not survive process restarts. Traces are auto-expired after a configurable TTL (default: 1 hour) to prevent unbounded memory growth.
- Single uvicorn worker is the deployment model. No inter-process state sharing is required.
- No real LLM, MCP server, external API, or network call is involved. The adapter is entirely local.
- `conversation_id` is a correlation label only — shared conversation IDs do not share authorization, results, or history.
- Operations are read-only. No payment, approval, or state-mutation semantics apply.
- Reasonable field length limits are documented but not externally specified — the implementation defines them (e.g., 256 characters for string fields).
