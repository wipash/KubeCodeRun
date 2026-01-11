"""Unit tests for Security Headers Middleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.middleware.headers import SecurityHeadersMiddleware


@pytest.fixture
def mock_app():
    """Create a mock ASGI app."""
    return AsyncMock()


@pytest.fixture
def headers_middleware(mock_app):
    """Create a headers middleware instance."""
    return SecurityHeadersMiddleware(mock_app)


class TestSecurityHeadersMiddlewareInit:
    """Tests for SecurityHeadersMiddleware initialization."""

    def test_init(self, mock_app):
        """Test middleware initialization."""
        middleware = SecurityHeadersMiddleware(mock_app)

        assert middleware.app is mock_app

    def test_security_headers_defined(self):
        """Test that security headers are defined."""
        headers = SecurityHeadersMiddleware.SECURITY_HEADERS

        assert b"x-content-type-options" in headers
        assert b"x-frame-options" in headers
        assert b"x-xss-protection" in headers
        assert b"strict-transport-security" in headers
        assert b"content-security-policy" in headers
        assert b"referrer-policy" in headers
        assert b"permissions-policy" in headers


class TestSecurityHeadersMiddlewareCall:
    """Tests for SecurityHeadersMiddleware __call__ method."""

    @pytest.mark.asyncio
    async def test_non_http_passes_through(self, headers_middleware, mock_app):
        """Test that non-HTTP requests pass through."""
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await headers_middleware(scope, receive, send)

        mock_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_adds_security_headers(self, mock_app):
        """Test that security headers are added to HTTP responses."""
        middleware = SecurityHeadersMiddleware(mock_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }
        receive = AsyncMock()

        captured_message = None

        async def capture_send(message):
            nonlocal captured_message
            captured_message = message

        # Configure mock app to send a response
        async def app_that_responds(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )

        middleware.app = app_that_responds

        await middleware(scope, receive, capture_send)

        assert captured_message is not None
        assert captured_message["type"] == "http.response.start"

        # Convert headers to dict for easier checking
        headers_dict = dict(captured_message["headers"])
        assert b"x-content-type-options" in headers_dict
        assert headers_dict[b"x-content-type-options"] == b"nosniff"
        assert b"x-frame-options" in headers_dict
        assert headers_dict[b"x-frame-options"] == b"DENY"

    @pytest.mark.asyncio
    async def test_preserves_existing_headers(self, mock_app):
        """Test that existing headers are preserved."""
        middleware = SecurityHeadersMiddleware(mock_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }
        receive = AsyncMock()

        captured_message = None

        async def capture_send(message):
            nonlocal captured_message
            captured_message = message

        # Configure mock app to send a response with existing headers
        async def app_with_headers(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )

        middleware.app = app_with_headers

        await middleware(scope, receive, capture_send)

        headers_dict = dict(captured_message["headers"])
        assert b"content-type" in headers_dict
        assert headers_dict[b"content-type"] == b"application/json"
        # Also has security headers
        assert b"x-frame-options" in headers_dict

    @pytest.mark.asyncio
    async def test_body_message_passes_through(self, mock_app):
        """Test that body messages pass through unchanged."""
        middleware = SecurityHeadersMiddleware(mock_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }
        receive = AsyncMock()

        captured_messages = []

        async def capture_send(message):
            captured_messages.append(message)

        # Configure mock app to send response start and body
        async def app_with_body(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"test body",
                }
            )

        middleware.app = app_with_body

        await middleware(scope, receive, capture_send)

        assert len(captured_messages) == 2
        assert captured_messages[1]["type"] == "http.response.body"
        assert captured_messages[1]["body"] == b"test body"
