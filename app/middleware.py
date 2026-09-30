from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_HEADER = "x-request-id"
# Chỉ tin header từ client khi nó ngắn và an toàn để ghi log (chống log injection).
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(header_value: str | None) -> str:
    if header_value and SAFE_REQUEST_ID.match(header_value):
        return header_value
    return new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Xóa context của request trước để metadata không rò sang request mới.
        clear_contextvars()

        correlation_id = resolve_correlation_id(request.headers.get(REQUEST_ID_HEADER))
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers[REQUEST_ID_HEADER] = correlation_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
        return response
