import asyncio
import logging
import time
from typing import Awaitable, Callable

from service.adapter.protocol import ToolAdapter
from service.adapter.validators import validate_tool_result
from service.core.config import Settings
from service.core.errors import (
    InvalidToolResultError,
    PermanentError,
    TransientError,
)
from service.executor.models import ExecutionResult
from service.traces.models import TraceEvent

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(
        self,
        settings: Settings,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._sleep_fn = sleep_fn or asyncio.sleep

    async def execute(
        self,
        adapter: ToolAdapter,
        agent_name: str,
        tool_name: str,
        tenant_id: str,
        capability: str,
        simulation: str,
        request_id: str,
    ) -> ExecutionResult:
        events: list[TraceEvent] = []
        start_time = time.monotonic()

        for attempt in range(1, self._settings.max_attempts + 1):
            events.append(TraceEvent(event="attempt_started", attempt=attempt))

            logger.info(
                "Execution attempt",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "agent": agent_name,
                        "attempt": attempt,
                    }
                },
            )

            try:
                raw_result = await asyncio.wait_for(
                    adapter.invoke(agent_name, tool_name, tenant_id, simulation, attempt),
                    timeout=self._settings.timeout_ms / 1000,
                )

                validated = validate_tool_result(capability, raw_result)

                events.append(TraceEvent(event="attempt_succeeded", attempt=attempt))
                duration_ms = (time.monotonic() - start_time) * 1000

                return ExecutionResult(
                    status="completed",
                    result=validated,
                    attempts=attempt,
                    duration_ms=duration_ms,
                    events=events,
                )

            except asyncio.TimeoutError:
                events.append(
                    TraceEvent(event="attempt_failed", attempt=attempt, code="TIMEOUT")
                )
                duration_ms = (time.monotonic() - start_time) * 1000
                return ExecutionResult(
                    status="failed",
                    error_code="UPSTREAM_TIMEOUT",
                    error_message="The tool did not respond in time.",
                    attempts=attempt,
                    duration_ms=duration_ms,
                    events=events,
                )

            except TransientError:
                events.append(
                    TraceEvent(event="attempt_failed", attempt=attempt, code="TRANSIENT")
                )

                if attempt >= self._settings.max_attempts:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    return ExecutionResult(
                        status="failed",
                        error_code="UPSTREAM_UNAVAILABLE",
                        error_message="The upstream service is temporarily unavailable.",
                        attempts=attempt,
                        duration_ms=duration_ms,
                        events=events,
                    )

                delay_ms = self._settings.backoff_delays_ms[attempt - 1]
                events.append(
                    TraceEvent(event="retry_scheduled", attempt=attempt, delay_ms=delay_ms)
                )

                logger.info(
                    "Retry scheduled",
                    extra={
                        "extra_fields": {
                            "request_id": request_id,
                            "agent": agent_name,
                            "attempt": attempt,
                            "delay_ms": delay_ms,
                        }
                    },
                )

                await self._sleep_fn(delay_ms / 1000)

            except PermanentError:
                events.append(
                    TraceEvent(event="attempt_failed", attempt=attempt, code="PERMANENT")
                )
                duration_ms = (time.monotonic() - start_time) * 1000
                return ExecutionResult(
                    status="failed",
                    error_code="UPSTREAM_PERMANENT",
                    error_message="The upstream service returned a permanent error.",
                    attempts=attempt,
                    duration_ms=duration_ms,
                    events=events,
                )

            except InvalidToolResultError:
                events.append(
                    TraceEvent(event="attempt_failed", attempt=attempt, code="INVALID_RESULT")
                )
                duration_ms = (time.monotonic() - start_time) * 1000
                return ExecutionResult(
                    status="failed",
                    error_code="INVALID_TOOL_RESULT",
                    error_message="The tool returned an invalid result.",
                    attempts=attempt,
                    duration_ms=duration_ms,
                    events=events,
                )

        duration_ms = (time.monotonic() - start_time) * 1000
        return ExecutionResult(
            status="failed",
            error_code="UPSTREAM_UNAVAILABLE",
            error_message="The upstream service is temporarily unavailable.",
            attempts=self._settings.max_attempts,
            duration_ms=duration_ms,
            events=events,
        )
