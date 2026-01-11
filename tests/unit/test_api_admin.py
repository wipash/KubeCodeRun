"""Unit tests for Admin API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.admin import (
    ApiKeyCreate,
    ApiKeyUpdate,
    RateLimitsUpdate,
    create_key,
    get_admin_stats,
    list_keys,
    revoke_key,
    update_key,
    verify_master_key,
)
from src.models.api_key import ApiKeyRecord, RateLimits


@pytest.fixture
def mock_api_key_record():
    """Create a mock API key record."""
    return ApiKeyRecord(
        key_hash="abc123hash",
        key_prefix="test-key...",
        name="Test Key",
        created_at=datetime.now(UTC),
        enabled=True,
        rate_limits=RateLimits(),
        metadata={"env": "test"},
        last_used_at=None,
        usage_count=0,
        source="managed",
    )


@pytest.fixture
def mock_env_key_record():
    """Create a mock environment API key record."""
    return ApiKeyRecord(
        key_hash="envkeyhash",
        key_prefix="env-key...",
        name="Environment Key",
        created_at=datetime.now(UTC),
        enabled=True,
        rate_limits=RateLimits(),
        metadata={},
        last_used_at=None,
        usage_count=0,
        source="environment",
    )


class TestVerifyMasterKey:
    """Tests for verify_master_key dependency."""

    @pytest.mark.asyncio
    async def test_verify_master_key_success(self):
        """Test successful master key verification."""
        with patch("src.api.admin.settings") as mock_settings:
            mock_settings.master_api_key = "test-master-key"

            result = await verify_master_key("test-master-key")

            assert result == "test-master-key"

    @pytest.mark.asyncio
    async def test_verify_master_key_invalid(self):
        """Test invalid master key raises 403."""
        with patch("src.api.admin.settings") as mock_settings:
            mock_settings.master_api_key = "test-master-key"

            with pytest.raises(HTTPException) as exc_info:
                await verify_master_key("wrong-key")

            assert exc_info.value.status_code == 403
            assert "Invalid" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_master_key_not_configured(self):
        """Test missing master key raises 500."""
        with patch("src.api.admin.settings") as mock_settings:
            mock_settings.master_api_key = None

            with pytest.raises(HTTPException) as exc_info:
                await verify_master_key("any-key")

            assert exc_info.value.status_code == 500
            assert "disabled" in exc_info.value.detail


class TestListKeys:
    """Tests for list_keys endpoint."""

    @pytest.mark.asyncio
    async def test_list_keys_success(self, mock_api_key_record):
        """Test successful key listing."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.list_keys = AsyncMock(return_value=[mock_api_key_record])
            mock_get_manager.return_value = mock_manager

            result = await list_keys("master-key")

            assert len(result) == 1
            assert result[0].key_hash == "abc123hash"
            assert result[0].name == "Test Key"
            mock_manager.list_keys.assert_called_once_with(include_env_keys=True)

    @pytest.mark.asyncio
    async def test_list_keys_empty(self):
        """Test listing when no keys exist."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.list_keys = AsyncMock(return_value=[])
            mock_get_manager.return_value = mock_manager

            result = await list_keys("master-key")

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_keys_includes_env_keys(self, mock_api_key_record, mock_env_key_record):
        """Test that environment keys are included."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.list_keys = AsyncMock(return_value=[mock_api_key_record, mock_env_key_record])
            mock_get_manager.return_value = mock_manager

            result = await list_keys("master-key")

            assert len(result) == 2
            sources = [r.source for r in result]
            assert "managed" in sources
            assert "environment" in sources


class TestCreateKey:
    """Tests for create_key endpoint."""

    @pytest.mark.asyncio
    async def test_create_key_success(self, mock_api_key_record):
        """Test successful key creation."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.create_key = AsyncMock(return_value=("full-api-key", mock_api_key_record))
            mock_get_manager.return_value = mock_manager

            data = ApiKeyCreate(name="New Key")
            result = await create_key(data, "master-key")

            assert result["api_key"] == "full-api-key"
            assert result["record"].name == "Test Key"
            mock_manager.create_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_key_with_rate_limits(self, mock_api_key_record):
        """Test key creation with rate limits."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.create_key = AsyncMock(return_value=("full-api-key", mock_api_key_record))
            mock_get_manager.return_value = mock_manager

            data = ApiKeyCreate(
                name="New Key",
                rate_limits=RateLimitsUpdate(per_minute=100, hourly=1000),
            )
            result = await create_key(data, "master-key")

            assert result["api_key"] == "full-api-key"
            # Verify rate_limits was passed
            call_args = mock_manager.create_key.call_args
            assert call_args.kwargs["rate_limits"] is not None

    @pytest.mark.asyncio
    async def test_create_key_with_metadata(self, mock_api_key_record):
        """Test key creation with metadata."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.create_key = AsyncMock(return_value=("full-api-key", mock_api_key_record))
            mock_get_manager.return_value = mock_manager

            data = ApiKeyCreate(name="New Key", metadata={"env": "production"})
            result = await create_key(data, "master-key")

            assert result["api_key"] == "full-api-key"
            call_args = mock_manager.create_key.call_args
            assert call_args.kwargs["metadata"] == {"env": "production"}


class TestUpdateKey:
    """Tests for update_key endpoint."""

    @pytest.mark.asyncio
    async def test_update_key_success(self, mock_api_key_record):
        """Test successful key update."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_api_key_record)
            mock_manager.update_key = AsyncMock(return_value=True)
            mock_get_manager.return_value = mock_manager

            data = ApiKeyUpdate(enabled=False)
            result = await update_key("abc123hash", data, "master-key")

            assert result is True
            mock_manager.update_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_key_not_found(self, mock_api_key_record):
        """Test updating non-existent key raises 404."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_api_key_record)
            mock_manager.update_key = AsyncMock(return_value=False)
            mock_get_manager.return_value = mock_manager

            data = ApiKeyUpdate(enabled=False)

            with pytest.raises(HTTPException) as exc_info:
                await update_key("nonexistent", data, "master-key")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_env_key_forbidden(self, mock_env_key_record):
        """Test updating environment key raises 403."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_env_key_record)
            mock_get_manager.return_value = mock_manager

            data = ApiKeyUpdate(enabled=False)

            with pytest.raises(HTTPException) as exc_info:
                await update_key("envkeyhash", data, "master-key")

            assert exc_info.value.status_code == 403
            assert "Environment keys cannot be modified" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_key_with_rate_limits(self, mock_api_key_record):
        """Test updating key with new rate limits."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_api_key_record)
            mock_manager.update_key = AsyncMock(return_value=True)
            mock_get_manager.return_value = mock_manager

            data = ApiKeyUpdate(rate_limits=RateLimitsUpdate(per_minute=200))
            result = await update_key("abc123hash", data, "master-key")

            assert result is True
            call_args = mock_manager.update_key.call_args
            assert call_args.kwargs["rate_limits"] is not None


class TestRevokeKey:
    """Tests for revoke_key endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_key_success(self, mock_api_key_record):
        """Test successful key revocation."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_api_key_record)
            mock_manager.revoke_key = AsyncMock(return_value=True)
            mock_get_manager.return_value = mock_manager

            result = await revoke_key("abc123hash", "master-key")

            assert result is True
            mock_manager.revoke_key.assert_called_once_with("abc123hash")

    @pytest.mark.asyncio
    async def test_revoke_key_not_found(self, mock_api_key_record):
        """Test revoking non-existent key raises 404."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_api_key_record)
            mock_manager.revoke_key = AsyncMock(return_value=False)
            mock_get_manager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await revoke_key("nonexistent", "master-key")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_env_key_forbidden(self, mock_env_key_record):
        """Test revoking environment key raises 403."""
        with patch("src.api.admin.get_api_key_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_key = AsyncMock(return_value=mock_env_key_record)
            mock_get_manager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await revoke_key("envkeyhash", "master-key")

            assert exc_info.value.status_code == 403
            assert "Environment keys cannot be revoked" in exc_info.value.detail


class TestGetAdminStats:
    """Tests for get_admin_stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_admin_stats_success(self):
        """Test successful stats retrieval."""
        with patch("src.api.admin.get_detailed_metrics_service") as mock_get_metrics:
            with patch("src.api.admin.health_service") as mock_health:
                # Mock metrics service
                mock_metrics = MagicMock()
                mock_summary = MagicMock()
                mock_summary.to_dict.return_value = {"total": 100}
                mock_metrics.get_summary = AsyncMock(return_value=mock_summary)
                mock_metrics.get_language_stats = AsyncMock(return_value={})
                mock_pool_stats = MagicMock()
                mock_pool_stats.to_dict.return_value = {"active": 5}
                mock_metrics.get_pool_stats = AsyncMock(return_value=mock_pool_stats)
                mock_get_metrics.return_value = mock_metrics

                # Mock health service
                mock_health.check_all_services = AsyncMock(return_value={})
                mock_status = MagicMock()
                mock_status.value = "healthy"
                mock_health.get_overall_status.return_value = mock_status

                result = await get_admin_stats(hours=24, _="master-key")

                assert "summary" in result
                assert "pool_stats" in result
                assert "health" in result
                assert "timestamp" in result
                assert result["period_hours"] == 24

    @pytest.mark.asyncio
    async def test_get_admin_stats_with_language_stats(self):
        """Test stats with language breakdown."""
        with patch("src.api.admin.get_detailed_metrics_service") as mock_get_metrics:
            with patch("src.api.admin.health_service") as mock_health:
                mock_metrics = MagicMock()
                mock_summary = MagicMock()
                mock_summary.to_dict.return_value = {}
                mock_metrics.get_summary = AsyncMock(return_value=mock_summary)

                # Mock language stats
                mock_py_stats = MagicMock()
                mock_py_stats.to_dict.return_value = {"executions": 50}
                mock_js_stats = MagicMock()
                mock_js_stats.to_dict.return_value = {"executions": 30}
                mock_metrics.get_language_stats = AsyncMock(
                    return_value={"python": mock_py_stats, "javascript": mock_js_stats}
                )

                mock_pool_stats = MagicMock()
                mock_pool_stats.to_dict.return_value = {}
                mock_metrics.get_pool_stats = AsyncMock(return_value=mock_pool_stats)
                mock_get_metrics.return_value = mock_metrics

                mock_health.check_all_services = AsyncMock(return_value={})
                mock_status = MagicMock()
                mock_status.value = "healthy"
                mock_health.get_overall_status.return_value = mock_status

                result = await get_admin_stats(hours=48, _="master-key")

                assert "by_language" in result
                assert "python" in result["by_language"]
                assert "javascript" in result["by_language"]
                assert result["period_hours"] == 48


class TestModels:
    """Tests for admin API models."""

    def test_rate_limits_update_all_none(self):
        """Test RateLimitsUpdate with default values."""
        update = RateLimitsUpdate()
        assert update.per_second is None
        assert update.per_minute is None
        assert update.hourly is None
        assert update.daily is None
        assert update.monthly is None

    def test_rate_limits_update_partial(self):
        """Test RateLimitsUpdate with partial values."""
        update = RateLimitsUpdate(per_minute=100, daily=10000)
        assert update.per_minute == 100
        assert update.daily == 10000
        assert update.hourly is None

    def test_api_key_create_minimal(self):
        """Test ApiKeyCreate with minimal fields."""
        create = ApiKeyCreate(name="Test Key")
        assert create.name == "Test Key"
        assert create.rate_limits is None
        assert create.metadata is None

    def test_api_key_update_partial(self):
        """Test ApiKeyUpdate with partial fields."""
        update = ApiKeyUpdate(enabled=False)
        assert update.enabled is False
        assert update.name is None
        assert update.rate_limits is None
