# Tasks: Observable Agent Gateway

**Input**: Design documents from `specs/001-agent-gateway/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: REQUIRED — the assessment mandates pytest source-level tests proving internal behavior.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths included in every task description

---

## Phase 1: Setup (Project Scaffolding)

**Purpose**: Create the modular package structure, install dependencies, configure tooling.

- [ ] T001 Create full project directory structure per plan.md: `service/`, `service/identity/`, `service/registry/`, `service/agents/`, `service/agents/tools/`, `service/adapter/`, `service/executor/`, `service/traces/`, `service/api/`, `tests/`, `tests/unit/`, `tests/integration/`
- [ ] T002 Create `requirements.txt` with pinned dependencies: `fastapi>=0.111.0`, `uvicorn[standard]>=0.30.0`, `pydantic>=2.7.0`, `httpx>=0.27.0`, `pytest>=8.2.0`, `pytest-asyncio>=0.23.0`
- [ ] T003 [P] Create `service/__init__.py` with package version string
- [ ] T004 [P] Create all `__init__.py` files for subpackages: `service/identity/__init__.py`, `service/registry/__init__.py`, `service/agents/__init__.py`, `service/agents/tools/__init__.py`, `service/adapter/__init__.py`, `service/executor/__init__.py`, `service/traces/__init__.py`, `service/api/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`
- [ ] T005 [P] Create `Dockerfile` with Python 3.11+ base, non-root user (`appuser`), `COPY requirements.txt`, `pip install`, `COPY . .`, `EXPOSE 8000`, `CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`
- [ ] T006 [P] Create `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, test paths `tests/`

**Checkpoint**: `pip install -r requirements.txt` succeeds, `python -c "import service"` succeeds, `docker build` succeeds.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure all user stories depend on — config, models, identity, registry, agents, adapter protocol, error handling, logging. No user story work can begin until this phase is complete.

### Configuration & Shared Models

- [ ] T007 Implement centralized config in `service/config.py`: dataclass `Settings` with fields `max_attempts: int = 3`, `backoff_delays_ms: list[int] = [50, 100]`, `timeout_ms: int = 250`, `trace_ttl_seconds: int = 3600`, `max_conversation_id_length: int = 256`, `max_capability_length: int = 256`, `max_message_length: int = 2048`. Provide a module-level `settings` singleton loaded from defaults (no env vars required for this exercise).
- [ ] T008 [P] Implement unified error exceptions in `service/errors.py`: base `GatewayError(Exception)` with `code: str` and `message: str`; subclasses `AuthenticationError(code="UNAUTHORIZED")`, `AuthorizationError(code="FORBIDDEN")`, `CapabilityNotFoundError(code="CAPABILITY_NOT_FOUND")`, `InputValidationError(code="VALIDATION_ERROR")`, `UpstreamUnavailableError(code="UPSTREAM_UNAVAILABLE")`, `UpstreamPermanentError(code="UPSTREAM_PERMANENT")`, `InvalidToolResultError(code="INVALID_TOOL_RESULT")`, `UpstreamTimeoutError(code="UPSTREAM_TIMEOUT")`
- [ ] T009 [P] Implement structured logging in `service/logging_config.py`: function `setup_logging()` that configures Python `logging` with a JSON formatter (one JSON object per line). Add a `SensitiveFieldFilter` that strips/redacts fields named `token`, `message`, `raw_result` from log records. Call `setup_logging()` in app startup.

### Identity Layer

- [ ] T010 Define `IdentityResolver` Protocol in `service/identity/protocol.py`: method `resolve(token: str) -> Principal | None` — returns `None` for unknown tokens.
- [ ] T011 [P] Define `Principal` Pydantic model in `service/identity/models.py`: fields `user_id: str`, `tenant_id: str`, `scopes: list[str]`. Frozen model (immutable).
- [ ] T012 Implement `TokenResolver` in `service/identity/token_resolver.py`: loads `fixtures/scenario.json` `principals` map at init. Method `resolve(token: str) -> Principal | None` does exact-match lookup. Constructor takes the principals dict (for testability).

### Agent & Tool Layer

- [ ] T013 Define `Tool` Protocol in `service/agents/tools/base.py`: properties `name: str`, `result_schema: type[BaseModel]`; method signature (protocol only, not implementation) for reference.
- [ ] T014 [P] Define `BaseAgent` Protocol in `service/agents/base.py`: properties `name: str`, `capabilities: list[str]`, `tools: dict[str, Tool]`.
- [ ] T015 [P] Implement `BillingSummaryTool` in `service/agents/tools/billing_summary.py`: `name = "billing_summary"`, `result_schema = BillingSummaryResult` (Pydantic model with `amount_due: float`, `currency: str`). Tool holds fixture data per tenant.
- [ ] T016 [P] Implement `SalesOffersTool` in `service/agents/tools/sales_offers.py`: `name = "sales_offers"`, `result_schema = SalesOffersResult` (Pydantic model with `offers: list[OfferItem]` where `OfferItem` has `id: str`, `name: str`). Tool holds fixture data per tenant.
- [ ] T017 Implement `BillingAgent` in `service/agents/billing_agent.py`: `name = "billing-agent"`, `capabilities = ["billing.summary"]`, `tools = {"billing_summary": BillingSummaryTool(...)}`. Constructor receives tenant-specific fixture data.
- [ ] T018 [P] Implement `SalesAgent` in `service/agents/sales_agent.py`: `name = "sales-agent"`, `capabilities = ["sales.offers"]`, `tools = {"sales_offers": SalesOffersTool(...)}`. Constructor receives tenant-specific fixture data.

### Registry Layer

- [ ] T019 Define `AgentRegistration` model in `service/registry/models.py`: fields `agent: BaseAgent`, `capability: str`, `required_scope: str`, `tool_name: str`.
- [ ] T020 Implement `CapabilityRegistry` in `service/registry/capability_registry.py`: constructor takes list of `AgentRegistration`. Method `resolve(capability: str) -> AgentRegistration | None`. Method `check_scope(registration: AgentRegistration, principal: Principal) -> bool` returns whether principal has the required scope. Registry is a dict indexed by capability string.

### Adapter Layer

- [ ] T021 Define `ToolAdapter` Protocol in `service/adapter/protocol.py`: async method `invoke(agent_name: str, tool_name: str, tenant_id: str, simulation: str) -> dict`. Raises typed exceptions for transient, permanent, timeout, and malformed scenarios.
- [ ] T022 [P] Implement per-capability result validators in `service/adapter/validators.py`: function `validate_tool_result(capability: str, raw_result: dict) -> dict` that looks up the correct Pydantic model (`BillingSummaryResult` or `SalesOffersResult`) and calls `model_validate(raw_result)`. Raises `InvalidToolResultError` on validation failure (no raw payload in the error message).
- [ ] T023 Implement `MockToolAdapter` in `service/adapter/mock_adapter.py`: async `invoke()` that switches on `simulation` parameter: `ok` → return fixture result for tenant; `transient_then_ok` → raise `TransientError` on attempts 1-2, succeed on 3 (track attempt via a passed-in attempt number or counter); `transient_always` → always raise `TransientError`; `permanent_error` → raise `PermanentError`; `malformed_result` → return `{"unexpected": True}`; `timeout` → `await asyncio.sleep(2.0)` (will be cancelled by executor). Adapter receives fixture `tool_results` dict at init. **CRITICAL**: Adapter must actually execute behavior (sleep, raise, return), not return canned status strings.

### API Layer (Request/Response Schemas)

- [ ] T024 Define API Pydantic models in `service/api/schemas.py`: `InvokeRequest` with `conversation_id: str` (min_length=1, max_length=256), `capability: str` (min_length=1, max_length=256), `message: str` (min_length=1, max_length=2048), `simulation: SimulationMode = SimulationMode.OK` where `SimulationMode` is a `str` enum with values `ok`, `transient_then_ok`, `transient_always`, `permanent_error`, `malformed_result`, `timeout`. Model uses `ConfigDict(extra="ignore")`. `InvokeResponse`, `InvokeErrorResponse`, `ErrorEnvelope` models per data-model.md. `TraceResponse` model matching the trace contract.
- [ ] T025 [P] Implement FastAPI exception handlers in `service/api/dependencies.py` (or register in `main.py`): handlers for `AuthenticationError` → 401, `AuthorizationError` → 403, `CapabilityNotFoundError` → 404, `InputValidationError` → 422, `UpstreamUnavailableError` → 503, `UpstreamPermanentError` → 502, `InvalidToolResultError` → 502, `UpstreamTimeoutError` → 504. Override FastAPI's default `RequestValidationError` handler to return unified `{"error": {"code": "VALIDATION_ERROR", "message": ...}}`. All handlers return `JSONResponse` with the unified error envelope.

### App Factory & Fixture Loading

- [ ] T026 Implement `service/main.py`: FastAPI app factory `create_app()` that: (1) loads `fixtures/scenario.json`, (2) instantiates `TokenResolver` with principals, (3) instantiates `BillingAgent` and `SalesAgent` with tenant-specific fixture data, (4) builds `CapabilityRegistry` from agent registrations, (5) instantiates `MockToolAdapter` with fixture `tool_results`, (6) instantiates `TraceStore` and `ExecutionEngine`, (7) registers exception handlers, (8) calls `setup_logging()`, (9) includes API routes, (10) stores components on `app.state` for dependency injection. Add `if __name__ == "__main__": uvicorn.run(...)`.
- [ ] T027 Implement FastAPI dependencies in `service/api/dependencies.py`: `get_principal(authorization: str = Header(...))` extracts bearer token from `Authorization` header (validates `Bearer ` prefix, raises `AuthenticationError` if missing/malformed/unknown). `get_registry()`, `get_adapter()`, `get_executor()`, `get_trace_store()` return components from `request.app.state`.

**Checkpoint**: `python -c "from service.main import create_app; app = create_app()"` succeeds. All subpackages import cleanly. `GET /health` returns 200.

---

## Phase 3: User Story 1 — Invoke a Capability Successfully (Priority: P1) MVP

**Goal**: API consumer sends a valid request and receives the correct tenant-specific result.

**Independent Test**: `POST /invoke` with `demo-alpha-full` + `billing.summary` → 200 with `{"amount_due": 42.0, "currency": "USD"}`.

### Tests for User Story 1

- [ ] T028 [P] [US1] Unit test token resolution in `tests/unit/test_identity.py`: valid tokens return correct `Principal` (user_id, tenant_id, scopes); unknown token returns `None`; all 3 fixture tokens tested.
- [ ] T029 [P] [US1] Unit test capability registry in `tests/unit/test_registry.py`: known capability returns correct `AgentRegistration`; unknown capability returns `None`; scope check passes/fails correctly.
- [ ] T030 [P] [US1] Unit test agent tools in `tests/unit/test_agents.py`: `BillingAgent` has correct name, capabilities, tools; `SalesAgent` likewise; tool `result_schema` is the correct Pydantic model.
- [ ] T031 [P] [US1] Unit test mock adapter `ok` simulation in `tests/unit/test_adapter.py`: returns correct fixture result per tenant. Test `validate_tool_result()` accepts valid billing and sales results, rejects mismatched schemas.
- [ ] T032 [US1] Integration test happy path in `tests/integration/test_invoke.py`: `POST /invoke` with each of the 3 demo tokens × 2 capabilities (where scope allows) → HTTP 200, correct `tenant_id`, correct `result`, `status == "completed"`, `request_id` starts with `req-`, `conversation_id` echoed.

### Implementation for User Story 1

- [ ] T033 [US1] Implement execution engine stub in `service/executor/engine.py`: for this phase, implement only the `ok` path — single attempt, no retry/timeout logic yet. Async method `execute(adapter, agent_name, tool_name, tenant_id, capability, simulation, config) -> ExecutionResult` that calls `adapter.invoke()`, validates result, returns `ExecutionResult(status="completed", result=..., attempts=1, duration_ms=..., events=[...])`. Record `attempt_started` and `attempt_succeeded` trace events.
- [ ] T034 [US1] Implement `GET /health` endpoint in `service/api/routes.py`: returns `{"status": "ok"}`, no auth required.
- [ ] T035 [US1] Implement `POST /invoke` endpoint in `service/api/routes.py`: (1) authenticate via `get_principal` dependency, (2) resolve capability via registry (raise `CapabilityNotFoundError` if not found), (3) check scope (raise `AuthorizationError` if insufficient), (4) generate `request_id` as `f"req-{uuid.uuid4()}"`, (5) call execution engine, (6) store trace, (7) return `InvokeResponse`. Log execution start and completion with request_id, agent, outcome. Log warning for unknown body fields (Pydantic `extra="ignore"` handles silently, but add a model validator that detects and logs extras before discarding).
- [ ] T036 [US1] Implement trace storage in `service/traces/store.py`: class `TraceStore` with `store(trace: ExecutionTrace)` and `get(request_id, user_id, tenant_id) -> ExecutionTrace | None`. In-memory dict of `{request_id: (trace, created_at)}`. `get()` checks user_id + tenant_id match AND TTL not expired. Lazy expiration — no background task.
- [ ] T037 [US1] Implement `ExecutionTrace` and `TraceEvent` models in `service/traces/models.py` per data-model.md: fields `request_id`, `conversation_id`, `tenant_id`, `user_id`, `agent`, `capability`, `status`, `attempts`, `duration_ms`, `events: list[TraceEvent]`, `created_at: datetime`.
- [ ] T038 [US1] Implement `GET /traces/{request_id}` endpoint in `service/api/routes.py`: authenticate, look up trace in store (pass user_id and tenant_id for access control), return 404 if not found/not authorized/expired, return `TraceResponse` if found.

**Checkpoint**: `pytest tests/unit/test_identity.py tests/unit/test_registry.py tests/unit/test_agents.py tests/unit/test_adapter.py tests/integration/test_invoke.py -q` all pass. Server running, curl happy path works.

---

## Phase 4: User Story 2 — Reject Unauthorized Requests (Priority: P1)

**Goal**: Missing/invalid tokens → 401. Valid token without required scope → 403 before adapter is called.

**Independent Test**: `POST /invoke` with no token → 401; `demo-alpha-sales` + `billing.summary` → 403.

### Tests for User Story 2

- [ ] T039 [P] [US2] Integration test auth in `tests/integration/test_auth.py`: no `Authorization` header → 401 with `{"error": {"code": "UNAUTHORIZED", ...}}`; malformed header (no `Bearer` prefix) → 401; unknown token → 401; valid token insufficient scope → 403 with `{"error": {"code": "FORBIDDEN", ...}}`; unknown capability → 404 with `{"error": {"code": "CAPABILITY_NOT_FOUND", ...}}`; invalid body fields (blank conversation_id, too-long message, invalid simulation value) → 422 with `{"error": {"code": "VALIDATION_ERROR", ...}}`.
- [ ] T040 [P] [US2] Prove adapter not called on auth/authz failure in `tests/integration/test_auth.py`: inject a spy/mock adapter that records calls. After a 401 or 403 response, assert the spy was never invoked. This proves authorization happens before adapter invocation.

### Implementation for User Story 2

- [ ] T041 [US2] Verify `get_principal` dependency in `service/api/dependencies.py` handles all auth edge cases: missing `Authorization` header → raise `AuthenticationError`; header present but not `Bearer ` prefix → raise `AuthenticationError`; token present but unknown → raise `AuthenticationError`. No extra headers (`X-Tenant-ID`, `X-Scopes`) influence resolution.
- [ ] T042 [US2] Verify scope check in `POST /invoke` route raises `AuthorizationError` before executor is called. The check is: `if not registry.check_scope(registration, principal): raise AuthorizationError(...)`.
- [ ] T043 [US2] Verify unified error envelope for all 4xx responses: every exception handler returns `{"error": {"code": ..., "message": ...}}`. No stack traces, no token values, no raw details in error messages.

**Checkpoint**: All auth/authz integration tests pass. Spy confirms adapter never called for rejected requests.

---

## Phase 5: User Story 3 — Handle Transient Failures with Retries (Priority: P1)

**Goal**: `transient_then_ok` → 200 after exactly 3 attempts. `transient_always` → 503 after exactly 3 attempts. Backoff delays of 50 ms and 100 ms.

**Independent Test**: Invoke with `transient_then_ok`, verify 3 attempts in trace with correct delay events.

### Tests for User Story 3

- [ ] T044 [P] [US3] Unit test executor retry logic in `tests/unit/test_executor.py`: inject a mock adapter that fails transiently N times then succeeds. Inject a spy sleep function that records delays. Assert: `transient_then_ok` → exactly 3 adapter calls, sleep called with ~50ms and ~100ms (within jitter bounds), final result is success. `transient_always` → exactly 3 adapter calls, sleep called twice, raises `UpstreamUnavailableError`.
- [ ] T045 [P] [US3] Integration test retry simulation in `tests/integration/test_invoke.py` (extend): `POST /invoke` with `simulation=transient_then_ok` → 200, trace shows 3 attempts, events include `attempt_failed` with code `TRANSIENT` and `retry_scheduled` with `delay_ms` 50 and 100. `POST /invoke` with `simulation=transient_always` → 503 with error code `UPSTREAM_UNAVAILABLE`, trace shows 3 attempts.

### Implementation for User Story 3

- [ ] T046 [US3] Extend execution engine in `service/executor/engine.py` with full retry loop: attempt 1 → on transient error, record `attempt_failed(code=TRANSIENT)` + `retry_scheduled(delay_ms=config.backoff_delays_ms[i])`, await `sleep_fn(delay / 1000)` (injectable sleep function, defaults to `asyncio.sleep`), attempt 2 → same, attempt 3 → succeed or fail permanently. Use config `max_attempts` and `backoff_delays_ms`. Jitter: optional random addition to delay, capped so total delay ≤ 250 ms. Track all events in the trace events list.
- [ ] T047 [US3] Define `TransientError` and `PermanentError` exception types in `service/adapter/mock_adapter.py` (or `service/errors.py`). The adapter raises `TransientError` for transient simulations. The executor catches `TransientError` → retryable, any other exception → non-retryable.
- [ ] T048 [US3] Wire the injectable `sleep_fn` parameter through the executor constructor so tests can substitute a no-op or recording spy. Default to `asyncio.sleep` in production.

**Checkpoint**: `pytest tests/unit/test_executor.py tests/integration/test_invoke.py -q` all pass. Retry counts deterministic. Trace events verified.

---

## Phase 6: User Story 4 — Handle Permanent Errors and Malformed Results (Priority: P2)

**Goal**: `permanent_error` → 502 after 1 attempt. `malformed_result` → 502 after 1 attempt, bad payload not exposed.

**Independent Test**: Invoke with each simulation, verify exactly 1 attempt and correct error code.

### Tests for User Story 4

- [ ] T049 [P] [US4] Unit test adapter simulation modes in `tests/unit/test_adapter.py` (extend): `permanent_error` raises `PermanentError`; `malformed_result` returns `{"unexpected": True}`.
- [ ] T050 [P] [US4] Unit test executor permanent/malformed handling in `tests/unit/test_executor.py` (extend): permanent error → exactly 1 attempt, raises `UpstreamPermanentError`; malformed result → exactly 1 attempt, raises `InvalidToolResultError`; verify the malformed payload `{"unexpected": True}` is NOT in the error message or trace events.
- [ ] T051 [US4] Integration test in `tests/integration/test_invoke.py` (extend): `simulation=permanent_error` → HTTP 502, `error.code == "UPSTREAM_PERMANENT"`, trace `attempts == 1`; `simulation=malformed_result` → HTTP 502, `error.code == "INVALID_TOOL_RESULT"`, trace `attempts == 1`, response body does not contain `"unexpected"`.

### Implementation for User Story 4

- [ ] T052 [US4] Ensure executor in `service/executor/engine.py` handles: `PermanentError` → record `attempt_failed(code=PERMANENT)`, no retry, raise `UpstreamPermanentError`. Validation failure from `validate_tool_result()` → record `attempt_failed(code=INVALID_RESULT)`, no retry, raise `InvalidToolResultError` with safe message (no raw payload).
- [ ] T053 [US4] Verify error responses in `service/api/routes.py` catch executor exceptions and return the invocation failure envelope (`request_id`, `conversation_id`, `tenant_id`, `agent`, `status: "failed"`, `error`) not just the bare error envelope.

**Checkpoint**: All permanent/malformed tests pass. Bad payload never appears in response or trace.

---

## Phase 7: User Story 5 — Enforce Timeout and Cancel Slow Operations (Priority: P2)

**Goal**: `timeout` → 504 after 1 attempt in < 500 ms. Late adapter result does not overwrite the failed outcome.

**Independent Test**: Invoke with `simulation=timeout`, verify 504 and trace shows `TIMEOUT` event.

### Tests for User Story 5

- [ ] T054 [P] [US5] Unit test executor timeout in `tests/unit/test_executor.py` (extend): mock adapter that sleeps 2 seconds. Executor with 250 ms timeout → `UpstreamTimeoutError` raised, exactly 1 attempt, completes in < 500 ms wall clock. Verify the asyncio task is cancelled (adapter's sleep interrupted).
- [ ] T055 [US5] Integration test timeout in `tests/integration/test_timeout.py`: `POST /invoke` with `simulation=timeout` → HTTP 504, `error.code == "UPSTREAM_TIMEOUT"`, trace `attempts == 1`, event `attempt_failed(code=TIMEOUT)`. Response time < 500 ms. After response, verify trace is stable — a late adapter completion does not alter the stored trace or overwrite the `"failed"` status.

### Implementation for User Story 5

- [ ] T056 [US5] Implement per-attempt timeout in `service/executor/engine.py`: wrap `adapter.invoke()` with `asyncio.wait_for(coro, timeout=config.timeout_ms / 1000)`. Catch `asyncio.TimeoutError` → record `attempt_failed(code=TIMEOUT)`, raise `UpstreamTimeoutError`. Timeout is terminal — not retried (break out of retry loop immediately). The cancelled task's late result is discarded because the coroutine is cancelled by `wait_for`.
- [ ] T057 [US5] Test timeout cancellation safety in `tests/integration/test_timeout.py`: after a timed-out invocation, sleep briefly (e.g., 300 ms) to allow any late adapter result to arrive, then re-read the trace and assert it has not changed.

**Checkpoint**: Timeout test passes in < 500 ms. Late result does not corrupt trace.

---

## Phase 8: User Story 6 — Retrieve Execution Traces (Priority: P2)

**Goal**: After any invocation, the creating user can retrieve the trace. Other users/tenants cannot.

**Independent Test**: Invoke, extract `request_id`, GET trace → full trace structure. Cross-user GET → 404.

### Tests for User Story 6

- [ ] T058 [P] [US6] Unit test trace store in `tests/unit/test_traces.py`: store a trace, retrieve by same user+tenant → found; retrieve by different user same tenant → None; retrieve by different tenant → None; retrieve after TTL expires → None. Test lazy expiration: expired trace returns None, cleaned up on next read.
- [ ] T059 [US6] Integration test trace retrieval in `tests/integration/test_invoke.py` (extend): invoke with `transient_then_ok`, extract `request_id` from response, `GET /traces/{request_id}` with same token → 200, verify `attempts == 3`, `duration_ms > 0`, events list matches expected sequence (`attempt_started`, `attempt_failed`, `retry_scheduled`, ..., `attempt_succeeded`). `GET /traces/{request_id}` with different token (different user same tenant or different tenant) → 404.

### Implementation for User Story 6

- [ ] T060 [US6] Verify `GET /traces/{request_id}` in `service/api/routes.py` passes `user_id` and `tenant_id` from authenticated principal to `trace_store.get()`. Unknown or unauthorized trace → 404 (no distinction between nonexistent, unauthorized, or expired — same 404 for all).
- [ ] T061 [US6] Verify trace store TTL in `service/traces/store.py`: `get()` checks `datetime.utcnow() - created_at > timedelta(seconds=config.trace_ttl_seconds)`. If expired, delete from dict and return None.

**Checkpoint**: Trace retrieval works for all simulation modes. Cross-tenant/cross-user access blocked.

---

## Phase 9: User Story 7 — Concurrent Request Isolation (Priority: P3)

**Goal**: Overlapping invocations with different principals maintain independent state.

**Independent Test**: Two concurrent invocations with different tokens produce independent results and traces.

### Tests for User Story 7

- [ ] T062 [US7] Concurrent isolation test in `tests/integration/test_isolation.py`: use `asyncio.Event` barrier. Launch two async invocations — `demo-alpha-full` with `billing.summary` and `demo-beta-full` with `billing.summary` — both wait on a shared event before proceeding. After both complete: (1) each response has correct tenant-specific result (42.0 vs 99.0), (2) each has a unique `request_id`, (3) each trace is accessible only by its own token, (4) neither response contains the other's data.
- [ ] T063 [US7] Same-conversation-id isolation test in `tests/integration/test_isolation.py`: two invocations with the same `conversation_id` but different tokens. Verify neither inherits the other's attempt state, result, or trace.
- [ ] T064 [P] [US7] Tenant data isolation test in `tests/integration/test_isolation.py`: for each of the 3 demo tokens, invoke both allowed capabilities. Verify every response contains only the correct tenant's data. Cross-check: no response body for tenant-a contains "Beta Plus" and no response body for tenant-b contains "Alpha Starter".

**Checkpoint**: All concurrent/isolation tests pass with barriers, not sleeps.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Sanitization, documentation, acceptance validation, Docker verification.

- [ ] T065 [P] Implement log/trace sanitization test in `tests/integration/test_sanitization.py`: invoke with a distinctive secret string in the `message` field (e.g., `"SECRET_CANARY_12345"`). Capture all structured log output (use `caplog` or `capfd`). Assert the secret string appears nowhere in: logs, trace events, error responses. Also assert the bearer token value appears nowhere in logs or traces.
- [ ] T066 [P] Write `README.md`: exact native venv setup commands (create, activate, install, test, run), exact Docker commands (build, test, run), one success `curl` example with expected output, one failure `curl` example with expected output, list of implemented features, known limitations.
- [ ] T067 [P] Complete `SUBMISSION_NOTES.md`: fill all fields — time spent, Python version/OS, AI tools used, implemented/incomplete list, native clean-install command+result, Docker build status, final pytest output, final acceptance-check output, public PR link + 150-word contribution summary, where OIDC would enter, where real MCP would replace mock, why read-only retries differ from billing-change retries, in-memory limitations and first production change.
- [ ] T068 Run `python -m pytest -q` and paste actual output into `SUBMISSION_NOTES.md`
- [ ] T069 Start server (`uvicorn service.main:app --host 0.0.0.0 --port 8000 --workers 1`) and run `python tools/acceptance_check.py --base-url http://127.0.0.1:8000`. Paste actual output into `SUBMISSION_NOTES.md`.
- [ ] T070 Run full quickstart.md validation scenarios (all 10) against running server. Verify each matches expected output.
- [ ] T071 Docker verification: `docker build -t dharmendra-agent-gateway .`, `docker run --rm --network none dharmendra-agent-gateway python -m pytest -q`, `docker run --rm -p 127.0.0.1:8000:8000 dharmendra-agent-gateway`. Run acceptance check against container. Record results in `SUBMISSION_NOTES.md`.
- [ ] T072 Final security audit: grep codebase for any bearer token values in non-fixture files, any `print()` statements leaking data, any error messages containing raw payloads or stack traces. Fix any findings.

**Checkpoint**: All tests pass. Acceptance checker passes. Docker builds and runs. SUBMISSION_NOTES.md complete with actual output.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phases 3–9 (User Stories)**: All depend on Phase 2 completion
  - US1 (Phase 3): Can start immediately after Phase 2
  - US2 (Phase 4): Can start immediately after Phase 2 (parallel with US1)
  - US3 (Phase 5): Depends on US1 (needs working invoke endpoint + executor stub)
  - US4 (Phase 6): Depends on US3 (needs retry loop in executor)
  - US5 (Phase 7): Depends on US3 (needs executor with async patterns)
  - US6 (Phase 8): Depends on US1 (needs trace store + /traces endpoint)
  - US7 (Phase 9): Depends on US1 (needs working invoke for multiple principals)
- **Phase 10 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

```text
Phase 2 (Foundation)
    │
    ├──→ US1 (Happy Path) ──→ US3 (Retries) ──→ US4 (Permanent/Malformed)
    │         │                      │
    │         │                      └──→ US5 (Timeout)
    │         │
    │         ├──→ US6 (Traces)
    │         │
    │         └──→ US7 (Isolation)
    │
    └──→ US2 (Auth/Authz) — independent, parallel with US1
```

### Parallel Opportunities per Phase

**Phase 1**: T003, T004, T005, T006 all parallel
**Phase 2**: T008+T009 parallel; T010+T011 parallel; T013+T014 parallel; T015+T016 parallel; T017+T018 parallel; T021+T022 parallel; T024+T025 parallel
**Phase 3**: T028+T029+T030+T031 (all unit tests parallel); T036+T037 parallel
**Phase 4**: T039+T040 parallel
**Phase 5**: T044+T045 parallel
**Phase 6**: T049+T050 parallel
**Phase 7**: T054 parallel with other unit tests
**Phase 9**: T062+T063+T064 parallel
**Phase 10**: T065+T066+T067 all parallel

---

## Parallel Example: Phase 2 Foundation

```text
# Batch 1: Config + errors + logging (parallel, different files):
T007: service/config.py
T008: service/errors.py
T009: service/logging_config.py

# Batch 2: Identity models + protocol + agent protocols (parallel):
T010: service/identity/protocol.py
T011: service/identity/models.py
T013: service/agents/tools/base.py
T014: service/agents/base.py

# Batch 3: Tools + agents + registry (parallel where marked):
T015: service/agents/tools/billing_summary.py
T016: service/agents/tools/sales_offers.py
T019: service/registry/models.py

# Batch 4: Implementations depending on above:
T012: service/identity/token_resolver.py (needs T010, T011)
T017: service/agents/billing_agent.py (needs T14, T15)
T018: service/agents/sales_agent.py (needs T14, T16)
T020: service/registry/capability_registry.py (needs T19)

# Batch 5: Adapter + API schemas:
T021: service/adapter/protocol.py
T022: service/adapter/validators.py
T023: service/adapter/mock_adapter.py (needs T021)
T024: service/api/schemas.py
T025: service/api/dependencies.py

# Batch 6: App factory (needs everything above):
T026: service/main.py
T027: service/api/dependencies.py (finalize)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T006)
2. Complete Phase 2: Foundation (T007–T027)
3. Complete Phase 3: User Story 1 (T028–T038)
4. **STOP and VALIDATE**: `pytest -q` + manual curl + acceptance checker
5. This delivers: working `/health`, `/invoke` (ok simulation), `/traces` with full happy path

### Incremental Delivery

1. Setup + Foundation → skeleton running
2. US1 → MVP: invoke + trace works for `ok` simulation
3. US2 → Auth hardened: 401/403 proven
4. US3 → Retries work: `transient_then_ok` and `transient_always`
5. US4 → Permanent + malformed failures handled
6. US5 → Timeout enforced, cancellation proven
7. US6 → Trace retrieval with isolation
8. US7 → Concurrent correctness proven
9. Polish → Docs, Docker, sanitization, acceptance

Each increment adds value without breaking previous stories.

---

## Notes

- [P] tasks = different files, no dependencies between them
- [Story] label maps task to specific user story for traceability
- Tests are REQUIRED by the assessment, not optional
- Commit after each phase or logical task group
- Stop at any checkpoint to validate independently
- The assessment requires **actual pytest output** and **actual acceptance checker output** in SUBMISSION_NOTES.md — do not fabricate
