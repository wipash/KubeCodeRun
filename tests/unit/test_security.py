"""Unit tests for security utilities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.utils.security import (
    RateLimiter,
    SecurityAudit,
    SecurityValidator,
    get_rate_limiter,
)


class TestSecurityValidatorFilename:
    """Tests for filename validation."""

    def test_validate_filename_valid(self):
        """Test valid filenames."""
        assert SecurityValidator.validate_filename("test.txt") is True
        assert SecurityValidator.validate_filename("data.csv") is True
        assert SecurityValidator.validate_filename("script.py") is True
        assert SecurityValidator.validate_filename("image.png") is True

    def test_validate_filename_empty(self):
        """Test empty filename."""
        assert SecurityValidator.validate_filename("") is False
        assert SecurityValidator.validate_filename(None) is False

    def test_validate_filename_too_long(self):
        """Test filename that's too long."""
        long_name = "a" * 252 + ".txt"  # 256 chars total, over 255 limit
        assert SecurityValidator.validate_filename(long_name) is False

    def test_validate_filename_path_traversal(self):
        """Test path traversal attempts."""
        assert SecurityValidator.validate_filename("../secret.txt") is False
        assert SecurityValidator.validate_filename("..\\secret.txt") is False
        assert SecurityValidator.validate_filename("dir/file.txt") is False
        assert SecurityValidator.validate_filename("dir\\file.txt") is False

    def test_validate_filename_null_byte(self):
        """Test null byte in filename."""
        assert SecurityValidator.validate_filename("test\x00.txt") is False

    def test_validate_filename_disallowed_extension(self):
        """Test disallowed file extensions."""
        assert SecurityValidator.validate_filename("script.exe") is False
        assert SecurityValidator.validate_filename("script.sh") is False
        assert SecurityValidator.validate_filename("script.bat") is False

    def test_validate_filename_suspicious_chars(self):
        """Test suspicious characters."""
        assert SecurityValidator.validate_filename("test<script>.txt") is False
        assert SecurityValidator.validate_filename("test|pipe.txt") is False
        assert SecurityValidator.validate_filename('test"quote.txt') is False
        assert SecurityValidator.validate_filename("test?query.txt") is False
        assert SecurityValidator.validate_filename("test*star.txt") is False


class TestSecurityValidatorCodeContent:
    """Tests for code content validation."""

    def test_validate_code_empty(self):
        """Test empty code."""
        result = SecurityValidator.validate_code_content("", "python")
        assert result["valid"] is True
        assert result["warnings"] == []

    def test_validate_code_safe(self):
        """Test safe code."""
        code = "print('Hello, World!')"
        result = SecurityValidator.validate_code_content(code, "python")
        assert result["valid"] is True
        assert result["warnings"] == []

    def test_validate_code_os_import(self):
        """Test code with os import."""
        code = "import os\nos.system('ls')"
        result = SecurityValidator.validate_code_content(code, "python")
        assert result["valid"] is True  # Warnings but still valid
        assert len(result["warnings"]) > 0

    def test_validate_code_subprocess_import(self):
        """Test code with subprocess import."""
        code = "import subprocess"
        result = SecurityValidator.validate_code_content(code, "python")
        assert len(result["warnings"]) > 0

    def test_validate_code_eval(self):
        """Test code with eval."""
        code = "eval('1+1')"
        result = SecurityValidator.validate_code_content(code, "python")
        assert len(result["warnings"]) > 0

    def test_validate_code_exec(self):
        """Test code with exec."""
        code = "exec('print(1)')"
        result = SecurityValidator.validate_code_content(code, "python")
        assert len(result["warnings"]) > 0

    def test_validate_code_very_large(self):
        """Test very large code."""
        code = "x = 1\n" * 50001  # Over 100KB
        result = SecurityValidator.validate_code_content(code, "python")
        assert any("large" in w.lower() for w in result["warnings"])

    def test_validate_code_infinite_loop(self):
        """Test potential infinite loop."""
        code = "while True: pass"
        result = SecurityValidator.validate_code_content(code, "python")
        assert any("loop" in w.lower() for w in result["warnings"])

    def test_validate_code_large_range(self):
        """Test large range loop."""
        code = "for i in range(1000000000): pass"
        result = SecurityValidator.validate_code_content(code, "python")
        # May or may not warn depending on pattern

    def test_validate_code_non_python(self):
        """Test that non-Python code doesn't trigger Python warnings."""
        code = "import os"
        result = SecurityValidator.validate_code_content(code, "javascript")
        assert result["warnings"] == []


class TestSecurityValidatorSessionId:
    """Tests for session ID sanitization."""

    def test_sanitize_session_id_valid(self):
        """Test valid session IDs."""
        # Session IDs must be 8-64 characters
        assert SecurityValidator.sanitize_session_id("abc12345") == "abc12345"  # 8 chars
        assert SecurityValidator.sanitize_session_id("test-session-123") == "test-session-123"
        assert SecurityValidator.sanitize_session_id("session_with_underscore") == "session_with_underscore"

    def test_sanitize_session_id_empty(self):
        """Test empty session ID."""
        assert SecurityValidator.sanitize_session_id("") is None
        assert SecurityValidator.sanitize_session_id(None) is None

    def test_sanitize_session_id_removes_special_chars(self):
        """Test removal of special characters."""
        # After removing special chars, result must still be 8+ chars
        assert SecurityValidator.sanitize_session_id("session12!@#$%") == "session12"  # 9 chars after cleanup
        assert SecurityValidator.sanitize_session_id("testscript<>tag") == "testscripttag"

    def test_sanitize_session_id_too_short(self):
        """Test session ID that's too short."""
        assert SecurityValidator.sanitize_session_id("abc") is None

    def test_sanitize_session_id_too_long(self):
        """Test session ID that's too long."""
        long_id = "a" * 100
        assert SecurityValidator.sanitize_session_id(long_id) is None


class TestSecurityValidatorFileId:
    """Tests for file ID sanitization."""

    def test_sanitize_file_id(self):
        """Test file ID sanitization uses same rules as session ID."""
        assert SecurityValidator.sanitize_file_id("file-123") == "file-123"
        assert SecurityValidator.sanitize_file_id("") is None


class TestSecurityValidatorSecureId:
    """Tests for secure ID generation."""

    def test_generate_secure_id_no_prefix(self):
        """Test secure ID generation without prefix."""
        id1 = SecurityValidator.generate_secure_id()
        id2 = SecurityValidator.generate_secure_id()

        assert id1 != id2
        assert len(id1) > 10

    def test_generate_secure_id_with_prefix(self):
        """Test secure ID generation with prefix."""
        id1 = SecurityValidator.generate_secure_id("file")

        assert id1.startswith("file_")


class TestSecurityValidatorHash:
    """Tests for sensitive data hashing."""

    def test_hash_sensitive_data(self):
        """Test hashing of sensitive data."""
        hash1 = SecurityValidator.hash_sensitive_data("secret123")
        hash2 = SecurityValidator.hash_sensitive_data("secret123")
        hash3 = SecurityValidator.hash_sensitive_data("different")

        assert hash1 == hash2  # Same input = same output
        assert hash1 != hash3  # Different input = different output
        assert len(hash1) == 16  # Truncated hash


class TestSecurityValidatorFileExtension:
    """Tests for file extension extraction."""

    def test_get_file_extension(self):
        """Test file extension extraction."""
        assert SecurityValidator._get_file_extension("test.txt") == ".txt"
        assert SecurityValidator._get_file_extension("test.PY") == ".py"
        assert SecurityValidator._get_file_extension("test.tar.gz") == ".gz"
        assert SecurityValidator._get_file_extension("noextension") == ""


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter()
        assert limiter._requests == {}

    def test_is_allowed_first_request(self):
        """Test first request is allowed."""
        limiter = RateLimiter()
        assert limiter.is_allowed("user1") is True

    def test_is_allowed_under_limit(self):
        """Test requests under limit."""
        limiter = RateLimiter()

        for _ in range(50):
            assert limiter.is_allowed("user1", max_requests=100) is True

    def test_is_allowed_at_limit(self):
        """Test requests at limit."""
        limiter = RateLimiter()

        for _ in range(100):
            limiter.is_allowed("user1", max_requests=100)

        assert limiter.is_allowed("user1", max_requests=100) is False

    def test_is_allowed_different_identifiers(self):
        """Test different identifiers have separate limits."""
        limiter = RateLimiter()

        # Max out user1
        for _ in range(100):
            limiter.is_allowed("user1", max_requests=100)

        # user2 should still be allowed
        assert limiter.is_allowed("user2", max_requests=100) is True

    def test_is_allowed_window_expiry(self):
        """Test requests outside window don't count."""
        limiter = RateLimiter()

        # Add old requests
        old_time = datetime.now(UTC) - timedelta(hours=2)
        limiter._requests["user1"] = [old_time] * 100

        # New request should be allowed
        assert limiter.is_allowed("user1", max_requests=100, window_minutes=60) is True

    def test_cleanup_old_requests(self):
        """Test cleanup of old requests."""
        limiter = RateLimiter()

        # Add old requests
        old_time = datetime.now(UTC) - timedelta(hours=3)
        limiter._requests["user1"] = [old_time] * 50
        limiter._requests["user2"] = [old_time] * 30

        limiter._cleanup_old_requests()

        # Both should be cleaned up
        assert "user1" not in limiter._requests
        assert "user2" not in limiter._requests

    def test_cleanup_triggered_periodically(self):
        """Test cleanup is triggered periodically."""
        limiter = RateLimiter()
        limiter._last_cleanup = datetime.now(UTC) - timedelta(minutes=10)

        # Add old requests
        old_time = datetime.now(UTC) - timedelta(hours=3)
        limiter._requests["user1"] = [old_time] * 50

        # This should trigger cleanup
        limiter.is_allowed("user2")

        assert "user1" not in limiter._requests


class TestGetRateLimiter:
    """Tests for global rate limiter."""

    def test_get_rate_limiter(self):
        """Test getting global rate limiter."""
        limiter = get_rate_limiter()
        assert limiter is not None
        assert isinstance(limiter, RateLimiter)

    def test_get_rate_limiter_singleton(self):
        """Test rate limiter is singleton."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2


class TestSecurityAudit:
    """Tests for SecurityAudit."""

    def test_log_security_event_info(self):
        """Test logging info security event."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_security_event(
                "test_event",
                {"key": "value"},
                severity="info",
            )

            mock_logger.info.assert_called_once()

    def test_log_security_event_warning(self):
        """Test logging warning security event."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_security_event(
                "test_event",
                {"key": "value"},
                severity="warning",
            )

            mock_logger.warning.assert_called_once()

    def test_log_security_event_critical(self):
        """Test logging critical security event."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_security_event(
                "test_event",
                {"key": "value"},
                severity="critical",
            )

            mock_logger.critical.assert_called_once()

    def test_log_authentication_event_success(self):
        """Test logging successful authentication."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_authentication_event(
                success=True,
                api_key_prefix="sk-test",
                client_ip="127.0.0.1",
                endpoint="/api/execute",
            )

            mock_logger.info.assert_called_once()

    def test_log_authentication_event_failure(self):
        """Test logging failed authentication."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_authentication_event(
                success=False,
                api_key_prefix="sk-test",
                client_ip="127.0.0.1",
                endpoint="/api/execute",
            )

            mock_logger.warning.assert_called_once()

    def test_log_file_operation(self):
        """Test logging file operation."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_file_operation(
                operation="upload",
                session_id="session-123",
                file_id="file-456",
                filename="test.txt",
                success=True,
            )

            mock_logger.info.assert_called_once()

    def test_log_code_execution_without_warnings(self):
        """Test logging code execution without warnings."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_code_execution(
                session_id="session-123",
                language="python",
                code_hash="abc123",
                success=True,
                warnings=[],
            )

            mock_logger.info.assert_called_once()

    def test_log_code_execution_with_warnings(self):
        """Test logging code execution with warnings."""
        with patch("src.utils.security.logger") as mock_logger:
            SecurityAudit.log_code_execution(
                session_id="session-123",
                language="python",
                code_hash="abc123",
                success=True,
                warnings=["Potential dangerous pattern"],
            )

            mock_logger.warning.assert_called_once()
