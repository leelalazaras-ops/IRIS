"""
Tests for AI exceptions.
"""

import pytest

from iris.ai.exceptions import (
    AIError,
    ConfigurationError,
    ProviderError,
    AuthenticationError,
    TimeoutError,
    ResponseError,
)


class TestAIExceptions:
    """Tests for AI exception classes."""

    def test_ai_error_basic(self):
        """Test basic AIError creation."""
        error = AIError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.details == {}

    def test_ai_error_with_details(self):
        """Test AIError with details."""
        error = AIError("Error occurred", {"code": 500, "endpoint": "/api/test"})

        assert error.message == "Error occurred"
        assert error.details["code"] == 500
        assert error.details["endpoint"] == "/api/test"

    def test_configuration_error(self):
        """Test ConfigurationError is a subclass of AIError."""
        error = ConfigurationError("Invalid config", {"field": "api_key"})

        assert isinstance(error, AIError)
        assert error.message == "Invalid config"
        assert error.details["field"] == "api_key"

    def test_provider_error(self):
        """Test ProviderError is a subclass of AIError."""
        error = ProviderError("Provider failed", {"status": 500})

        assert isinstance(error, AIError)
        assert error.message == "Provider failed"

    def test_authentication_error_default_message(self):
        """Test AuthenticationError with default message."""
        error = AuthenticationError()

        assert isinstance(error, ProviderError)
        assert error.message == "Authentication failed"

    def test_authentication_error_sanitizes_key(self):
        """Test that AuthenticationError removes API keys from details."""
        error = AuthenticationError(
            "Auth failed",
            {"api_key": "secret123", "status_code": 401, "token": "bearer_xyz"}
        )

        assert "api_key" not in error.details
        assert "token" not in error.details
        assert error.details["status_code"] == 401

    def test_authentication_error_preserves_safe_details(self):
        """Test that AuthenticationError keeps non-secret details."""
        error = AuthenticationError(
            "Auth failed",
            {"status_code": 401, "endpoint": "/api/auth", "method": "POST"}
        )

        assert error.details["status_code"] == 401
        assert error.details["endpoint"] == "/api/auth"
        assert error.details["method"] == "POST"

    def test_timeout_error(self):
        """Test TimeoutError is a subclass of ProviderError."""
        error = TimeoutError("Request timed out", {"timeout": 30.0})

        assert isinstance(error, ProviderError)
        assert error.message == "Request timed out"
        assert error.details["timeout"] == 30.0

    def test_response_error(self):
        """Test ResponseError is a subclass of ProviderError."""
        error = ResponseError("Invalid response", {"raw": "{broken json"})

        assert isinstance(error, ProviderError)
        assert error.message == "Invalid response"

    def test_exception_hierarchy(self):
        """Test the complete exception hierarchy."""
        # All specific errors should be catchable as AIError
        errors = [
            ConfigurationError("test"),
            ProviderError("test"),
            AuthenticationError("test"),
            TimeoutError("test"),
            ResponseError("test"),
        ]

        for error in errors:
            assert isinstance(error, AIError)

        # Provider errors should be catchable as ProviderError
        provider_errors = [
            AuthenticationError("test"),
            TimeoutError("test"),
            ResponseError("test"),
        ]

        for error in provider_errors:
            assert isinstance(error, ProviderError)
