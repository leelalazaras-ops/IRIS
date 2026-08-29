"""
AI-specific exceptions for IRIS.

All exceptions sanitize sensitive data to prevent secret leakage in logs.
"""


class AIError(Exception):
    """Base exception for all AI-related errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        return self.message


class ConfigurationError(AIError):
    """Raised when AI configuration is invalid or missing."""
    pass


class ProviderError(AIError):
    """Base exception for provider-related errors."""
    pass


class AuthenticationError(ProviderError):
    """Raised when API authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: dict | None = None):
        # Ensure API keys are never in the exception details
        safe_details = {}
        if details:
            safe_details = {k: v for k, v in details.items() if 'key' not in k.lower() and 'token' not in k.lower()}
        super().__init__(message, safe_details)


class TimeoutError(ProviderError):
    """Raised when a provider request times out."""
    pass


class ResponseError(ProviderError):
    """Raised when a provider returns an invalid or unexpected response."""
    pass
