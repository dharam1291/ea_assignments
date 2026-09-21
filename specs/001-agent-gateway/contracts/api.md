# API Contract: Observable Agent Gateway

**Date**: 2026-09-21 | **Base URL**: `http://localhost:8000`

## Endpoints

### GET /health

Unauthenticated health check.

**Request**: No headers or body required.

**Response** (200):
```json
{"status": "ok"}
```

---

### POST /invoke

Invoke an agent capability through the gateway.

**Headers**:
- `Authorization: Bearer <demo-token>` (required)
- `Content-Type: application/json`

**Request Body**:
```json
{
  "conversation_id": "string (1-256 chars, non-blank, required)",
  "capability": "string (1-256 chars, non-blank, required)",
  "message": "string (1-2048 chars, non-blank, required)",
  "simulation": "enum (optional, default: ok)"
}
```

**Simulation values**: `ok`, `transient_then_ok`, `transient_always`, `permanent_error`, `malformed_result`, `timeout`

**Unknown body fields**: Silently ignored (not processed), warning logged.

**Success Response** (200):
```json
{
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "status": "completed",
  "result": {"amount_due": 42.0, "currency": "USD"}
}
```

**Failure Response** (502 | 503 | 504):
```json
{
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "status": "failed",
  "error": {"code": "UPSTREAM_TIMEOUT", "message": "The tool did not respond in time."}
}
```

**Error Responses**:

| Status | Code | Condition |
|--------|------|-----------|
| 401 | `UNAUTHORIZED` | Missing, malformed, or unknown bearer token |
| 403 | `FORBIDDEN` | Valid token but principal lacks required scope |
| 404 | `CAPABILITY_NOT_FOUND` | Unknown capability value |
| 422 | `VALIDATION_ERROR` | Invalid/missing body fields or invalid simulation value |
| 502 | `UPSTREAM_PERMANENT` | Adapter returned non-retryable error |
| 502 | `INVALID_TOOL_RESULT` | Adapter returned malformed result |
| 503 | `UPSTREAM_UNAVAILABLE` | Transient errors exhausted all 3 retry attempts |
| 504 | `UPSTREAM_TIMEOUT` | Adapter exceeded 250 ms per-attempt timeout |

**All error responses** use unified envelope:
```json
{
  "error": {"code": "<ERROR_CODE>", "message": "<human-readable>"}
}
```

Note: 502/503/504 responses from adapter failures include the full invocation envelope (`request_id`, `conversation_id`, `tenant_id`, `agent`, `status: "failed"`, `error`).

---

### GET /traces/{request_id}

Retrieve the execution trace for a completed or failed invocation.

**Headers**:
- `Authorization: Bearer <demo-token>` (required, must be same principal+tenant as original invocation)

**Path Parameters**:
- `request_id`: The `request_id` returned from `/invoke`

**Success Response** (200):
```json
{
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "conversation-001",
  "tenant_id": "tenant-a",
  "agent": "billing-agent",
  "capability": "billing.summary",
  "status": "completed",
  "attempts": 3,
  "duration_ms": 153.2,
  "events": [
    {"event": "attempt_started", "attempt": 1},
    {"event": "attempt_failed", "attempt": 1, "code": "TRANSIENT"},
    {"event": "retry_scheduled", "attempt": 1, "delay_ms": 50},
    {"event": "attempt_started", "attempt": 2},
    {"event": "attempt_failed", "attempt": 2, "code": "TRANSIENT"},
    {"event": "retry_scheduled", "attempt": 2, "delay_ms": 100},
    {"event": "attempt_started", "attempt": 3},
    {"event": "attempt_succeeded", "attempt": 3}
  ]
}
```

**Error Responses**:

| Status | Code | Condition |
|--------|------|-----------|
| 401 | `UNAUTHORIZED` | Missing, malformed, or unknown bearer token |
| 404 | (standard 404) | Unknown request_id, different user, different tenant, or expired trace |

**Access Control**: Only the same `user_id` AND `tenant_id` that created the trace can read it. All other lookups return 404 (no distinction between nonexistent, unauthorized, or expired).

---

## Capability Registry

| Capability | Agent | Required Scope | Result Schema |
|-----------|-------|----------------|---------------|
| `billing.summary` | `billing-agent` | `billing:read` | `{amount_due: float, currency: string}` |
| `sales.offers` | `sales-agent` | `sales:read` | `{offers: [{id: string, name: string}]}` |

## Principal Registry

| Token | User | Tenant | Scopes |
|-------|------|--------|--------|
| `demo-alpha-full` | `user-a` | `tenant-a` | `billing:read`, `sales:read` |
| `demo-alpha-sales` | `user-c` | `tenant-a` | `sales:read` |
| `demo-beta-full` | `user-b` | `tenant-b` | `billing:read`, `sales:read` |

## Execution Policy

| Simulation | Adapter Behavior | HTTP Status | Attempts | Error Code |
|-----------|-----------------|-------------|----------|------------|
| `ok` | Returns valid fixture result | 200 | 1 | — |
| `transient_then_ok` | Fails 2x then succeeds | 200 | 3 | — |
| `transient_always` | Always fails transiently | 503 | 3 | `UPSTREAM_UNAVAILABLE` |
| `permanent_error` | Non-retryable error | 502 | 1 | `UPSTREAM_PERMANENT` |
| `malformed_result` | Wrong-schema result | 502 | 1 | `INVALID_TOOL_RESULT` |
| `timeout` | Sleeps ~2 seconds | 504 | 1 | `UPSTREAM_TIMEOUT` |

**Retry backoff**: 50 ms before attempt 2, 100 ms before attempt 3. Optional jitter, max delay 250 ms.

**Timeout**: 250 ms per attempt. Terminal — not retried. Local task cancelled.
