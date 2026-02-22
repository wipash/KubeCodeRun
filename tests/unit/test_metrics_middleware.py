"""Unit tests for Metrics Middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.middleware.metrics import MetricsMiddleware


def _make_scope(path="/api/v1/exec", method="POST"):
    """Create a minimal ASGI HTTP scope."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
    }


def _make_asgi_app(status=200):
    """Create a mock ASGI app that sends a response with the given status."""

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    return app


@pytest.fixture
def mock_app():
    """Create a mock ASGI app."""
    return _make_asgi_app(200)


@pytest.fixture
def metrics_middleware(mock_app):
    """Create a metrics middleware instance."""
    return MetricsMiddleware(mock_app)


class TestMetricsMiddlewareDispatch:
    """Tests for MetricsMiddleware __call__ method."""

    @pytest.mark.asyncio
    async def test_records_metrics(self):
        """Test that __call__ records metrics."""
        inner_app = _make_asgi_app(200)
        middleware = MetricsMiddleware(inner_app)
        send = AsyncMock()

        with patch("src.middleware.metrics.metrics_collector") as mock_collector:
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = False
                await middleware(_make_scope(), AsyncMock(), send)

        mock_collector.record_api_metrics.assert_called_once()
        metrics = mock_collector.record_api_metrics.call_args[0][0]
        assert metrics.status_code == 200
        assert metrics.method == "POST"
        assert metrics.endpoint == "/api/v1/exec"

    @pytest.mark.asyncio
    async def test_adds_debug_header(self):
        """Test that debug header is added in debug mode."""
        inner_app = _make_asgi_app(200)
        middleware = MetricsMiddleware(inner_app)
        sent_messages = []

        async def capture_send(message):
            sent_messages.append(message)

        with patch("src.middleware.metrics.metrics_collector"):
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = True
                await middleware(_make_scope(), AsyncMock(), capture_send)

        start_msg = sent_messages[0]
        header_names = [name for name, _ in start_msg["headers"]]
        assert b"x-response-time-ms" in header_names
        # Verify original headers are preserved (not dropped by dict round-trip)
        assert b"content-type" in header_names

    @pytest.mark.asyncio
    async def test_handles_metric_error(self):
        """Test that __call__ handles metrics recording errors gracefully."""
        inner_app = _make_asgi_app(200)
        middleware = MetricsMiddleware(inner_app)
        send = AsyncMock()

        with patch("src.middleware.metrics.metrics_collector") as mock_collector:
            mock_collector.record_api_metrics.side_effect = Exception("Metrics error")
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = False

                # Should not raise, just log error
                await middleware(_make_scope(), AsyncMock(), send)

        # Verify the response was still sent to the client
        assert send.called

    @pytest.mark.asyncio
    async def test_passthrough_non_http(self):
        """Test that non-HTTP scopes are passed through."""
        inner_app = AsyncMock()
        middleware = MetricsMiddleware(inner_app)

        scope = {"type": "lifespan"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        inner_app.assert_called_once_with(scope, receive, send)


class TestNormalizeEndpoint:
    """Tests for _normalize_endpoint method."""

    def test_normalize_removes_query_params(self, metrics_middleware):
        """Test that query parameters are removed."""
        result = metrics_middleware._normalize_endpoint("/api/v1/exec?foo=bar")

        assert "?" not in result
        assert result == "/api/v1/exec"

    def test_normalize_replaces_session_id(self, metrics_middleware):
        """Test that session IDs are replaced with placeholder."""
        result = metrics_middleware._normalize_endpoint("/api/v1/sessions/abcdef1234567890")

        assert "{id}" in result

    def test_normalize_replaces_file_id(self, metrics_middleware):
        """Test that file IDs are replaced with placeholder."""
        result = metrics_middleware._normalize_endpoint("/api/v1/files/abcdef1234567890")

        assert "{id}" in result

    def test_normalize_replaces_execution_id(self, metrics_middleware):
        """Test that execution IDs are replaced with placeholder."""
        result = metrics_middleware._normalize_endpoint("/api/v1/executions/abcdef1234567890")

        assert "{id}" in result

    def test_normalize_replaces_download_id(self, metrics_middleware):
        """Test that download IDs are replaced with placeholder."""
        result = metrics_middleware._normalize_endpoint("/api/v1/download/abcdef1234567890")

        assert "{id}" in result

    def test_normalize_keeps_short_segments(self, metrics_middleware):
        """Test that short path segments are not replaced."""
        result = metrics_middleware._normalize_endpoint("/api/v1/exec")

        assert result == "/api/v1/exec"

    def test_normalize_handles_root_path(self, metrics_middleware):
        """Test that root path is handled."""
        result = metrics_middleware._normalize_endpoint("/")

        assert result == "/"

    def test_normalize_handles_health_path(self, metrics_middleware):
        """Test that health path is not modified."""
        result = metrics_middleware._normalize_endpoint("/health")

        assert result == "/health"
