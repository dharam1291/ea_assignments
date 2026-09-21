<!--
  SYNC IMPACT REPORT (remove before commit)
  Version change: 0.0.0 → 1.0.0
  Added principles:
    - I. Layered Service Architecture
    - II. Secure by Default
    - III. Test-First Verification
    - IV. Observable Execution
    - V. Resilient Failure Handling
    - VI. Scalability-Ready Design
    - VII. Simplicity and Explicitness
  Added sections:
    - Technology Stack and Constraints
    - Development Workflow
    - Governance
  Removed sections: none (initial ratification)
  Deferred TODOs: none
-->

# Agent Gateway Constitution

## Core Principles

### I. Layered Service Architecture

All application code MUST be organized into distinct, independently testable
layers with explicit boundaries. The implementation folder is `service/`.

- **Identity layer**: resolves credentials to principals. No business logic.
- **Registry/router layer**: maps capabilities to agents and enforces scopes.
  Adding a new capability MUST NOT require changes to the API endpoint or
  execution loop.
- **Adapter layer**: invokes tools and validates their output schemas. Adapters
  are swappable; the execution layer depends on adapter interfaces, not
  concrete implementations.
- **Execution policy layer**: orchestrates retries, timeouts, and backoff.
  Attempt state MUST be local to each invocation; no shared mutable state
  between concurrent requests.
- **Trace layer**: records structured execution events. Traces are written
  before the HTTP response is sent.

Each layer MUST be importable and testable without starting the HTTP server.
Dependencies flow inward: API → Execution → Adapter → Registry → Identity.
No circular imports.

**Rationale**: Clean separation enables independent testing, makes failure
modes explicit, and allows each layer to be replaced (e.g., demo token lookup
→ OIDC verification) without rewriting adjacent code.

### II. Secure by Default

Security constraints are enforced at the boundary and MUST NOT be
bypassable by request content, headers, or body fields.

- Bearer tokens are the sole source of identity. Extra headers such as
  `X-Tenant-ID` or `X-Scopes` MUST NOT influence principal resolution.
- Authorization (scope check) MUST occur before the adapter is invoked.
- Trace access MUST be restricted to the same principal and tenant that
  created the trace. No admin bypass exists.
- Error responses MUST NOT expose stack traces, bearer tokens, raw user
  messages, or invalid tool payloads.
- Structured logs MUST NOT record bearer tokens, raw message text, or
  tool-result bodies.

**Rationale**: Defense in depth. The message text is untrusted input; it
MUST NOT change identity, scopes, agent selection, or the tool allowlist.

### III. Test-First Verification

All behavioral requirements MUST have corresponding pytest tests that fail
when the behavior is broken.

- Unit tests MUST cover each layer in isolation using dependency injection.
- Integration tests MUST exercise the full HTTP request/response cycle.
- Retry behavior MUST be verified with injected clock/sleeper or spy,
  not wall-clock timing assertions.
- Concurrency tests MUST use synchronization barriers, not sleep-based
  timing.
- Parameterized tests are encouraged for simulation modes and
  multi-principal scenarios.
- A blanket catch-all that converts defects into passing tests is
  prohibited.

**Rationale**: Tests prove internal behavior, not just fabricated responses.
The acceptance checker is a supplement, not a replacement for source-level
assertions.

### IV. Observable Execution

Every adapter invocation MUST produce a structured trace with attempt-level
event granularity.

- Traces MUST include: request_id, conversation_id, tenant_id, agent,
  capability, status, attempts count, duration_ms, and an ordered events
  list.
- Events use the canonical names: `attempt_started`, `attempt_failed`,
  `attempt_succeeded`, `retry_scheduled`.
- Timings and events MUST be derived from actual execution, never
  manufactured.
- Application logs MUST be structured and include request_id, agent,
  attempt number, and outcome at execution start, retry, and
  completion/failure.

**Rationale**: Observability enables debugging, auditing, and incident
response without requiring reproduction of the failure.

### V. Resilient Failure Handling

The execution layer MUST classify adapter outcomes and react according to
a deterministic policy.

- Transient errors: retry up to 3 attempts with async backoff (50 ms,
  100 ms). Jitter is optional but delays MUST NOT exceed 250 ms.
- Permanent errors: fail immediately, 1 attempt.
- Malformed results: fail immediately, do not expose the bad payload.
- Timeout: enforce 250 ms per-attempt deadline. Cancel the local task.
  Terminal — not retried.
- Error codes MUST use: `UPSTREAM_UNAVAILABLE`, `UPSTREAM_PERMANENT`,
  `INVALID_TOOL_RESULT`, `UPSTREAM_TIMEOUT`.
- Attempt state MUST be local to each invocation. Concurrent requests
  MUST NOT share retry counters or results.

**Rationale**: Deterministic failure classification prevents cascading
failures and makes retry behavior auditable through traces.

### VI. Scalability-Ready Design

The architecture MUST support evolution from single-process in-memory
state to distributed deployment without structural rewrites.

- All state access (traces, registry) MUST go through abstract
  interfaces (protocols/ABCs), not direct dictionary access in
  endpoint handlers.
- Request handling MUST be async-native (`async def` endpoints and
  `asyncio` primitives) to support concurrent request processing.
- Configuration (timeouts, retry counts, backoff delays) MUST be
  centralized and injectable, not scattered as magic numbers.
- The adapter interface MUST be defined such that replacing the local
  mock with a remote MCP client or agent SDK requires implementing
  one interface, not modifying the execution loop.

**Rationale**: In-memory storage and single-process execution are
deliberate simplifications for this exercise. The code structure
MUST NOT embed those simplifications as architectural assumptions.

### VII. Simplicity and Explicitness

Favor explicit, readable code over clever abstractions.

- No feature flags, backwards-compatibility shims, or speculative
  generalization beyond what the requirements demand.
- Pydantic models MUST define all request/response schemas with
  strict validation. No arbitrary dict pass-through.
- Configuration follows a single, documented pattern.
- Dependencies are minimal: FastAPI, uvicorn, pydantic, pytest,
  httpx. No ORM, no external logging framework, no task queue.

**Rationale**: A four-hour time-boxed exercise rewards clarity and
correctness over framework sophistication. Every abstraction must
earn its place by serving a stated requirement.

## Technology Stack and Constraints

- **Language**: Python 3.11+
- **Framework**: FastAPI with a single uvicorn worker
- **Validation**: Pydantic v2 models for all request/response schemas
- **Testing**: pytest with httpx AsyncClient (TestClient)
- **Packaging**: `requirements.txt` or `pyproject.toml` with pinned
  runtime and test dependencies
- **Containerization**: Dockerfile with non-root runtime user
- **Implementation directory**: `service/` — all application source
  lives here
- **Fixtures**: `fixtures/scenario.json` loaded at startup, read-only
- **Network**: no outbound access required at runtime or during tests
- **Storage**: in-memory only; no database, no filesystem writes

## Development Workflow

- All changes MUST pass `python -m pytest -q` before submission.
- All changes MUST pass `tools/acceptance_check.py` against the
  running server.
- Code review readiness: the candidate MUST be able to trace a
  request through the code, reproduce a failure, and implement a
  small change with a test during the follow-up session.
- Commit messages follow conventional format:
  `type(scope): description`.
- The README MUST contain exact commands for native and Docker
  execution, one success example, one failure example, implemented
  features, and known limitations.
- `SUBMISSION_NOTES.md` MUST contain actual output, not
  reconstructed expected results.

## Governance

This constitution defines the non-negotiable design principles for the
Agent Gateway project. All implementation decisions MUST be traceable
to a stated principle or an explicit requirement from `ASSESSMENT.md`.

- Amendments require documentation of the change rationale and an
  updated version number.
- Version follows semantic versioning: MAJOR for principle removals
  or redefinitions, MINOR for new principles or material expansions,
  PATCH for clarifications and wording fixes.
- Complexity MUST be justified by a requirement. If a principle
  conflicts with the four-hour time constraint, the simplification
  MUST be documented in `SUBMISSION_NOTES.md` under known
  limitations.

**Version**: 1.0.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-21
