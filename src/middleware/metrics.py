"""Optimized metrics collection middleware for API requests."""

# Standard library imports
import time
from typing import Callable

# Third-party imports
import structlog
from fastapi import Request

from ..config import settings

# Local application imports
from ..services.metrics import APIMetrics, metrics_collector

logger = structlog.get_logger(__name__)


class MetricsMiddleware:
    """Pure ASGI middleware to collect essential API request metrics.

    Replaces the previous BaseHTTPMiddleware implementation to avoid
    its background task + memory stream mechanism that can silently fail
    for long-running requests, preventing the response from being fully
    written to the socket.
    """

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        """Process request and collect essential metrics."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        start_time = time.time()
        response_status = None
        response_body_sent = False
        client_disconnected = False

        # Monitor for client disconnect during processing
        async def receive_wrapper():
            nonlocal client_disconnected
            message = await receive()
            if message.get("type") == "http.disconnect":
                client_disconnected = True
                logger.warning(
                    "Client disconnected during request processing",
                    method=request.method,
                    path=request.url.path,
                    elapsed_ms=round((time.time() - start_time) * 1000, 2),
                )
            return message

        async def send_wrapper(message):
            nonlocal response_status, response_body_sent
            if message["type"] == "http.response.start":
                response_status = message["status"]

                # Add debug timing header (append to preserve duplicate headers like Set-Cookie)
                if settings.api_debug:
                    response_time_ms = (time.time() - start_time) * 1000
                    headers = list(message.get("headers", []))
                    headers.append((b"x-response-time-ms", str(round(response_time_ms, 2)).encode()))
                    message["headers"] = headers

            elif message["type"] == "http.response.body":
                more_body = message.get("more_body", False)
                if not more_body:
                    response_body_sent = True

            try:
                await send(message)
            except Exception as e:
                logger.error(
                    "Failed to send response to client",
                    method=request.method,
                    path=request.url.path,
                    message_type=message.get("type"),
                    elapsed_ms=round((time.time() - start_time) * 1000, 2),
                    error=str(e),
                )
                raise

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            # Log diagnostic info for requests where the response body
            # was not confirmed sent (indicates socket hang-up scenario)
            if not response_body_sent and response_status is not None:
                logger.warning(
                    "Response headers sent but body not confirmed",
                    method=request.method,
                    path=request.url.path,
                    status=response_status,
                    client_disconnected=client_disconnected,
                    elapsed_ms=round((time.time() - start_time) * 1000, 2),
                )
            response_time_ms = (time.time() - start_time) * 1000
            normalized_endpoint = self._normalize_endpoint(request.url.path)

            api_metrics = APIMetrics(
                endpoint=normalized_endpoint,
                method=request.method,
                status_code=response_status if response_status is not None else 500,
                response_time_ms=response_time_ms,
                request_size_bytes=0,
                response_size_bytes=0,
                user_agent=None,
            )

            try:
                metrics_collector.record_api_metrics(api_metrics)
            except Exception as e:
                logger.error("Failed to record API metrics", error=str(e))

    def _normalize_endpoint(self, path: str) -> str:
        """Simplified endpoint path normalization."""
        # Remove query parameters
        if "?" in path:
            path = path.split("?")[0]

        # Simple ID replacement for common patterns
        path_parts = path.split("/")
        for i, part in enumerate(path_parts):
            # Replace UUIDs and long IDs with placeholder
            if len(part) >= 16 and any(c.isalnum() or c in "-_" for c in part):
                if i > 0 and path_parts[i - 1] in [
                    "sessions",
                    "files",
                    "executions",
                    "download",
                ]:
                    path_parts[i] = "{id}"

        return "/".join(path_parts)
