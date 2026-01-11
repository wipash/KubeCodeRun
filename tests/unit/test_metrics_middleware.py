"""Unit tests for Metrics Middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.middleware.metrics import MetricsMiddleware


@pytest.fixture
def mock_request():
    """Create a mock request."""
    request = MagicMock()
    request.url.path = "/api/v1/exec"
    request.method = "POST"
    return request


@pytest.fixture
def mock_response():
    """Create a mock response."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    return response


@pytest.fixture
def mock_app():
    """Create a mock app."""
    return MagicMock()


@pytest.fixture
def metrics_middleware(mock_app):
    """Create a metrics middleware instance."""
    return MetricsMiddleware(mock_app)


class TestMetricsMiddlewareDispatch:
    """Tests for MetricsMiddleware dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_records_metrics(self, metrics_middleware, mock_request, mock_response):
        """Test that dispatch records metrics."""
        call_next = AsyncMock(return_value=mock_response)

        with patch("src.middleware.metrics.metrics_collector") as mock_collector:
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = False

                result = await metrics_middleware.dispatch(mock_request, call_next)

        assert result == mock_response
        mock_collector.record_api_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_adds_debug_header(self, metrics_middleware, mock_request, mock_response):
        """Test that debug header is added in debug mode."""
        call_next = AsyncMock(return_value=mock_response)

        with patch("src.middleware.metrics.metrics_collector"):
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = True

                result = await metrics_middleware.dispatch(mock_request, call_next)

        assert "X-Response-Time-Ms" in result.headers

    @pytest.mark.asyncio
    async def test_dispatch_handles_metric_error(self, metrics_middleware, mock_request, mock_response):
        """Test that dispatch handles metrics recording errors gracefully."""
        call_next = AsyncMock(return_value=mock_response)

        with patch("src.middleware.metrics.metrics_collector") as mock_collector:
            mock_collector.record_api_metrics.side_effect = Exception("Metrics error")
            with patch("src.middleware.metrics.settings") as mock_settings:
                mock_settings.api_debug = False

                # Should not raise, just log error
                result = await metrics_middleware.dispatch(mock_request, call_next)

        assert result == mock_response


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
