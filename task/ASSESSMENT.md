# Take-home: a small, observable agent gateway

**Candidate:** Dharmendra Singh · **Role:** SE III, hands-on contractor  
**Time limit:** four hours, including setup, tests and documentation  
**Deliverable:** runnable Python code, not pseudocode or an architecture-only submission

## Why this exercise

This builds on your LMOS/ARC, OpenID, agent-observability and asynchronous execution experience. Build a small slice of an agent platform: resolve a capability, enforce permissions, invoke a local agent/tool adapter and explain what happened through a trace.

We are evaluating implementation, failure handling and code ownership. We are **not** asking you to reproduce LMOS, deliver free production work, or build a research model. All data is synthetic. Do not use employer code, credentials or private documents.

Stop at four hours. Submit what works and clearly list anything unfinished. Extra features or additional hours do not earn extra credit. AI tools and documentation are welcome; you must personally run, test and understand your submission.

## What you receive

- `fixtures/scenario.json`: three demo identities, two agent registrations and synthetic tool results.
- `tools/acceptance_check.py`: a dependency-free HTTP checker. Run it against your service before submitting. Răzvan will use the same checks.
- `SUBMISSION_NOTES.md`: a short handoff template.

The included checker runs; **the gateway is yours to implement**. It does not replace your own unit/integration tests.

## Build this slice

Use Python 3.11 or later and FastAPI. One process with in-memory state is sufficient. Provide separate, testable boundaries for:

1. **Identity:** resolve the supplied opaque bearer token to a principal from the fixture.
2. **Registry/router:** resolve `capability` using the supplied registrations; apply the required scope.
3. **Agent/tool adapter:** invoke the selected agent's local, read-only mock tool and validate its output.
4. **Execution policy:** enforce bounded attempts, asynchronous waits and a timeout.
5. **Trace:** record the selected agent, attempts, timing and final outcome without sensitive payloads.

The registry may be a dictionary loaded from JSON. Do not require natural-language routing: the request explicitly selects a capability. Do not allow the message text to change identity, scopes, agent selection or the tool allowlist. Adding another registered capability should not require rewriting the API endpoint or retry loop.

### Deliberate simplifications

- Demo tokens are **not JWTs**. Validate them by exact lookup; no Keycloak server, token signing or custom cryptography is needed. Document how verified OIDC claims would replace this adapter in production.
- The local tool adapter is **MCP-inspired, not an MCP implementation**. No real MCP server, model, browser, telecom backend or external API is required. Do not label it MCP-compliant.
- Operations are read-only. No payments, approvals, distributed transactions, durable idempotency or restart recovery are required.
- No UI, voice processing, RAG, database, Kubernetes, LMOS installation or cloud deployment.
- `conversation_id` is a correlation label, not a credential. Shared conversation IDs must not share authorization or results. You do not need to store conversation history.

## API contract

### `GET /health`

Unauthenticated. Return HTTP 200 and `{"status":"ok"}`.

### `POST /invoke`

Accept `Authorization: Bearer <demo-token>`. The request is:

```json
{
  "conversation_id": "conversation-001",
  "capability": "billing.summary",
  "message": "Show my billing summary.",
  "simulation": "ok"
}
```

Use nonblank strings for `conversation_id`, `capability` and `message`; limit each to a documented reasonable length. `simulation` is optional and defaults to `ok`. Restrict it to the six values below. Invalid input returns 422. Unknown, nonblank capability returns 404.

The fixture is authoritative:

| Capability | Agent | Required scope |
| --- | --- | --- |
| `billing.summary` | `billing-agent` | `billing:read` |
| `sales.offers` | `sales-agent` | `sales:read` |

| Demo token | Principal | Tenant | Access |
| --- | --- | --- | --- |
| `demo-alpha-full` | `user-a` | `tenant-a` | Both capabilities |
| `demo-alpha-sales` | `user-c` | `tenant-a` | Sales only |
| `demo-beta-full` | `user-b` | `tenant-b` | Both capabilities |

Missing, malformed or unknown credentials return 401. A known principal without the required scope receives 403 **before the adapter is called**. Do not trust extra headers such as `X-Tenant-ID` or `X-Scopes` to change the principal. No tenant or user override belongs in the request body; ignore or reject unknown body fields.

Normal success returns HTTP 200:

```json
{
  "request_id": "server-generated-unique-id",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "status": "completed",
  "result": {"amount_due": 42.0, "currency": "USD"}
}
```

Return the correct tenant's result from `fixtures/scenario.json`. Validate the result structure for each capability, rather than accepting arbitrary strings/objects. Each HTTP invocation gets its own request ID, even if the conversation ID is reused. There is no deduplication requirement for these read-only calls.

### Failure simulation and recovery

Implement the following behavior **inside the mock adapter**. The execution layer must observe the adapter's output/error, classify it and react. Do not simply return a canned status/trace based on the simulation field without invoking the adapter.

| Simulation | Adapter behavior | Required service behavior |
| --- | --- | --- |
| `ok` | Valid fixture result | 200; 1 attempt |
| `transient_then_ok` | First 2 attempts raise a transient error; third succeeds | 200; exactly 3 attempts |
| `transient_always` | Every attempt raises a transient error | 503; stop after 3 attempts |
| `permanent_error` | A non-retryable error on the first attempt | 502; 1 attempt |
| `malformed_result` | Wrong-schema result, e.g. `{"unexpected":true}` | 502; 1 attempt; do not expose the bad payload |
| `timeout` | Await a slow operation, e.g. 2 seconds | Enforce a 250 ms per-attempt timeout; 504; 1 attempt; stop/cancel the local task |

Retry transient errors only, with asynchronous backoff: 50 ms before attempt 2, 100 ms before attempt 3. Optional nonnegative jitter may increase either delay, but neither may exceed 250 ms; make tests deterministic. Keep attempt state local to each invocation. For this exercise timeout is terminal, not retried. Explain why this read-only retry policy cannot automatically be used for a tool that changes billing data.

The status for those execution failures must use this envelope:

```json
{
  "request_id": "server-generated-unique-id",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "status": "failed",
  "error": {"code": "UPSTREAM_TIMEOUT", "message": "The tool did not respond in time."}
}
```

Use error codes `UPSTREAM_UNAVAILABLE`, `UPSTREAM_PERMANENT`, `INVALID_TOOL_RESULT` and `UPSTREAM_TIMEOUT` for the respective failure rows. The human-readable message is your choice. Never expose stack traces, token values, raw messages or invalid tool payloads in errors. Ordinary input/authentication/authorization error envelopes are your choice; a trace is not required for those rejected requests.

### `GET /traces/{request_id}`

Requires the same bearer authentication. Only the **same principal in the same tenant** that invoked the request can read its trace. Return 404 for unknown or inaccessible trace IDs, including requests from another user in the same tenant. Do not implement an admin bypass.

Store one trace for every completed or failed adapter execution, available before `/invoke` responds. In-memory storage is sufficient. Include at least:

```json
{
  "request_id": "server-generated-unique-id",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "capability": "billing.summary",
  "status": "completed",
  "attempts": 3,
  "duration_ms": 153.2,
  "events": [
    {"event":"attempt_started", "attempt":1},
    {"event":"attempt_failed", "attempt":1, "code":"TRANSIENT"},
    {"event":"retry_scheduled", "attempt":1, "delay_ms":50},
    {"event":"attempt_started", "attempt":2},
    {"event":"attempt_failed", "attempt":2, "code":"TRANSIENT"},
    {"event":"retry_scheduled", "attempt":2, "delay_ms":100},
    {"event":"attempt_started", "attempt":3},
    {"event":"attempt_succeeded", "attempt":3}
  ]
}
```

Use those event names/fields. A failed attempt uses code `TRANSIENT`, `PERMANENT`, `INVALID_RESULT` or `TIMEOUT`. Attempts are numbered from 1. Extra safe metadata is fine. Derive timings and events from execution; do not manufacture them. No token counts are expected because no LLM is called.

Add structured application logs for execution start, retry and completion/failure. Include request ID, agent, attempt and outcome where relevant. Debug logging must not record bearer tokens, raw message text or tool-result bodies. No logging/metrics vendor is required.

## Tests you must write and run

Use `pytest`. The public HTTP checker is useful but not sufficient: source-level tests must prove internal behavior, not just a fabricated response.

1. Route both capabilities; validate their result schemas.
2. Reject invalid credentials and insufficient scopes; prove the adapter was not called.
3. Keep tenants/users isolated for results and trace lookup, including the same conversation ID.
4. Exercise all six simulation modes; count actual adapter calls and verify retry delays with an injected clock/sleeper or spy.
5. Send at least two overlapping invocations with different principals. Prove neither inherits the other's attempt state, result or trace. Prefer a synchronization event/barrier to a timing-only assertion.
6. Test timeout cancellation: a late adapter result must not turn the failed request into success or overwrite its trace.
7. Capture logs and traces with a distinctive secret string in the input; assert neither the secret nor the bearer token appears.

Parameterized tests are fine. Test names/count alone are not evidence. Assertions must fail when the corresponding behavior is broken. A blanket catch-all that converts defects into success is not acceptable.

## How it must run

Supply `requirements.txt` **or** `pyproject.toml` with runtime and test dependencies, plus a Dockerfile. Pick and document a supported Python version. Both the test suite and server must use the same installed project.

Required container contract, from the submitted repository root:

```bash
docker build -t dharmendra-agent-gateway .
docker run --rm --network none dharmendra-agent-gateway python -m pytest -q
docker run --rm -p 127.0.0.1:8000:8000 dharmendra-agent-gateway
```

The default container command starts the server on `0.0.0.0:8000`, with **one worker**. The app and tests must need no outbound network access once dependencies are installed. Include sample data inside the image. Do not bake credentials into it. A non-root runtime user is preferred.

From another terminal:

```bash
python tools/acceptance_check.py --base-url http://127.0.0.1:8000
```

Also document a native virtual-environment path, including activation commands for your OS, dependency installation, `python -m pytest -q` and server startup. If Docker is unavailable on your machine, run and prove the native path, include a Dockerfile and state explicitly that the image is unverified. Do not claim a build you did not run. That limitation alone is not an automatic rejection.

## Handoff

Submit one ZIP or repository containing code, fixture, tests, dependency manifest, Dockerfile, README and completed `SUBMISSION_NOTES.md`. Include actual final test and acceptance-check output. Exclude `.venv`, caches, model weights and credentials.

The README must contain exact commands, one success example, one failure example, implemented features and known limitations. In the notes, link one of your own public LMOS/ARC/Browser Use/AgC changes and explain in 150 words what you personally changed and how that experience informed this design. No private employer code is needed.

Suggested time split: setup 20 minutes; routing/authentication/adapters 75; failures/traces 45; tests 70; clean-run/documentation 30. Simplify when necessary; do not exceed four hours.

## How we will evaluate it

| Area | Weight |
| --- | ---: |
| Reproducible execution and honest handoff | 20% |
| Identity, permissions and trace isolation | 20% |
| Capability routing and adapter design | 15% |
| Failure policy and asynchronous correctness | 20% |
| Meaningful, executable tests | 15% |
| Useful, privacy-conscious observability | 10% |

No bonus for extra infrastructure, frameworks or a polished UI. A genuine security failure remains material even if the weighted score is otherwise high. We will distinguish a disclosed time-box omission from an implementation incorrectly presented as complete.

## Next round with Răzvan

Be ready to run the project and tests on your own machine, trace one request through your code, reproduce one failure, and implement a small change with a test. You may use documentation and AI under the same rules. We are assessing your ability to inspect, modify, debug and own the implementation, not decorator memorization.

## Background references (no installation required)

- [LMOS overview](https://eclipse.dev/lmos/docs/introduction/)
- [ARC metrics contribution #323](https://github.com/eclipse-lmos/arc/pull/323)
- [ARC View OpenID contribution #26](https://github.com/eclipse-lmos/arc-view/pull/26)
- [Browser Use asynchronous pause/resume contribution #1466](https://github.com/browser-use/browser-use/pull/1466)
- [AgC local-tool support contribution #196](https://github.com/masaic-ai-platform/AgC/pull/196)

These explain the exercise's relevance; authorship or a merged PR is not a substitute for the implementation and review.
