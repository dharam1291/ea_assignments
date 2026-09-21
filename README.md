# Agent Gateway

A small, observable agent gateway built with Python 3.11 and FastAPI. Resolves capabilities, enforces identity/scope-based permissions, invokes mock tool adapters with failure simulation, and records structured execution traces.

## Quick Start

### Native (macOS/Linux)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest -q

# Start server
uvicorn service.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Docker

```bash
docker build -t dharmendra-agent-gateway .
docker run --rm --network none dharmendra-agent-gateway python -m pytest -q
docker run --rm -p 127.0.0.1:8000:8000 dharmendra-agent-gateway
```

### Acceptance Check

```bash
python tools/acceptance_check.py --base-url http://127.0.0.1:8000
```

## API Endpoints

### `GET /health`
Unauthenticated health check.

### `POST /invoke`
Invoke an agent capability. Requires `Authorization: Bearer <token>`.

**Success example:**
```bash
curl -s http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-full" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"c1","capability":"billing.summary","message":"Show billing.","simulation":"ok"}'
```
```json
{
  "request_id": "req-...",
  "conversation_id": "c1",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "status": "completed",
  "result": {"amount_due": 42.0, "currency": "USD"}
}
```

**Failure example (insufficient scope):**
```bash
curl -s http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-sales" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"c1","capability":"billing.summary","message":"Show billing."}'
```
```json
{"error": {"code": "FORBIDDEN", "message": "Insufficient permissions."}}
```

### `GET /traces/{request_id}`
Retrieve execution trace. Same bearer auth; only the invoking principal can access their trace.

## Simulation Modes

| Mode | Behavior | HTTP Status |
|------|----------|-------------|
| `ok` | Returns fixture result | 200 |
| `transient_then_ok` | Fails first 2 attempts, succeeds on 3rd | 200 |
| `transient_always` | All attempts fail with transient error | 503 |
| `permanent_error` | Non-retryable error on first attempt | 502 |
| `malformed_result` | Invalid schema returned | 502 |
| `timeout` | 2s adapter sleep, 250ms timeout enforced | 504 |

## Architecture

```
service/
├── identity/          # Token resolution → Principal
├── registry/          # Capability → Agent + scope check
├── agents/            # BillingAgent, SalesAgent with Tool protocol
│   └── tools/         # BillingSummaryTool, SalesOffersTool
├── adapter/           # MockToolAdapter with simulation modes
├── executor/          # Retry engine with backoff/timeout
├── traces/            # In-memory trace store with TTL
├── api/               # FastAPI routes, schemas, dependencies
├── config.py          # Settings dataclass
├── errors.py          # Error hierarchy
├── logging_config.py  # Structured JSON logging
└── main.py            # App factory
```

## Implemented Features

- Identity resolution via opaque bearer tokens
- Scope-based authorization checked before adapter invocation
- Capability routing through agent registry
- Mock tool adapter with all 6 simulation modes
- Async retry with configurable backoff (50ms, 100ms) and 250ms timeout
- Injectable sleep function for deterministic test timing
- Structured execution traces with event-level detail
- Trace access control (same user + tenant)
- TTL-based trace expiration (1 hour)
- Structured JSON application logging with sensitive field redaction
- Input validation (whitespace, length limits, simulation enum)
- Extra/unknown body fields silently ignored
- Extra headers (X-Tenant-ID, X-Scopes) do not override principal

## Known Limitations

- In-memory state: all traces lost on restart
- Single-process: no horizontal scaling
- No persistent conversation history
- TTL expiration is lazy (on read), not background
