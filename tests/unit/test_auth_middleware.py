"""Unit tests for authentication middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.middleware.auth import AuthenticationMiddleware


@pytest.fixture
def mock_app():
    """Create a mock ASGI app."""
    return AsyncMock()


@pytest.fixture
def auth_middleware(mock_app):
    """Create auth middleware instance."""
    return AuthenticationMiddleware(mock_app)


class TestAuthMiddlewareInit:
    """Tests for AuthenticationMiddleware initialization."""

    def test_init(self, mock_app):
        """Test middleware initialization."""
        middleware = AuthenticationMiddleware(mock_app)

        assert middleware.app == mock_app
        assert "/health" in middleware.excluded_paths
        assert "/docs" in middleware.excluded_paths
        assert "/redoc" in middleware.excluded_paths
        assert "/openapi.json" in middleware.excluded_paths


class TestShouldSkipAuth:
    """Tests for _should_skip_auth method."""

    def test_skip_health_endpoint(self, auth_middleware):
        """Test health endpoint is skipped."""
        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.method = "GET"

        assert auth_middleware._should_skip_auth(mock_request) is True

    def test_skip_docs_endpoint(self, auth_middleware):
        """Test docs endpoint is skipped."""
        mock_request = MagicMock()
        mock_request.url.path = "/docs"
        mock_request.method = "GET"

        assert auth_middleware._should_skip_auth(mock_request) is True

    def test_skip_options_request(self, auth_middleware):
        """Test OPTIONS requests are skipped."""
        mock_request = MagicMock()
        mock_request.url.path = "/api/execute"
        mock_request.method = "OPTIONS"

        assert auth_middleware._should_skip_auth(mock_request) is True

    def test_dont_skip_api_endpoint(self, auth_middleware):
        """Test API endpoint is not skipped."""
        mock_request = MagicMock()
        mock_request.url.path = "/api/execute"
        mock_request.method = "POST"

        assert auth_middleware._should_skip_auth(mock_request) is False


class TestExtractApiKey:
    """Tests for _extract_api_key method."""

    def test_extract_from_x_api_key_header(self, auth_middleware):
        """Test extraction from x-api-key header."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "test-key" if h == "x-api-key" else None

        result = auth_middleware._extract_api_key(mock_request)

        assert result == "test-key"

    def test_extract_from_bearer_authorization(self, auth_middleware):
        """Test extraction from Bearer authorization."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "Bearer test-key" if h == "authorization" else None

        result = auth_middleware._extract_api_key(mock_request)

        assert result == "test-key"

    def test_extract_from_apikey_authorization(self, auth_middleware):
        """Test extraction from ApiKey authorization."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "ApiKey test-key" if h == "authorization" else None

        result = auth_middleware._extract_api_key(mock_request)

        assert result == "test-key"

    def test_extract_no_key(self, auth_middleware):
        """Test when no API key is present."""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        result = auth_middleware._extract_api_key(mock_request)

        assert result is None

    def test_extract_prefers_x_api_key(self, auth_middleware):
        """Test x-api-key is preferred over Authorization."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: {
            "x-api-key": "key-from-header",
            "authorization": "Bearer key-from-auth",
        }.get(h)

        result = auth_middleware._extract_api_key(mock_request)

        assert result == "key-from-header"


class TestGetClientIp:
    """Tests for _get_client_ip method."""

    def test_get_ip_from_x_forwarded_for(self, auth_middleware):
        """Test getting IP from X-Forwarded-For."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "1.2.3.4, 5.6.7.8" if h == "x-forwarded-for" else None
        mock_request.client = MagicMock(host="127.0.0.1")

        result = auth_middleware._get_client_ip(mock_request)

        assert result == "1.2.3.4"

    def test_get_ip_from_x_real_ip(self, auth_middleware):
        """Test getting IP from X-Real-IP."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "1.2.3.4" if h == "x-real-ip" else None
        mock_request.client = MagicMock(host="127.0.0.1")

        result = auth_middleware._get_client_ip(mock_request)

        assert result == "1.2.3.4"

    def test_get_ip_from_client(self, auth_middleware):
        """Test getting IP from client."""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client = MagicMock(host="192.168.1.1")

        result = auth_middleware._get_client_ip(mock_request)

        assert result == "192.168.1.1"

    def test_get_ip_unknown(self, auth_middleware):
        """Test getting IP when client is None."""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client = None

        result = auth_middleware._get_client_ip(mock_request)

        assert result == "unknown"


class TestAuthenticateRequest:
    """Tests for _authenticate_request method."""

    @pytest.mark.asyncio
    async def test_authenticate_valid_key(self, auth_middleware):
        """Test authentication with valid API key."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "valid-key" if h == "x-api-key" else None
        mock_request.client = MagicMock(host="127.0.0.1")

        scope = {"state": {}}

        mock_auth_service = AsyncMock()
        mock_auth_service.check_rate_limit.return_value = True
        mock_auth_service.validate_api_key.return_value = True

        with patch("src.middleware.auth.get_auth_service", return_value=mock_auth_service):
            await auth_middleware._authenticate_request(mock_request, scope)

        assert scope["state"]["authenticated"] is True
        assert scope["state"]["api_key"] == "valid-key"

    @pytest.mark.asyncio
    async def test_authenticate_rate_limited(self, auth_middleware):
        """Test authentication when rate limited."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "valid-key" if h == "x-api-key" else None
        mock_request.client = MagicMock(host="127.0.0.1")

        scope = {}

        mock_auth_service = AsyncMock()
        mock_auth_service.check_rate_limit.return_value = False

        with patch("src.middleware.auth.get_auth_service", return_value=mock_auth_service):
            with pytest.raises(HTTPException) as exc_info:
                await auth_middleware._authenticate_request(mock_request, scope)

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_authenticate_invalid_key(self, auth_middleware):
        """Test authentication with invalid API key."""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: "invalid-key" if h == "x-api-key" else None
        mock_request.client = MagicMock(host="127.0.0.1")

        scope = {}

        mock_auth_service = AsyncMock()
        mock_auth_service.check_rate_limit.return_value = True
        mock_auth_service.validate_api_key.return_value = False

        with patch("src.middleware.auth.get_auth_service", return_value=mock_auth_service):
            with pytest.raises(HTTPException) as exc_info:
                await auth_middleware._authenticate_request(mock_request, scope)

            assert exc_info.value.status_code == 401


class TestMiddlewareCall:
    """Tests for middleware __call__ method."""

    @pytest.mark.asyncio
    async def test_call_non_http(self, auth_middleware, mock_app):
        """Test non-HTTP requests pass through."""
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await auth_middleware(scope, receive, send)

        mock_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_call_excluded_path(self, auth_middleware, mock_app):
        """Test excluded paths pass through."""
        scope = {
            "type": "http",
            "path": "/health",
            "method": "GET",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        await auth_middleware(scope, receive, send)

        mock_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_authenticated(self, auth_middleware, mock_app):
        """Test authenticated requests pass through."""
        scope = {
            "type": "http",
            "path": "/api/execute",
            "method": "POST",
            "headers": [(b"x-api-key", b"valid-key")],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        mock_auth_service = AsyncMock()
        mock_auth_service.check_rate_limit.return_value = True
        mock_auth_service.validate_api_key.return_value = True

        with patch("src.middleware.auth.get_auth_service", return_value=mock_auth_service):
            await auth_middleware(scope, receive, send)

        mock_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_unauthenticated(self, auth_middleware, mock_app):
        """Test unauthenticated requests return 401."""
        scope = {
            "type": "http",
            "path": "/api/execute",
            "method": "POST",
            "headers": [(b"x-api-key", b"invalid-key")],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        mock_auth_service = AsyncMock()
        mock_auth_service.check_rate_limit.return_value = True
        mock_auth_service.validate_api_key.return_value = False

        with patch("src.middleware.auth.get_auth_service", return_value=mock_auth_service):
            await auth_middleware(scope, receive, send)

        # App should not be called
        mock_app.assert_not_called()
        # send should be called (for error response)
        send.assert_called()

    @pytest.mark.asyncio
    async def test_call_internal_error(self, auth_middleware, mock_app):
        """Test internal errors return 500."""
        scope = {
            "type": "http",
            "path": "/api/execute",
            "method": "POST",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch("src.middleware.auth.get_auth_service", side_effect=Exception("Internal error")):
            await auth_middleware(scope, receive, send)

        mock_app.assert_not_called()
        send.assert_called()
