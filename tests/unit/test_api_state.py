"""Unit tests for State API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, Response

from src.api.state import (
    MAX_STATE_SIZE,
    delete_state,
    download_state,
    get_state_info,
    upload_state,
)
from src.models.state import StateInfo, StateUploadResponse


@pytest.fixture
def mock_state_service():
    """Create a mock state service."""
    service = MagicMock()
    service.get_state_hash = AsyncMock(return_value=None)
    service.get_state_raw = AsyncMock(return_value=None)
    service.save_state_raw = AsyncMock(return_value=True)
    service.delete_state = AsyncMock()
    service.get_full_state_info = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_state_archival_service():
    """Create a mock state archival service."""
    service = MagicMock()
    service.restore_state = AsyncMock(return_value=False)
    service.has_archived_state = AsyncMock(return_value=False)
    service.delete_archived_state = AsyncMock()
    return service


@pytest.fixture
def mock_request():
    """Create a mock request."""
    request = MagicMock(spec=Request)
    return request


class TestDownloadState:
    """Tests for download_state endpoint."""

    @pytest.mark.asyncio
    async def test_download_state_success(self, mock_state_service, mock_state_archival_service):
        """Test successful state download."""
        mock_state_service.get_state_hash.return_value = "abc123hash"
        mock_state_service.get_state_raw.return_value = b"\x01\x02\x03\x04"

        response = await download_state(
            session_id="session-123",
            state_service=mock_state_service,
            state_archival_service=mock_state_archival_service,
            if_none_match=None,
        )

        assert isinstance(response, Response)
        assert response.body == b"\x01\x02\x03\x04"
        assert response.media_type == "application/octet-stream"
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_download_state_not_found(self, mock_state_service, mock_state_archival_service):
        """Test state not found returns 404."""
        mock_state_service.get_state_hash.return_value = None

        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            with pytest.raises(HTTPException) as exc_info:
                await download_state(
                    session_id="session-123",
                    state_service=mock_state_service,
                    state_archival_service=mock_state_archival_service,
                    if_none_match=None,
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_state_304_not_modified(self, mock_state_service, mock_state_archival_service):
        """Test 304 response when ETag matches."""
        mock_state_service.get_state_hash.return_value = "abc123hash"

        response = await download_state(
            session_id="session-123",
            state_service=mock_state_service,
            state_archival_service=mock_state_archival_service,
            if_none_match='"abc123hash"',
        )

        assert response.status_code == 304

    @pytest.mark.asyncio
    async def test_download_state_restores_from_archive(self, mock_state_service, mock_state_archival_service):
        """Test state is restored from archive when not in Redis."""
        mock_state_service.get_state_hash.side_effect = [None, "restored123"]
        mock_state_archival_service.restore_state.return_value = True
        mock_state_service.get_state_raw.return_value = b"\x01\x02"

        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            response = await download_state(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
                if_none_match=None,
            )

        assert isinstance(response, Response)
        mock_state_archival_service.restore_state.assert_called_once_with("session-123")

    @pytest.mark.asyncio
    async def test_download_state_raw_bytes_missing(self, mock_state_service, mock_state_archival_service):
        """Test 404 when hash exists but raw bytes missing."""
        mock_state_service.get_state_hash.return_value = "abc123hash"
        mock_state_service.get_state_raw.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await download_state(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
                if_none_match=None,
            )

        assert exc_info.value.status_code == 404


class TestUploadState:
    """Tests for upload_state endpoint."""

    @pytest.mark.asyncio
    async def test_upload_state_success(self, mock_state_service, mock_request):
        """Test successful state upload."""
        # Version 1 state with some data
        mock_request.body = AsyncMock(return_value=b"\x01\x02\x03\x04")

        response = await upload_state(
            session_id="session-123",
            request=mock_request,
            state_service=mock_state_service,
        )

        assert isinstance(response, StateUploadResponse)
        assert response.message == "state_uploaded"
        assert response.size == 4
        mock_state_service.save_state_raw.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_state_too_large(self, mock_state_service, mock_request):
        """Test state upload rejected when too large."""
        mock_request.body = AsyncMock(return_value=b"\x01" * (MAX_STATE_SIZE + 1))

        with pytest.raises(HTTPException) as exc_info:
            await upload_state(
                session_id="session-123",
                request=mock_request,
                state_service=mock_state_service,
            )

        assert exc_info.value.status_code == 413
        assert "too_large" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_state_too_short(self, mock_state_service, mock_request):
        """Test state upload rejected when too short."""
        mock_request.body = AsyncMock(return_value=b"\x01")

        with pytest.raises(HTTPException) as exc_info:
            await upload_state(
                session_id="session-123",
                request=mock_request,
                state_service=mock_state_service,
            )

        assert exc_info.value.status_code == 400
        assert "too short" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_state_invalid_version(self, mock_state_service, mock_request):
        """Test state upload rejected with invalid version byte."""
        # Version 99 is invalid
        mock_request.body = AsyncMock(return_value=b"\x63\x02\x03")

        with pytest.raises(HTTPException) as exc_info:
            await upload_state(
                session_id="session-123",
                request=mock_request,
                state_service=mock_state_service,
            )

        assert exc_info.value.status_code == 400
        assert "Unknown state version" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_state_version_1(self, mock_state_service, mock_request):
        """Test state upload with version 1."""
        mock_request.body = AsyncMock(return_value=b"\x01\x02\x03")

        response = await upload_state(
            session_id="session-123",
            request=mock_request,
            state_service=mock_state_service,
        )

        assert response.message == "state_uploaded"

    @pytest.mark.asyncio
    async def test_upload_state_version_2(self, mock_state_service, mock_request):
        """Test state upload with version 2."""
        mock_request.body = AsyncMock(return_value=b"\x02\x02\x03")

        response = await upload_state(
            session_id="session-123",
            request=mock_request,
            state_service=mock_state_service,
        )

        assert response.message == "state_uploaded"

    @pytest.mark.asyncio
    async def test_upload_state_save_failed(self, mock_state_service, mock_request):
        """Test 500 when save fails."""
        mock_request.body = AsyncMock(return_value=b"\x01\x02\x03")
        mock_state_service.save_state_raw.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await upload_state(
                session_id="session-123",
                request=mock_request,
                state_service=mock_state_service,
            )

        assert exc_info.value.status_code == 500
        assert "save_failed" in str(exc_info.value.detail)


class TestGetStateInfo:
    """Tests for get_state_info endpoint."""

    @pytest.mark.asyncio
    async def test_get_state_info_from_redis(self, mock_state_service, mock_state_archival_service):
        """Test getting state info from Redis."""
        mock_state_service.get_full_state_info.return_value = {
            "size_bytes": 1024,
            "hash": "abc123",
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
        }

        response = await get_state_info(
            session_id="session-123",
            state_service=mock_state_service,
            state_archival_service=mock_state_archival_service,
        )

        assert isinstance(response, StateInfo)
        assert response.exists is True
        assert response.session_id == "session-123"
        assert response.source == "redis"
        assert response.size_bytes == 1024

    @pytest.mark.asyncio
    async def test_get_state_info_from_archive(self, mock_state_service, mock_state_archival_service):
        """Test getting state info from archive."""
        mock_state_service.get_full_state_info.return_value = None
        mock_state_archival_service.has_archived_state.return_value = True

        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            response = await get_state_info(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        assert response.exists is True
        assert response.source == "archive"

    @pytest.mark.asyncio
    async def test_get_state_info_not_found(self, mock_state_service, mock_state_archival_service):
        """Test state info when state doesn't exist."""
        mock_state_service.get_full_state_info.return_value = None
        mock_state_archival_service.has_archived_state.return_value = False

        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            response = await get_state_info(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        assert response.exists is False
        assert response.session_id == "session-123"

    @pytest.mark.asyncio
    async def test_get_state_info_archive_disabled(self, mock_state_service, mock_state_archival_service):
        """Test state info when archive is disabled."""
        mock_state_service.get_full_state_info.return_value = None

        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            response = await get_state_info(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        assert response.exists is False
        # Archive service should not be called
        mock_state_archival_service.has_archived_state.assert_not_called()


class TestDeleteState:
    """Tests for delete_state endpoint."""

    @pytest.mark.asyncio
    async def test_delete_state_success(self, mock_state_service, mock_state_archival_service):
        """Test successful state deletion."""
        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = True

            response = await delete_state(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        assert response.status_code == 204
        mock_state_service.delete_state.assert_called_once_with("session-123")
        mock_state_archival_service.delete_archived_state.assert_called_once_with("session-123")

    @pytest.mark.asyncio
    async def test_delete_state_archive_disabled(self, mock_state_service, mock_state_archival_service):
        """Test state deletion when archive is disabled."""
        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            response = await delete_state(
                session_id="session-123",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        assert response.status_code == 204
        mock_state_service.delete_state.assert_called_once_with("session-123")
        mock_state_archival_service.delete_archived_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_state_nonexistent(self, mock_state_service, mock_state_archival_service):
        """Test deleting non-existent state returns 204."""
        with patch("src.api.state.settings") as mock_settings:
            mock_settings.state_archive_enabled = False

            response = await delete_state(
                session_id="nonexistent-session",
                state_service=mock_state_service,
                state_archival_service=mock_state_archival_service,
            )

        # Should still return 204, not 404
        assert response.status_code == 204
