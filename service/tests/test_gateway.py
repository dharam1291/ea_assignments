"""
Comprehensive gateway tests covering all 7 required test categories:
1. Route both capabilities; validate result schemas
2. Reject invalid credentials and insufficient scopes; prove adapter not called
3. Tenant/user isolation for results and traces
4. All six simulation modes; verify retry delays with injected clock
5. Overlapping invocations with different principals
6. Timeout cancellation: late result must not turn failed into success
7. Log/trace redaction of secrets
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from service.tests.conftest import ALPHA_FULL, ALPHA_SALES, BETA_FULL, invoke_body


# ---------------------------------------------------------------------------
# 1. Route both capabilities; validate result schemas
# ---------------------------------------------------------------------------


class TestCapabilityRouting:
    @pytest.mark.asyncio
    async def test_billing_summary_returns_valid_schema(self, client):
        r = await client.post("/invoke", json=invoke_body("billing.summary"), headers=ALPHA_FULL)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["agent"] == "billing-agent"
        result = body["result"]
        assert isinstance(result["amount_due"], (int, float))
        assert isinstance(result["currency"], str)

    @pytest.mark.asyncio
    async def test_sales_offers_returns_valid_schema(self, client):
        r = await client.post("/invoke", json=invoke_body("sales.offers"), headers=ALPHA_FULL)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["agent"] == "sales-agent"
        result = body["result"]
        assert isinstance(result["offers"], list)
        for offer in result["offers"]:
            assert "id" in offer
            assert "name" in offer

    @pytest.mark.asyncio
    async def test_unknown_capability_returns_404(self, client):
        r = await client.post("/invoke", json=invoke_body("nonexistent.cap"), headers=ALPHA_FULL)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. Reject invalid credentials / insufficient scopes; adapter not called
# ---------------------------------------------------------------------------


class TestAuthenticationAuthorization:
    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_401(self, client):
        r = await client.post("/invoke", json=invoke_body())
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        r = await client.post("/invoke", json=invoke_body(), headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_auth_header_returns_401(self, client):
        r = await client.post("/invoke", json=invoke_body(), headers={"Authorization": "NotBearer token"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_bearer_returns_401(self, client):
        r = await client.post("/invoke", json=invoke_body(), headers={"Authorization": "Bearer "})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_insufficient_scope_returns_403(self, client):
        r = await client.post(
            "/invoke",
            json=invoke_body("billing.summary"),
            headers=ALPHA_SALES,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_adapter_not_called_on_auth_failure(self, app):
        with patch.object(app.state.adapter, "invoke", new_callable=AsyncMock) as mock_invoke:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/invoke", json=invoke_body(), headers={"Authorization": "Bearer bad"})
                mock_invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_adapter_not_called_on_scope_failure(self, app):
        with patch.object(app.state.adapter, "invoke", new_callable=AsyncMock) as mock_invoke:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post("/invoke", json=invoke_body("billing.summary"), headers=ALPHA_SALES)
                mock_invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_extra_headers_do_not_override_principal(self, client):
        r = await client.post(
            "/invoke",
            json=invoke_body("billing.summary"),
            headers={**ALPHA_SALES, "X-Tenant-ID": "tenant-x", "X-Scopes": "billing:read"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_input_validation_returns_422(self, client):
        r = await client.post(
            "/invoke",
            json={"conversation_id": "", "capability": "billing.summary", "message": "x"},
            headers=ALPHA_FULL,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_simulation_returns_422(self, client):
        body = invoke_body()
        body["simulation"] = "invalid_mode"
        r = await client.post("/invoke", json=body, headers=ALPHA_FULL)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 3. Tenant/user isolation for results and traces
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_a_gets_tenant_a_billing_result(self, client):
        r = await client.post("/invoke", json=invoke_body("billing.summary"), headers=ALPHA_FULL)
        assert r.json()["result"]["amount_due"] == 42.0
        assert r.json()["tenant_id"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_tenant_b_gets_tenant_b_billing_result(self, client):
        r = await client.post("/invoke", json=invoke_body("billing.summary"), headers=BETA_FULL)
        assert r.json()["result"]["amount_due"] == 99.0
        assert r.json()["tenant_id"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_cross_tenant_trace_not_accessible(self, client):
        r = await client.post("/invoke", json=invoke_body("billing.summary"), headers=ALPHA_FULL)
        request_id = r.json()["request_id"]

        trace_r = await client.get(f"/traces/{request_id}", headers=BETA_FULL)
        assert trace_r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_tenant_different_user_trace_not_accessible(self, client):
        r = await client.post("/invoke", json=invoke_body("sales.offers"), headers=ALPHA_FULL)
        request_id = r.json()["request_id"]

        trace_r = await client.get(f"/traces/{request_id}", headers=ALPHA_SALES)
        assert trace_r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_conversation_id_different_tenants_isolated(self, client):
        conv_id = "shared-conv"
        r_a = await client.post(
            "/invoke", json=invoke_body("billing.summary", conversation_id=conv_id), headers=ALPHA_FULL
        )
        r_b = await client.post(
            "/invoke", json=invoke_body("billing.summary", conversation_id=conv_id), headers=BETA_FULL
        )
        assert r_a.json()["result"]["amount_due"] == 42.0
        assert r_b.json()["result"]["amount_due"] == 99.0
        assert r_a.json()["request_id"] != r_b.json()["request_id"]

    @pytest.mark.asyncio
    async def test_own_trace_is_accessible(self, client):
        r = await client.post("/invoke", json=invoke_body("billing.summary"), headers=ALPHA_FULL)
        request_id = r.json()["request_id"]

        trace_r = await client.get(f"/traces/{request_id}", headers=ALPHA_FULL)
        assert trace_r.status_code == 200
        trace = trace_r.json()
        assert trace["request_id"] == request_id
        assert trace["capability"] == "billing.summary"

    @pytest.mark.asyncio
    async def test_nonexistent_trace_returns_404(self, client):
        r = await client.get("/traces/req-nonexistent", headers=ALPHA_FULL)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 4. Exercise all six simulation modes; count adapter calls, verify delays
# ---------------------------------------------------------------------------


class TestSimulationModes:
    @pytest.mark.asyncio
    async def test_ok_simulation(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="ok"), headers=ALPHA_FULL)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 1
        assert any(e["event"] == "attempt_succeeded" for e in trace["events"])

    @pytest.mark.asyncio
    async def test_transient_then_ok_simulation(self, client, sleep_calls):
        calls, _ = sleep_calls
        r = await client.post("/invoke", json=invoke_body(simulation="transient_then_ok"), headers=ALPHA_FULL)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 3
        assert len(calls) == 2
        assert calls[0] == pytest.approx(0.05)
        assert calls[1] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_transient_always_simulation(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="transient_always"), headers=ALPHA_FULL)
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "failed"
        assert body["error"]["code"] == "UPSTREAM_UNAVAILABLE"

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 3

    @pytest.mark.asyncio
    async def test_permanent_error_simulation(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="permanent_error"), headers=ALPHA_FULL)
        assert r.status_code == 502
        body = r.json()
        assert body["error"]["code"] == "UPSTREAM_PERMANENT"

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 1

    @pytest.mark.asyncio
    async def test_malformed_result_simulation(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="malformed_result"), headers=ALPHA_FULL)
        assert r.status_code == 502
        body = r.json()
        assert body["error"]["code"] == "INVALID_TOOL_RESULT"
        assert "unexpected" not in str(body)

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 1

    @pytest.mark.asyncio
    async def test_timeout_simulation(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="timeout"), headers=ALPHA_FULL)
        assert r.status_code == 504
        body = r.json()
        assert body["error"]["code"] == "UPSTREAM_TIMEOUT"

        trace_r = await client.get(f"/traces/{body['request_id']}", headers=ALPHA_FULL)
        trace = trace_r.json()
        assert trace["attempts"] == 1

    @pytest.mark.asyncio
    async def test_retry_delays_are_deterministic(self, client, sleep_calls):
        calls, _ = sleep_calls
        await client.post("/invoke", json=invoke_body(simulation="transient_always"), headers=ALPHA_FULL)
        assert len(calls) == 2
        assert calls[0] == pytest.approx(0.05)
        assert calls[1] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_trace_events_match_simulation_transient_then_ok(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="transient_then_ok"), headers=ALPHA_FULL)
        trace_r = await client.get(f"/traces/{r.json()['request_id']}", headers=ALPHA_FULL)
        events = trace_r.json()["events"]
        event_types = [e["event"] for e in events]
        assert event_types == [
            "attempt_started", "attempt_failed", "retry_scheduled",
            "attempt_started", "attempt_failed", "retry_scheduled",
            "attempt_started", "attempt_succeeded",
        ]


# ---------------------------------------------------------------------------
# 5. Overlapping invocations with different principals
# ---------------------------------------------------------------------------


class TestConcurrentIsolation:
    @pytest.mark.asyncio
    async def test_overlapping_invocations_isolated(self, app, sleep_calls):
        barrier = asyncio.Barrier(2)
        results = {}

        async def invoke_for(token_header, token_name, cap):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await barrier.wait()
                r = await c.post("/invoke", json=invoke_body(cap), headers=token_header)
                results[token_name] = r.json()

        await asyncio.gather(
            invoke_for(ALPHA_FULL, "alpha", "billing.summary"),
            invoke_for(BETA_FULL, "beta", "billing.summary"),
        )

        assert results["alpha"]["tenant_id"] == "tenant-a"
        assert results["beta"]["tenant_id"] == "tenant-b"
        assert results["alpha"]["result"]["amount_due"] == 42.0
        assert results["beta"]["result"]["amount_due"] == 99.0
        assert results["alpha"]["request_id"] != results["beta"]["request_id"]

    @pytest.mark.asyncio
    async def test_overlapping_traces_isolated(self, app, sleep_calls):
        barrier = asyncio.Barrier(2)
        request_ids = {}

        async def invoke_and_trace(token_header, name):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await barrier.wait()
                r = await c.post("/invoke", json=invoke_body("billing.summary"), headers=token_header)
                request_ids[name] = r.json()["request_id"]

        await asyncio.gather(
            invoke_and_trace(ALPHA_FULL, "alpha"),
            invoke_and_trace(BETA_FULL, "beta"),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            t_a = await c.get(f"/traces/{request_ids['alpha']}", headers=ALPHA_FULL)
            assert t_a.status_code == 200

            t_cross = await c.get(f"/traces/{request_ids['alpha']}", headers=BETA_FULL)
            assert t_cross.status_code == 404


# ---------------------------------------------------------------------------
# 6. Timeout cancellation: late result must not overwrite failed trace
# ---------------------------------------------------------------------------


class TestTimeoutCancellation:
    @pytest.mark.asyncio
    async def test_late_result_does_not_overwrite_trace(self, app, sleep_calls):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/invoke", json=invoke_body(simulation="timeout"), headers=ALPHA_FULL)
            assert r.status_code == 504
            body = r.json()
            request_id = body["request_id"]

            trace_r = await client.get(f"/traces/{request_id}", headers=ALPHA_FULL)
            assert trace_r.status_code == 200
            trace = trace_r.json()
            assert trace["status"] == "failed"
            assert any(e.get("code") == "TIMEOUT" for e in trace["events"])

            await asyncio.sleep(0.01)

            trace_r2 = await client.get(f"/traces/{request_id}", headers=ALPHA_FULL)
            trace2 = trace_r2.json()
            assert trace2["status"] == "failed"


# ---------------------------------------------------------------------------
# 7. Log/trace redaction of secrets
# ---------------------------------------------------------------------------


class TestSecretRedaction:
    @pytest.mark.asyncio
    async def test_secret_not_in_traces(self, client):
        secret = "SUPER_SECRET_VALUE_12345"
        body = invoke_body()
        body["message"] = f"Show billing for {secret}"
        r = await client.post("/invoke", json=body, headers=ALPHA_FULL)
        request_id = r.json()["request_id"]

        trace_r = await client.get(f"/traces/{request_id}", headers=ALPHA_FULL)
        trace_str = str(trace_r.json())
        assert secret not in trace_str
        assert "demo-alpha-full" not in trace_str

    @pytest.mark.asyncio
    async def test_secret_not_in_logs(self, client, caplog):
        secret = "LOG_SECRET_ABC789"
        body = invoke_body()
        body["message"] = f"secret is {secret}"

        with caplog.at_level(logging.DEBUG):
            await client.post("/invoke", json=body, headers=ALPHA_FULL)

        for record in caplog.records:
            formatted = record.getMessage()
            assert secret not in formatted
            assert "demo-alpha-full" not in formatted

    @pytest.mark.asyncio
    async def test_error_response_does_not_expose_raw_payload(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="malformed_result"), headers=ALPHA_FULL)
        body_str = str(r.json())
        assert "unexpected" not in body_str

    @pytest.mark.asyncio
    async def test_error_envelope_no_stack_trace(self, client):
        r = await client.post("/invoke", json=invoke_body(simulation="permanent_error"), headers=ALPHA_FULL)
        body_str = str(r.json())
        assert "Traceback" not in body_str
        assert "File " not in body_str


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_each_invoke_gets_unique_request_id(self, client):
        ids = set()
        for _ in range(5):
            r = await client.post("/invoke", json=invoke_body(), headers=ALPHA_FULL)
            ids.add(r.json()["request_id"])
        assert len(ids) == 5

    @pytest.mark.asyncio
    async def test_request_id_format(self, client):
        r = await client.post("/invoke", json=invoke_body(), headers=ALPHA_FULL)
        rid = r.json()["request_id"]
        assert rid.startswith("req-")
        assert len(rid) > 10

    @pytest.mark.asyncio
    async def test_unknown_body_fields_ignored(self, client):
        body = invoke_body()
        body["user_id"] = "hacker"
        body["tenant_id"] = "evil-tenant"
        r = await client.post("/invoke", json=body, headers=ALPHA_FULL)
        assert r.status_code == 200
        assert r.json()["tenant_id"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_trace_unauthenticated_returns_401(self, client):
        r = await client.get("/traces/some-id")
        assert r.status_code == 401
