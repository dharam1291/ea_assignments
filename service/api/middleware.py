"""
HTTP middleware pipeline.

Middleware runs outside the FastAPI dependency graph and therefore applies
uniformly to every request — including those that fail authentication.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


async def _request_context_middleware(request: Request, call_next):
    request_id = f"req-{uuid.uuid4()}"
    request.state.request_id = request_id
    start = time.monotonic()

    response = await call_next(request)

    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Request completed",
        extra={
            "extra_fields": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            }
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


def register_middleware(app: FastAPI) -> None:
    app.middleware("http")(_request_context_middleware)
