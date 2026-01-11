"""Unit tests for Authentication Dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.dependencies.auth import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_optional,
    verify_api_key,
    verify_api_key_optional,
)


@pytest.fixture
def mock_request():
    """Create a mock request."""
    request = MagicMock()
    request.state = MagicMock()
    request.state.authenticated = False
    request.headers = MagicMock()
    request.headers.get.return_value = None
    return request


@pytest.fixture
def mock_credentials():
    """Create mock credentials."""
    credentials = MagicMock()
    credentials.credentials = "test-bearer-token"
    return credentials


@pytest.fixture
def mock_auth_service():
    """Create a mock auth service."""
    service = MagicMock()
    service.validate_api_key = AsyncMock(return_value=True)
    return service


class TestVerifyApiKey:
    """Tests for verify_api_key dependency."""

    @pytest.mark.asyncio
    async def test_already_authenticated(self, mock_request):
        """Test when middleware already authenticated."""
        mock_request.state.authenticated = True
        mock_request.state.api_key = "middleware-key"

        result = await verify_api_key(mock_request, None)

        assert result == "middleware-key"

    @pytest.mark.asyncio
    async def test_x_api_key_header(self, mock_request, mock_auth_service):
        """Test authentication with x-api-key header."""
        mock_request.headers.get.return_value = "header-api-key"

        with patch("src.dependencies.auth.get_auth_service", return_value=mock_auth_service):
            result = await verify_api_key(mock_request, None)

        assert result == "header-api-key"

    @pytest.mark.asyncio
    async def test_authorization_header_fallback(self, mock_request, mock_credentials, mock_auth_service):
        """Test authentication with Authorization header fallback."""
        mock_request.headers.get.return_value = None

        with patch("src.dependencies.auth.get_auth_service", return_value=mock_auth_service):
            result = await verify_api_key(mock_request, mock_credentials)

        assert result == "test-bearer-token"

    @pytest.mark.asyncio
    async def test_no_api_key_raises_401(self, mock_request):
        """Test that missing API key raises 401."""
        mock_request.headers.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request, None)

        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_401(self, mock_request, mock_auth_service):
        """Test that invalid API key raises 401."""
        mock_request.headers.get.return_value = "invalid-key"
        mock_auth_service.validate_api_key.return_value = False

        with patch("src.dependencies.auth.get_auth_service", return_value=mock_auth_service):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(mock_request, None)

        assert exc_info.value.status_code == 401
        assert "Invalid" in exc_info.value.detail


class TestVerifyApiKeyOptional:
    """Tests for verify_api_key_optional dependency."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_key(self, mock_request):
        """Test that None is returned when no API key is provided."""
        mock_request.headers.get.return_value = None

        result = await verify_api_key_optional(mock_request, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_key_when_valid(self, mock_request, mock_auth_service):
        """Test that key is returned when valid."""
        mock_request.headers.get.return_value = "valid-key"

        with patch("src.dependencies.auth.get_auth_service", return_value=mock_auth_service):
            result = await verify_api_key_optional(mock_request, None)

        assert result == "valid-key"

    @pytest.mark.asyncio
    async def test_raises_when_invalid_key(self, mock_request, mock_auth_service):
        """Test that invalid key still raises exception."""
        mock_request.headers.get.return_value = "invalid-key"
        mock_auth_service.validate_api_key.return_value = False

        with patch("src.dependencies.auth.get_auth_service", return_value=mock_auth_service):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key_optional(mock_request, None)

        assert exc_info.value.status_code == 401


class TestAuthenticatedUser:
    """Tests for AuthenticatedUser class."""

    def test_init(self):
        """Test AuthenticatedUser initialization."""
        user = AuthenticatedUser("test-api-key-12345678")

        assert user.api_key == "test-api-key-12345678"
        assert user.key_prefix == "test-api..."

    def test_init_short_key(self):
        """Test AuthenticatedUser with short key."""
        user = AuthenticatedUser("short")

        assert user.api_key == "short"
        assert user.key_prefix == "short"

    def test_str(self):
        """Test string representation."""
        user = AuthenticatedUser("test-api-key-12345678")

        result = str(user)

        assert "AuthenticatedUser" in result
        assert "test-api..." in result


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_returns_authenticated_user(self):
        """Test that authenticated user is returned."""
        # This function just wraps verify_api_key result
        # We need to mock the dependency injection
        api_key = "test-key-12345678"

        # Call directly as the dependency injection is handled by FastAPI
        result = await get_current_user(api_key)

        assert isinstance(result, AuthenticatedUser)
        assert result.api_key == api_key


class TestGetCurrentUserOptional:
    """Tests for get_current_user_optional dependency."""

    @pytest.mark.asyncio
    async def test_returns_user_when_key_present(self):
        """Test that user is returned when key is present."""
        api_key = "test-key-12345678"

        result = await get_current_user_optional(api_key)

        assert isinstance(result, AuthenticatedUser)
        assert result.api_key == api_key

    @pytest.mark.asyncio
    async def test_returns_none_when_no_key(self):
        """Test that None is returned when no key."""
        result = await get_current_user_optional(None)

        assert result is None
