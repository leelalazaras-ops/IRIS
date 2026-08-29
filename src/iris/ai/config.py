"""
Configuration management for IRIS AI core.

Loads settings from environment variables with validation and sensible defaults.
"""

import os
from dataclasses import dataclass
from typing import Literal

from iris.ai.exceptions import ConfigurationError


@dataclass(frozen=True)
class AIConfig:
    """Configuration for IRIS AI runtime."""

    provider: str
    base_url: str | None
    api_key: str | None
    model: str
    timeout: float

    @classmethod
    def from_env(cls) -> "AIConfig":
        """
        Load configuration from environment variables.

        Environment variables:
        - IRIS_AI_PROVIDER: Provider type (default: "openai-compatible")
        - IRIS_AI_BASE_URL: API base URL (required for openai-compatible)
        - IRIS_AI_API_KEY: API authentication key (required for openai-compatible)
        - IRIS_AI_MODEL: Model identifier (default: "gpt-3.5-turbo")
        - IRIS_AI_TIMEOUT: Request timeout in seconds (default: 30.0)

        Returns:
            AIConfig instance

        Raises:
            ConfigurationError: If required configuration is missing or invalid
        """
        provider = os.getenv("IRIS_AI_PROVIDER", "openai-compatible")
        base_url = os.getenv("IRIS_AI_BASE_URL")
        api_key = os.getenv("IRIS_AI_API_KEY")
        model = os.getenv("IRIS_AI_MODEL", "gpt-3.5-turbo")

        # Parse timeout with validation
        timeout_str = os.getenv("IRIS_AI_TIMEOUT", "30.0")
        try:
            timeout = float(timeout_str)
            if timeout <= 0:
                raise ValueError("Timeout must be positive")
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid IRIS_AI_TIMEOUT: {timeout_str}",
                {"error": str(e)}
            )

        # Validate provider-specific requirements
        if provider == "openai-compatible":
            if not base_url:
                raise ConfigurationError(
                    "IRIS_AI_BASE_URL is required for openai-compatible provider",
                    {"provider": provider}
                )
            if not api_key:
                raise ConfigurationError(
                    "IRIS_AI_API_KEY is required for openai-compatible provider",
                    {"provider": provider}
                )
        elif provider == "mock":
            # Mock provider doesn't require base_url or api_key
            pass
        else:
            raise ConfigurationError(
                f"Unknown provider: {provider}",
                {"provider": provider}
            )

        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    def __repr__(self) -> str:
        """String representation with masked API key."""
        safe_key = "***" if self.api_key else None
        return (
            f"AIConfig(provider={self.provider!r}, "
            f"base_url={self.base_url!r}, "
            f"api_key={safe_key!r}, "
            f"model={self.model!r}, "
            f"timeout={self.timeout})"
        )
