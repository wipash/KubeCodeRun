"""Unit tests for Health API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.health import (
    basic_health_check,
    detailed_health_check,
    get_api_metrics,
    get_execution_metrics,
    get_metrics,
    get_service_status,
    kubernetes_health_check,
    minio_health_check,
    redis_health_check,
)
from src.services.health import HealthCheckResult, HealthStatus


@pytest.fixture
def mock_health_result():
    """Create a mock health result."""
    return HealthCheckResult(
        service="test",
        status=HealthStatus.HEALTHY,
        response_time_ms=10.5,
        details={"test": "value"},
    )


@pytest.fixture
def mock_unhealthy_result():
    """Create a mock unhealthy result."""
    return HealthCheckResult(
        service="test",
        status=HealthStatus.UNHEALTHY,
        response_time_ms=5000.0,
        error="Connection failed",
    )


class TestBasicHealthCheck:
    """Tests for basic_health_check endpoint."""

    @pytest.mark.asyncio
    async def test_returns_healthy(self):
        """Test basic health check returns healthy."""
        result = await basic_health_check()

        assert result["status"] == "healthy"
        assert "version" in result
        assert "service" in result


class TestDetailedHealthCheck:
    """Tests for detailed_health_check endpoint."""

    @pytest.mark.asyncio
    async def test_all_healthy(self, mock_health_result):
        """Test detailed check when all services healthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(
                return_value={"redis": mock_health_result, "minio": mock_health_result}
            )
            mock_health.get_overall_status.return_value = HealthStatus.HEALTHY

            response = await detailed_health_check(use_cache=True, _="api-key")

            assert response.status_code == 200
            body = response.body.decode()
            assert "healthy" in body

    @pytest.mark.asyncio
    async def test_degraded_status(self, mock_health_result):
        """Test detailed check with degraded status."""
        degraded_result = HealthCheckResult(
            service="redis",
            status=HealthStatus.DEGRADED,
            response_time_ms=500.0,
        )

        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(return_value={"redis": degraded_result})
            mock_health.get_overall_status.return_value = HealthStatus.DEGRADED

            response = await detailed_health_check(use_cache=True, _="api-key")

            assert response.status_code == 200
            assert "X-Health-Status" in response.headers

    @pytest.mark.asyncio
    async def test_unhealthy_status(self, mock_unhealthy_result):
        """Test detailed check with unhealthy status."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(return_value={"redis": mock_unhealthy_result})
            mock_health.get_overall_status.return_value = HealthStatus.UNHEALTHY

            response = await detailed_health_check(use_cache=True, _="api-key")

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_exception_returns_503(self):
        """Test that exceptions return 503."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(side_effect=Exception("Test error"))

            with patch("src.api.health.settings") as mock_settings:
                mock_settings.api_debug = True

                response = await detailed_health_check(use_cache=True, _="api-key")

                assert response.status_code == 503


class TestRedisHealthCheck:
    """Tests for redis_health_check endpoint."""

    @pytest.mark.asyncio
    async def test_healthy(self, mock_health_result):
        """Test Redis health check when healthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_redis = AsyncMock(return_value=mock_health_result)

            response = await redis_health_check(_="api-key")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unhealthy(self, mock_unhealthy_result):
        """Test Redis health check when unhealthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_redis = AsyncMock(return_value=mock_unhealthy_result)

            response = await redis_health_check(_="api-key")

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test Redis health check exception handling."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_redis = AsyncMock(side_effect=Exception("Redis error"))

            with patch("src.api.health.settings") as mock_settings:
                mock_settings.api_debug = False

                response = await redis_health_check(_="api-key")

                assert response.status_code == 503


class TestMinioHealthCheck:
    """Tests for minio_health_check endpoint."""

    @pytest.mark.asyncio
    async def test_healthy(self, mock_health_result):
        """Test MinIO health check when healthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_minio = AsyncMock(return_value=mock_health_result)

            response = await minio_health_check(_="api-key")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unhealthy(self, mock_unhealthy_result):
        """Test MinIO health check when unhealthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_minio = AsyncMock(return_value=mock_unhealthy_result)

            response = await minio_health_check(_="api-key")

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test MinIO health check exception handling."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_minio = AsyncMock(side_effect=Exception("MinIO error"))

            with patch("src.api.health.settings") as mock_settings:
                mock_settings.api_debug = True

                response = await minio_health_check(_="api-key")

                assert response.status_code == 503


class TestKubernetesHealthCheck:
    """Tests for kubernetes_health_check endpoint."""

    @pytest.mark.asyncio
    async def test_healthy(self, mock_health_result):
        """Test Kubernetes health check when healthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_kubernetes = AsyncMock(return_value=mock_health_result)

            response = await kubernetes_health_check(_="api-key")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unhealthy(self, mock_unhealthy_result):
        """Test Kubernetes health check when unhealthy."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_kubernetes = AsyncMock(return_value=mock_unhealthy_result)

            response = await kubernetes_health_check(_="api-key")

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test Kubernetes health check exception handling."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_kubernetes = AsyncMock(side_effect=Exception("K8s error"))

            with patch("src.api.health.settings") as mock_settings:
                mock_settings.api_debug = False

                response = await kubernetes_health_check(_="api-key")

                assert response.status_code == 503


class TestGetMetrics:
    """Tests for get_metrics endpoint."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful metrics retrieval."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_execution_statistics.return_value = {"executions": 100}
            mock_metrics.get_api_statistics.return_value = {"requests": 500}
            mock_metrics.get_system_metrics.return_value = {"uptime": 3600}

            result = await get_metrics(_="api-key")

            assert "execution_statistics" in result
            assert "api_statistics" in result
            assert "system_metrics" in result

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test metrics retrieval exception."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_execution_statistics.side_effect = Exception("Metrics error")

            with pytest.raises(HTTPException) as exc_info:
                await get_metrics(_="api-key")

            assert exc_info.value.status_code == 500


class TestGetExecutionMetrics:
    """Tests for get_execution_metrics endpoint."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful execution metrics retrieval."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_execution_statistics.return_value = {"executions": 100}

            result = await get_execution_metrics(_="api-key")

            assert result == {"executions": 100}

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test execution metrics exception."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_execution_statistics.side_effect = Exception("Error")

            with pytest.raises(HTTPException) as exc_info:
                await get_execution_metrics(_="api-key")

            assert exc_info.value.status_code == 500


class TestGetApiMetrics:
    """Tests for get_api_metrics endpoint."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful API metrics retrieval."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_api_statistics.return_value = {"requests": 500}

            result = await get_api_metrics(_="api-key")

            assert result == {"requests": 500}

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test API metrics exception."""
        with patch("src.api.health.metrics_collector") as mock_metrics:
            mock_metrics.get_api_statistics.side_effect = Exception("Error")

            with pytest.raises(HTTPException) as exc_info:
                await get_api_metrics(_="api-key")

            assert exc_info.value.status_code == 500


class TestGetServiceStatus:
    """Tests for get_service_status endpoint."""

    @pytest.mark.asyncio
    async def test_success(self, mock_health_result):
        """Test successful service status retrieval."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(return_value={"redis": mock_health_result})
            mock_health.get_overall_status.return_value = HealthStatus.HEALTHY

            with patch("src.api.health.metrics_collector") as mock_metrics:
                mock_metrics.get_system_metrics.return_value = {
                    "counters": {"executions_total": 100, "api_requests_total": 500},
                    "buffer_size": 10,
                    "uptime_seconds": 3600,
                }

                with patch("src.api.health.settings") as mock_settings:
                    mock_settings.api_debug = False
                    mock_settings.max_execution_time = 30
                    mock_settings.max_memory_mb = 512
                    mock_settings.session_ttl_hours = 2
                    mock_settings.supported_languages = {"python": {}, "javascript": {}}

                    result = await get_service_status(_="api-key")

                    assert "overall_status" in result
                    assert "services" in result
                    assert "metrics" in result
                    assert "configuration" in result

    @pytest.mark.asyncio
    async def test_exception(self):
        """Test service status exception."""
        with patch("src.api.health.health_service") as mock_health:
            mock_health.check_all_services = AsyncMock(side_effect=Exception("Error"))

            with pytest.raises(HTTPException) as exc_info:
                await get_service_status(_="api-key")

            assert exc_info.value.status_code == 500
