"""Unit tests for State Archival Service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from minio.error import S3Error

from src.services.state_archival import StateArchivalService


@pytest.fixture
def mock_state_service():
    """Create a mock state service."""
    service = MagicMock()
    service.get_state = AsyncMock(return_value=None)
    service.save_state = AsyncMock(return_value=True)
    service.save_state_raw = AsyncMock(return_value=True)
    service.get_state_raw = AsyncMock(return_value=None)
    service.delete_state = AsyncMock()
    return service


@pytest.fixture
def mock_minio_client():
    """Create a mock MinIO client."""
    client = MagicMock()
    client.bucket_exists = MagicMock(return_value=True)
    client.make_bucket = MagicMock()
    client.put_object = MagicMock()
    client.get_object = MagicMock()
    client.remove_object = MagicMock()
    client.stat_object = MagicMock()
    return client


@pytest.fixture
def archival_service(mock_state_service, mock_minio_client):
    """Create an archival service with mocked dependencies."""
    with patch("src.services.state_archival.settings") as mock_settings:
        mock_settings.minio_bucket = "test-bucket"
        mock_settings.state_ttl_seconds = 7200
        mock_settings.minio.create_client.return_value = mock_minio_client

        service = StateArchivalService(
            state_service=mock_state_service,
            minio_client=mock_minio_client,
        )
        return service


class TestStateArchivalServiceInit:
    """Tests for StateArchivalService initialization."""

    def test_init_with_dependencies(self, mock_state_service, mock_minio_client):
        """Test initialization with provided dependencies."""
        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.minio_bucket = "test-bucket"

            service = StateArchivalService(
                state_service=mock_state_service,
                minio_client=mock_minio_client,
            )

            assert service.state_service is mock_state_service
            assert service.minio_client is mock_minio_client
            assert service.bucket_name == "test-bucket"
            assert service._bucket_checked is False

    def test_get_state_object_key(self, archival_service):
        """Test state object key generation."""
        key = archival_service._get_state_object_key("session-123")

        assert key == "states/session-123/state.dat"


class TestEnsureBucketExists:
    """Tests for _ensure_bucket_exists method."""

    @pytest.mark.asyncio
    async def test_bucket_already_exists(self, archival_service, mock_minio_client):
        """Test when bucket already exists."""
        mock_minio_client.bucket_exists.return_value = True

        await archival_service._ensure_bucket_exists()

        assert archival_service._bucket_checked is True
        mock_minio_client.make_bucket.assert_not_called()

    @pytest.mark.asyncio
    async def test_bucket_created(self, archival_service, mock_minio_client):
        """Test bucket creation when it doesn't exist."""
        mock_minio_client.bucket_exists.return_value = False

        await archival_service._ensure_bucket_exists()

        assert archival_service._bucket_checked is True
        mock_minio_client.make_bucket.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_if_already_checked(self, archival_service, mock_minio_client):
        """Test skipping bucket check if already done."""
        archival_service._bucket_checked = True

        await archival_service._ensure_bucket_exists()

        mock_minio_client.bucket_exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_bucket_error_raises(self, archival_service, mock_minio_client):
        """Test S3Error is raised on bucket check failure."""
        mock_minio_client.bucket_exists.side_effect = S3Error("test", "TestError", "test", "test", "test", "test")

        with pytest.raises(S3Error):
            await archival_service._ensure_bucket_exists()


class TestArchiveState:
    """Tests for archive_state method."""

    @pytest.mark.asyncio
    async def test_archive_state_success(self, archival_service, mock_minio_client):
        """Test successful state archival."""
        archival_service._bucket_checked = True

        result = await archival_service.archive_state("session-123", "base64statedata")

        assert result is True
        mock_minio_client.put_object.assert_called_once()

        # Verify call arguments
        call_args = mock_minio_client.put_object.call_args
        assert call_args[0][0] == "test-bucket"
        assert "session-123" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_archive_state_error(self, archival_service, mock_minio_client):
        """Test state archival failure returns False."""
        archival_service._bucket_checked = True
        mock_minio_client.put_object.side_effect = Exception("Upload failed")

        result = await archival_service.archive_state("session-123", "base64statedata")

        assert result is False


class TestRestoreState:
    """Tests for restore_state method."""

    @pytest.mark.asyncio
    async def test_restore_state_success(self, archival_service, mock_minio_client, mock_state_service):
        """Test successful state restoration."""
        archival_service._bucket_checked = True

        # Mock response object
        mock_response = MagicMock()
        mock_response.read.return_value = b"statedata"
        mock_minio_client.get_object.return_value = mock_response

        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_ttl_seconds = 7200
            result = await archival_service.restore_state("session-123")

        assert result == "statedata"
        mock_state_service.save_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_state_not_found(self, archival_service, mock_minio_client):
        """Test restoration when state doesn't exist."""
        archival_service._bucket_checked = True

        error = S3Error("test", "NoSuchKey", "test", "test", "test", "test")
        mock_minio_client.get_object.side_effect = error

        result = await archival_service.restore_state("session-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_restore_state_error(self, archival_service, mock_minio_client):
        """Test restoration failure returns None."""
        archival_service._bucket_checked = True
        mock_minio_client.get_object.side_effect = Exception("Download failed")

        result = await archival_service.restore_state("session-123")

        assert result is None


class TestDeleteArchivedState:
    """Tests for delete_archived_state method."""

    @pytest.mark.asyncio
    async def test_delete_state_success(self, archival_service, mock_minio_client):
        """Test successful state deletion."""
        archival_service._bucket_checked = True

        result = await archival_service.delete_archived_state("session-123")

        assert result is True
        mock_minio_client.remove_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_state_not_found(self, archival_service, mock_minio_client):
        """Test deletion when state doesn't exist returns True."""
        archival_service._bucket_checked = True

        error = S3Error("test", "NoSuchKey", "test", "test", "test", "test")
        mock_minio_client.remove_object.side_effect = error

        result = await archival_service.delete_archived_state("session-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_state_s3_error(self, archival_service, mock_minio_client):
        """Test deletion S3 error returns False."""
        archival_service._bucket_checked = True

        error = S3Error("test", "AccessDenied", "test", "test", "test", "test")
        mock_minio_client.remove_object.side_effect = error

        result = await archival_service.delete_archived_state("session-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_state_generic_error(self, archival_service, mock_minio_client):
        """Test deletion generic error returns False."""
        archival_service._bucket_checked = True
        mock_minio_client.remove_object.side_effect = Exception("Delete failed")

        result = await archival_service.delete_archived_state("session-123")

        assert result is False


class TestHasArchivedState:
    """Tests for has_archived_state method."""

    @pytest.mark.asyncio
    async def test_has_state_true(self, archival_service, mock_minio_client):
        """Test checking for existing archived state."""
        archival_service._bucket_checked = True
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await archival_service.has_archived_state("session-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_has_state_false(self, archival_service, mock_minio_client):
        """Test checking for non-existing archived state."""
        archival_service._bucket_checked = True

        error = S3Error("test", "NoSuchKey", "test", "test", "test", "test")
        mock_minio_client.stat_object.side_effect = error

        result = await archival_service.has_archived_state("session-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_has_state_error(self, archival_service, mock_minio_client):
        """Test checking for state with error returns False."""
        archival_service._bucket_checked = True
        mock_minio_client.stat_object.side_effect = Exception("Check failed")

        result = await archival_service.has_archived_state("session-123")

        assert result is False


class TestArchiveInactiveStates:
    """Tests for archive_inactive_states method."""

    @pytest.mark.asyncio
    async def test_archive_inactive_states_disabled(self, archival_service):
        """Test archive_inactive_states when archival is disabled."""
        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            result = await archival_service.archive_inactive_states()

        assert result["archived"] == 0
        assert "disabled" in result.get("skipped", "")

    @pytest.mark.asyncio
    async def test_archive_inactive_states_success(self, archival_service, mock_state_service, mock_minio_client):
        """Test successful state archival."""
        archival_service._bucket_checked = True
        mock_state_service.get_states_for_archival = AsyncMock(return_value=[("session-123", 100, 1024)])
        mock_state_service.get_state.return_value = "base64statedata"
        mock_minio_client.stat_object.side_effect = S3Error("test", "NoSuchKey", "test", "test", "test", "test")

        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = True
            mock_settings.minio_bucket = "test-bucket"

            result = await archival_service.archive_inactive_states()

        assert result["archived"] >= 0

    @pytest.mark.asyncio
    async def test_archive_inactive_states_already_archived(
        self, archival_service, mock_state_service, mock_minio_client
    ):
        """Test skipping already archived states."""
        archival_service._bucket_checked = True
        mock_state_service.get_states_for_archival = AsyncMock(return_value=[("session-123", 100, 1024)])
        mock_minio_client.stat_object.return_value = MagicMock()  # Exists

        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            result = await archival_service.archive_inactive_states()

        assert result["already_archived"] >= 1

    @pytest.mark.asyncio
    async def test_archive_inactive_states_error(self, archival_service, mock_state_service):
        """Test handling errors during archival."""
        mock_state_service.get_states_for_archival = AsyncMock(side_effect=Exception("Redis error"))

        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            result = await archival_service.archive_inactive_states()

        assert "error" in result


class TestCleanupExpiredArchives:
    """Tests for cleanup_expired_archives method."""

    @pytest.mark.asyncio
    async def test_cleanup_disabled(self, archival_service):
        """Test cleanup when archival is disabled."""
        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            result = await archival_service.cleanup_expired_archives()

        assert result["deleted"] == 0
        assert "disabled" in result.get("skipped", "")

    @pytest.mark.asyncio
    async def test_cleanup_error(self, archival_service, mock_minio_client):
        """Test handling errors during cleanup."""
        archival_service._bucket_checked = True
        mock_minio_client.list_objects.side_effect = Exception("MinIO error")

        with patch("src.services.state_archival.settings") as mock_settings:
            mock_settings.state_archive_enabled = True
            mock_settings.state_archive_ttl_days = 30

            result = await archival_service.cleanup_expired_archives()

        assert "error" in result
