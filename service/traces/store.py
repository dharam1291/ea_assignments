from datetime import datetime, timedelta, timezone

from service.core.config import Settings
from service.traces.models import ExecutionTrace


class TraceStore:
    def __init__(self, settings: Settings) -> None:
        self._traces: dict[str, ExecutionTrace] = {}
        self._ttl = timedelta(seconds=settings.trace_ttl_seconds)

    def store(self, trace: ExecutionTrace) -> None:
        self._traces[trace.request_id] = trace

    def get(self, request_id: str, user_id: str, tenant_id: str) -> ExecutionTrace | None:
        trace = self._traces.get(request_id)
        if trace is None:
            return None

        if datetime.now(timezone.utc) - trace.created_at > self._ttl:
            del self._traces[request_id]
            return None

        if trace.user_id != user_id or trace.tenant_id != tenant_id:
            return None

        return trace
