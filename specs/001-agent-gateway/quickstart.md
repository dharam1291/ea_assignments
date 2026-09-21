# Quickstart Validation Guide: Observable Agent Gateway

**Date**: 2026-09-21 | **Spec**: [spec.md](spec.md) | **Contract**: [contracts/api.md](contracts/api.md)

## Prerequisites

- Python 3.11+
- Docker (optional, for container validation)

## Setup (Native)

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

## Run Tests

```bash
python -m pytest -q
```

**Expected**: All tests pass, exit code 0, completes in < 30 seconds.

## Start Server

```bash
uvicorn service.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## Validation Scenarios

### 1. Health Check

```bash
curl -s http://127.0.0.1:8000/health | python -m json.tool
```

**Expected**: `{"status": "ok"}`

### 2. Successful Invocation (billing)

```bash
curl -s -X POST http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-full" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-001","capability":"billing.summary","message":"Show billing."}' \
  | python -m json.tool
```

**Expected**: HTTP 200 with `status: "completed"`, `result: {"amount_due": 42.0, "currency": "USD"}`, `tenant_id: "tenant-a"`, and a `request_id` starting with `req-`.

### 3. Tenant Isolation (different tenant same capability)

```bash
curl -s -X POST http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-beta-full" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-002","capability":"billing.summary","message":"Show billing."}' \
  | python -m json.tool
```

**Expected**: HTTP 200 with `amount_due: 99.0` and `tenant_id: "tenant-b"`.

### 4. Unauthorized (missing token)

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-003","capability":"billing.summary","message":"test"}'
```

**Expected**: HTTP 401 with `{"error": {"code": "UNAUTHORIZED", ...}}`

### 5. Forbidden (insufficient scope)

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-sales" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-004","capability":"billing.summary","message":"test"}' \
  | python -m json.tool
```

**Expected**: HTTP 403 with `{"error": {"code": "FORBIDDEN", ...}}`

### 6. Transient Recovery

```bash
curl -s -X POST http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-full" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-005","capability":"billing.summary","message":"test","simulation":"transient_then_ok"}' \
  | python -m json.tool
```

**Expected**: HTTP 200 with `status: "completed"`. Trace will show 3 attempts.

### 7. Timeout Failure

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/invoke \
  -H "Authorization: Bearer demo-alpha-full" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv-006","capability":"billing.summary","message":"test","simulation":"timeout"}' \
  | python -m json.tool
```

**Expected**: HTTP 504 with `error.code: "UPSTREAM_TIMEOUT"`. Response arrives in < 500 ms.

### 8. Trace Retrieval

Use the `request_id` from scenario 2:

```bash
curl -s http://127.0.0.1:8000/traces/<request_id> \
  -H "Authorization: Bearer demo-alpha-full" \
  | python -m json.tool
```

**Expected**: HTTP 200 with trace showing `attempts: 1`, `status: "completed"`, and events list.

### 9. Trace Isolation (cross-tenant)

Use the same `request_id` from scenario 2, but a different token:

```bash
curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/traces/<request_id> \
  -H "Authorization: Bearer demo-beta-full"
```

**Expected**: HTTP 404.

### 10. Acceptance Checker

```bash
python tools/acceptance_check.py --base-url http://127.0.0.1:8000
```

**Expected**: All checks pass.

## Docker Validation

```bash
docker build -t dharmendra-agent-gateway .
docker run --rm --network none dharmendra-agent-gateway python -m pytest -q
docker run --rm -p 127.0.0.1:8000:8000 dharmendra-agent-gateway
```

Then repeat scenarios 1–10 against `http://127.0.0.1:8000`.
