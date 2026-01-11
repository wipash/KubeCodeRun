"""Unit tests for Dashboard Metrics API."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


class TestVerifyMasterKey:
    """Tests for verify_master_key dependency."""

    @pytest.mark.asyncio
    async def test_verify_master_key_success(self):
        """Test successful master key verification."""
        from src.api.dashboard_metrics import verify_master_key

        with patch("src.api.dashboard_metrics.settings") as mock_settings:
            mock_settings.master_api_key = "test-master-key"

            result = await verify_master_key(x_api_key="test-master-key")

            assert result == "test-master-key"

    @pytest.mark.asyncio
    async def test_verify_master_key_no_master_key_configured(self):
        """Test when no master key is configured."""
        from src.api.dashboard_metrics import verify_master_key

        with patch("src.api.dashboard_metrics.settings") as mock_settings:
            mock_settings.master_api_key = None

            with pytest.raises(HTTPException) as exc_info:
                await verify_master_key(x_api_key="any-key")

            assert exc_info.value.status_code == 500
            assert "Admin operations are disabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_master_key_invalid_key(self):
        """Test with invalid master key."""
        from src.api.dashboard_metrics import verify_master_key

        with patch("src.api.dashboard_metrics.settings") as mock_settings:
            mock_settings.master_api_key = "correct-key"

            with pytest.raises(HTTPException) as exc_info:
                await verify_master_key(x_api_key="wrong-key")

            assert exc_info.value.status_code == 403
            assert "Invalid Master API Key" in exc_info.value.detail


class TestGetDateRange:
    """Tests for get_date_range function."""

    def test_get_date_range_with_start_date(self):
        """Test get_date_range with custom start_date."""
        from src.api.dashboard_metrics import get_date_range

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 15, tzinfo=UTC)

        result_start, result_end = get_date_range("day", start_date=start, end_date=end)

        assert result_start == start
        assert result_end == end

    def test_get_date_range_hour_period(self):
        """Test get_date_range with hour period."""
        from src.api.dashboard_metrics import get_date_range

        start, end = get_date_range("hour")

        assert (end - start) == timedelta(hours=1)

    def test_get_date_range_day_period(self):
        """Test get_date_range with day period."""
        from src.api.dashboard_metrics import get_date_range

        start, end = get_date_range("day")

        assert (end - start) == timedelta(days=1)

    def test_get_date_range_week_period(self):
        """Test get_date_range with week period."""
        from src.api.dashboard_metrics import get_date_range

        start, end = get_date_range("week")

        assert (end - start) == timedelta(weeks=1)

    def test_get_date_range_month_period(self):
        """Test get_date_range with month period."""
        from src.api.dashboard_metrics import get_date_range

        start, end = get_date_range("month")

        assert (end - start) == timedelta(days=30)

    def test_get_date_range_unknown_period(self):
        """Test get_date_range with unknown period defaults to day."""
        from src.api.dashboard_metrics import get_date_range

        start, end = get_date_range("unknown")

        assert (end - start) == timedelta(days=1)


class TestGetGranularity:
    """Tests for get_granularity function."""

    def test_get_granularity_hour(self):
        """Test granularity for hour period."""
        from src.api.dashboard_metrics import get_granularity

        assert get_granularity("hour") == "hour"

    def test_get_granularity_day(self):
        """Test granularity for day period."""
        from src.api.dashboard_metrics import get_granularity

        assert get_granularity("day") == "hour"

    def test_get_granularity_week(self):
        """Test granularity for week period."""
        from src.api.dashboard_metrics import get_granularity

        assert get_granularity("week") == "day"

    def test_get_granularity_month(self):
        """Test granularity for month period."""
        from src.api.dashboard_metrics import get_granularity

        assert get_granularity("month") == "day"


class TestGetMetricsSummaryEndpoint:
    """Tests for get_metrics_summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_metrics_summary_success(self):
        """Test successful summary retrieval."""
        from src.api.dashboard_metrics import get_metrics_summary

        mock_stats = {
            "total_executions": 100,
            "success_count": 90,
            "failure_count": 8,
            "timeout_count": 2,
            "success_rate": 90.0,
            "avg_execution_time_ms": 150.5,
            "pool_hit_rate": 85.0,
            "active_api_keys": 5,
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_summary_stats = AsyncMock(return_value=mock_stats)

            result = await get_metrics_summary(period="day")

        assert result.total_executions == 100
        assert result.success_count == 90
        assert result.success_rate == 90.0
        assert result.period == "day"

    @pytest.mark.asyncio
    async def test_get_metrics_summary_with_api_key_filter(self):
        """Test summary with API key filter."""
        from src.api.dashboard_metrics import get_metrics_summary

        mock_stats = {
            "total_executions": 50,
            "success_count": 45,
            "failure_count": 5,
            "timeout_count": 0,
            "success_rate": 90.0,
            "avg_execution_time_ms": 100.0,
            "pool_hit_rate": 80.0,
            "active_api_keys": 1,
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_summary_stats = AsyncMock(return_value=mock_stats)

            result = await get_metrics_summary(period="week", api_key_hash="abc123")

        mock_service.get_summary_stats.assert_called_once()
        call_kwargs = mock_service.get_summary_stats.call_args.kwargs
        assert call_kwargs["api_key_hash"] == "abc123"


class TestGetLanguageMetricsEndpoint:
    """Tests for get_language_metrics endpoint."""

    @pytest.mark.asyncio
    async def test_get_language_metrics_success(self):
        """Test successful language metrics retrieval."""
        from src.api.dashboard_metrics import get_language_metrics

        mock_data = {
            "by_language": {"python": 50, "javascript": 30},
            "by_api_key": {"key1": 40, "key2": 40},
            "matrix": {"python": {"key1": 30, "key2": 20}},
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_language_usage = AsyncMock(return_value=mock_data)

            result = await get_language_metrics(period="day")

        assert result.by_language == {"python": 50, "javascript": 30}
        assert result.by_api_key == {"key1": 40, "key2": 40}

    @pytest.mark.asyncio
    async def test_get_language_metrics_with_stack_by_api_key(self):
        """Test language metrics with stack_by_api_key option."""
        from src.api.dashboard_metrics import get_language_metrics

        mock_data = {
            "by_language": {},
            "by_api_key": {},
            "matrix": {},
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_language_usage = AsyncMock(return_value=mock_data)

            await get_language_metrics(period="day", stack_by_api_key=True)

        call_kwargs = mock_service.get_language_usage.call_args.kwargs
        assert call_kwargs["stack_by_api_key"] is True


class TestGetTimeSeriesEndpoint:
    """Tests for get_time_series endpoint."""

    @pytest.mark.asyncio
    async def test_get_time_series_success(self):
        """Test successful time series retrieval."""
        from src.api.dashboard_metrics import get_time_series

        mock_data = {
            "timestamps": ["2024-01-01T00:00:00", "2024-01-01T01:00:00"],
            "executions": [10, 15],
            "success_rate": [95.0, 90.0],
            "avg_duration": [100.5, 120.3],
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_time_series = AsyncMock(return_value=mock_data)

            result = await get_time_series(period="day")

        assert result.timestamps == ["2024-01-01T00:00:00", "2024-01-01T01:00:00"]
        assert result.executions == [10, 15]
        assert result.granularity == "hour"

    @pytest.mark.asyncio
    async def test_get_time_series_week_period(self):
        """Test time series with week period."""
        from src.api.dashboard_metrics import get_time_series

        mock_data = {
            "timestamps": [],
            "executions": [],
            "success_rate": [],
            "avg_duration": [],
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_time_series = AsyncMock(return_value=mock_data)

            result = await get_time_series(period="week")

        assert result.granularity == "day"


class TestGetActivityHeatmapEndpoint:
    """Tests for get_activity_heatmap endpoint."""

    @pytest.mark.asyncio
    async def test_get_activity_heatmap_success(self):
        """Test successful heatmap retrieval."""
        from src.api.dashboard_metrics import get_activity_heatmap

        mock_data = {
            "matrix": [[1, 2, 3] + [0] * 21 for _ in range(7)],
            "max_value": 10,
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_heatmap_data = AsyncMock(return_value=mock_data)

            result = await get_activity_heatmap(period="week")

        assert len(result.matrix) == 7
        assert result.max_value == 10
        assert result.days == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assert len(result.hours) == 24

    @pytest.mark.asyncio
    async def test_get_activity_heatmap_expands_small_period(self):
        """Test that small periods are expanded to week for heatmap."""
        from src.api.dashboard_metrics import get_activity_heatmap

        mock_data = {
            "matrix": [[0] * 24 for _ in range(7)],
            "max_value": 0,
        }

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_heatmap_data = AsyncMock(return_value=mock_data)

            # Pass "hour" period but it should be expanded to "week"
            await get_activity_heatmap(period="hour")

            # Check that get_heatmap_data was called with week range
            call_kwargs = mock_service.get_heatmap_data.call_args.kwargs
            start = call_kwargs["start"]
            end = call_kwargs["end"]
            # Should be approximately 1 week
            assert (end - start) >= timedelta(days=6)


class TestGetApiKeysForFilterEndpoint:
    """Tests for get_api_keys_for_filter endpoint."""

    @pytest.mark.asyncio
    async def test_get_api_keys_success(self):
        """Test successful API keys list retrieval."""
        from src.api.dashboard_metrics import get_api_keys_for_filter

        # Mock managed keys
        mock_key = MagicMock()
        mock_key.key_hash = "hash123"
        mock_key.name = "Test Key"
        mock_key.key_prefix = "key_abc"
        mock_key.source = "managed"

        # Mock SQLite keys
        mock_sqlite_keys = [
            {"key_hash": "hash123", "usage_count": 100},
        ]

        with patch("src.api.dashboard_metrics.get_api_key_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_keys = AsyncMock(return_value=[mock_key])
            mock_get_manager.return_value = mock_manager

            with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
                mock_service.get_api_keys_list = AsyncMock(return_value=mock_sqlite_keys)

                result = await get_api_keys_for_filter()

        assert len(result) == 1
        assert result[0].key_hash == "hash123"
        assert result[0].name == "Test Key"
        assert result[0].usage_count == 100

    @pytest.mark.asyncio
    async def test_get_api_keys_with_env_keys(self):
        """Test API keys with environment keys included."""
        from src.api.dashboard_metrics import get_api_keys_for_filter

        # Mock managed keys including env key
        mock_managed_key = MagicMock()
        mock_managed_key.key_hash = "hash123"
        mock_managed_key.name = "Managed Key"
        mock_managed_key.key_prefix = "key_abc"
        mock_managed_key.source = "managed"

        mock_env_key = MagicMock()
        mock_env_key.key_hash = "envhash456"
        mock_env_key.name = "Env Key"
        mock_env_key.key_prefix = "env_xyz"
        mock_env_key.source = "environment"
        mock_env_key.usage_count = 0

        # SQLite only has the managed key
        mock_sqlite_keys = [
            {"key_hash": "hash123", "usage_count": 50},
        ]

        with patch("src.api.dashboard_metrics.get_api_key_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_keys = AsyncMock(return_value=[mock_managed_key, mock_env_key])
            mock_get_manager.return_value = mock_manager

            with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
                mock_service.get_api_keys_list = AsyncMock(return_value=mock_sqlite_keys)

                result = await get_api_keys_for_filter()

        # Should include both managed and env keys
        assert len(result) == 2
        key_hashes = [r.key_hash for r in result]
        assert "hash123" in key_hashes
        assert "envhash456" in key_hashes

    @pytest.mark.asyncio
    async def test_get_api_keys_unknown_key(self):
        """Test API keys when SQLite has unknown keys."""
        from src.api.dashboard_metrics import get_api_keys_for_filter

        # No managed keys
        mock_sqlite_keys = [
            {"key_hash": "unknownhash", "usage_count": 25},
        ]

        with patch("src.api.dashboard_metrics.get_api_key_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_keys = AsyncMock(return_value=[])
            mock_get_manager.return_value = mock_manager

            with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
                mock_service.get_api_keys_list = AsyncMock(return_value=mock_sqlite_keys)

                result = await get_api_keys_for_filter()

        # Should create a placeholder key
        assert len(result) == 1
        assert result[0].key_hash == "unknownhash"
        assert result[0].name == "Key unknownh"


class TestGetTopLanguagesEndpoint:
    """Tests for get_top_languages endpoint."""

    @pytest.mark.asyncio
    async def test_get_top_languages_success(self):
        """Test successful top languages retrieval."""
        from src.api.dashboard_metrics import get_top_languages

        mock_languages = [
            {"language": "python", "count": 100},
            {"language": "javascript", "count": 50},
        ]

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_top_languages = AsyncMock(return_value=mock_languages)

            result = await get_top_languages(period="day", limit=5)

        assert result["languages"] == mock_languages
        assert result["period"] == "day"

    @pytest.mark.asyncio
    async def test_get_top_languages_with_custom_limit(self):
        """Test top languages with custom limit."""
        from src.api.dashboard_metrics import get_top_languages

        mock_languages = [{"language": "python", "count": 100}]

        with patch("src.api.dashboard_metrics.sqlite_metrics_service") as mock_service:
            mock_service.get_top_languages = AsyncMock(return_value=mock_languages)

            await get_top_languages(period="week", limit=10)

        call_kwargs = mock_service.get_top_languages.call_args.kwargs
        assert call_kwargs["limit"] == 10
