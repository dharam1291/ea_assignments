# Research: Observable Agent Gateway

**Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

## R1: Async Retry with Backoff in FastAPI

**Decision**: Use `asyncio.sleep()` for backoff delays and `asyncio.wait_for()` for per-attempt timeouts, with an injectable sleep function for test determinism.

**Rationale**: FastAPI is async-native, so the retry loop must be non-blocking. `asyncio.wait_for()` provides built-in timeout + cancellation. Injecting the sleep function allows tests to verify delays without wall-clock waits.

**Alternatives considered**:
- `tenacity` library: adds a dependency for a simple 3-attempt loop; overkill for this scope.
- Threading with `concurrent.futures`: mixes paradigms; loses cancellation semantics that `asyncio` provides natively.

## R2: TTL-Based Trace Expiration

**Decision**: Wrap the in-memory trace dict with a TTL check on read. Store `(trace, created_at)` tuples. On each read, check if `now - created_at > ttl` and return 404 if expired. Run a lazy cleanup — no background thread.

**Rationale**: Lazy expiration avoids a background task that complicates single-worker shutdown. Traces are small and infrequent in this exercise; a background sweeper would be over-engineering. The TTL is configurable via `config.py`.

**Alternatives considered**:
- Background `asyncio.Task` sweeper: adds shutdown coordination complexity for no measurable benefit at exercise scale.
- `cachetools.TTLCache`: adds a dependency; the custom wrapper is ~10 lines.

## R3: Pydantic v2 Strict Validation for Tool Results

**Decision**: Define per-capability Pydantic models (`BillingSummaryResult`, `SalesOffersResult`) and validate adapter output against them. Use `model_validate()` with strict mode.

**Rationale**: The spec requires validating result structure per capability (FR-007). Pydantic v2 is already a dependency via FastAPI. Per-capability models are explicit, testable, and produce clear validation errors.

**Alternatives considered**:
- JSON Schema validation with `jsonschema` library: adds a dependency; Pydantic already does this.
- Dict key/type checking: fragile, no schema documentation, harder to test.

## R4: Structured Logging with Python `logging`

**Decision**: Use Python's standard `logging` module with a custom `json` formatter that outputs one JSON object per line. Configure via `logging_config.py` at app startup. Filter sensitive fields (token, message, tool result) from all log records.

**Rationale**: Clarification session chose Python `logging` (not a third-party library). JSON-line output is machine-parseable for production log aggregation. A custom formatter keeps the dependency count at zero.

**Alternatives considered**:
- `structlog`: excellent library but adds a dependency the constitution discourages.
- `logging.basicConfig` with default format: not structured, not machine-parseable.

## R5: Unified Error Envelope via Exception Handlers

**Decision**: Define custom exception classes (`AuthenticationError`, `AuthorizationError`, `CapabilityNotFoundError`, `ValidationError`) and register FastAPI exception handlers that return the unified `{"error": {"code": "...", "message": "..."}}` envelope. Override FastAPI's default `RequestValidationError` handler.

**Rationale**: Clarification session chose unified envelope (FR-021). Custom exception handlers are the idiomatic FastAPI pattern for consistent error responses. This avoids scattering `JSONResponse` construction across endpoint handlers.

**Alternatives considered**:
- Middleware-based error wrapping: catches too broadly; loses type information.
- Return error dicts directly in each endpoint: duplicates envelope construction; error-prone.

## R6: Request ID Format

**Decision**: Use `f"req-{uuid.uuid4()}"` for request ID generation. Generate in the endpoint handler, pass through all layers.

**Rationale**: Clarification session chose prefixed UUID4. The `req-` prefix makes IDs instantly recognizable in logs. UUID4 provides collision resistance without a counter or database.

**Alternatives considered**:
- ULID: requires `python-ulid` dependency; time-sorting is not a requirement.
- Sequential counter: not safe across restarts; not unique across instances if scaled.

## R7: Agent as First-Class Entity with Owned Tools

**Decision**: Model agents as concrete classes implementing a `BaseAgent` Protocol. Each agent declares its `name`, `capabilities`, and owns a `tools` dict mapping tool names to `Tool` Protocol implementations. The registry maps capability → agent instance. The adapter invokes the agent's tool, not a free function.

**Rationale**: The assessment says "invoke the selected agent's local, read-only mock tool." Agents are not passive registry entries — they are the unit of registration, discovery, and invocation. A concrete agent that owns its tools mirrors a real agent platform (LMOS/ARC pattern): adding a new agent means one class + one fixture entry, zero changes elsewhere.

**Alternatives considered**:
- Flat registry (capability → tool function): loses the agent abstraction; "adding a new capability" requires touching multiple unrelated files.
- Agent as a dict/dataclass without tool ownership: tools float disconnected from their agent; no clear ownership boundary.

## R8: Adapter Interface Design

**Decision**: Define a `ToolAdapter` Protocol with a single async method `invoke(agent, tool, tenant_id, simulation) -> dict`. The mock adapter receives the resolved agent and tool objects, simulates the configured behavior, and returns fixture data. The execution layer depends on the Protocol, not the implementation.

**Rationale**: Constitution Principle VI requires swappable adapters. The adapter receives the agent and tool (already resolved by the registry) so it can produce the correct tenant-specific result. In production, a remote adapter would replace the mock by calling a real MCP endpoint using the agent/tool identifiers.

**Alternatives considered**:
- Adapter that re-resolves the agent internally: duplicates registry logic; violates single-responsibility.
- Callable/function instead of Protocol: loses semantic grouping; harder to type-check and mock in tests.

## R9: Concurrency Test Strategy

**Decision**: Use `asyncio.Event` barriers in tests. Both test invocations wait on a shared event before proceeding, ensuring overlap. Assert results independently after both complete.

**Rationale**: Spec requires synchronization barriers, not timing-based assertions (FR-020, SC-005). `asyncio.Event` is deterministic and built-in.

**Alternatives considered**:
- `threading.Barrier`: mixes threading into an async test suite.
- Sleep-based overlap: non-deterministic; explicitly rejected by the spec.
