"""
Tests for AI configuration.
"""

import os
import pytest

from iris.ai.config import AIConfig
from iris.ai.exceptions import ConfigurationError


class TestAIConfig:
    """Tests for AIConfig class."""

    def test_from_env_openai_compatible(self, monkeypatch):
        """Test loading OpenAI-compatible config from environment."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key-123")
        monkeypatch.setenv("IRIS_AI_MODEL", "gpt-4")
        monkeypatch.setenv("IRIS_AI_TIMEOUT", "60.0")

        config = AIConfig.from_env()

        assert config.provider == "openai-compatible"
        assert config.base_url == "https://api.example.com/v1"
        assert config.api_key == "test-key-123"
        assert config.model == "gpt-4"
        assert config.timeout == 60.0

    def test_from_env_defaults(self, monkeypatch):
        """Test default values are applied correctly."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key")

        # Clear optional vars
        monkeypatch.delenv("IRIS_AI_MODEL", raising=False)
        monkeypatch.delenv("IRIS_AI_TIMEOUT", raising=False)

        config = AIConfig.from_env()

        assert config.model == "gpt-3.5-turbo"
        assert config.timeout == 30.0

    def test_from_env_mock_provider(self, monkeypatch):
        """Test mock provider doesn't require API credentials."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")
        monkeypatch.delenv("IRIS_AI_BASE_URL", raising=False)
        monkeypatch.delenv("IRIS_AI_API_KEY", raising=False)

        config = AIConfig.from_env()

        assert config.provider == "mock"
        assert config.base_url is None
        assert config.api_key is None

    def test_from_env_missing_base_url(self, monkeypatch):
        """Test error when base URL is missing for openai-compatible."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.delenv("IRIS_AI_BASE_URL", raising=False)
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key")

        with pytest.raises(ConfigurationError) as exc_info:
            AIConfig.from_env()

        assert "IRIS_AI_BASE_URL is required" in str(exc_info.value)

    def test_from_env_missing_api_key(self, monkeypatch):
        """Test error when API key is missing for openai-compatible."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.delenv("IRIS_AI_API_KEY", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            AIConfig.from_env()

        assert "IRIS_AI_API_KEY is required" in str(exc_info.value)

    def test_from_env_invalid_timeout(self, monkeypatch):
        """Test error when timeout is invalid."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key")
        monkeypatch.setenv("IRIS_AI_TIMEOUT", "not-a-number")

        with pytest.raises(ConfigurationError) as exc_info:
            AIConfig.from_env()

        assert "Invalid IRIS_AI_TIMEOUT" in str(exc_info.value)

    def test_from_env_negative_timeout(self, monkeypatch):
        """Test error when timeout is negative."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key")
        monkeypatch.setenv("IRIS_AI_TIMEOUT", "-5.0")

        with pytest.raises(ConfigurationError) as exc_info:
            AIConfig.from_env()

        assert "Invalid IRIS_AI_TIMEOUT" in str(exc_info.value)

    def test_from_env_unknown_provider(self, monkeypatch):
        """Test error when provider is unknown."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "unknown-provider")

        with pytest.raises(ConfigurationError) as exc_info:
            AIConfig.from_env()

        assert "Unknown provider" in str(exc_info.value)

    def test_repr_masks_api_key(self, monkeypatch):
        """Test that __repr__ masks the API key."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "secret-key-12345")
        monkeypatch.setenv("IRIS_AI_MODEL", "gpt-4")

        config = AIConfig.from_env()
        repr_str = repr(config)

        assert "secret-key-12345" not in repr_str
        assert "***" in repr_str
        assert "gpt-4" in repr_str

    def test_config_is_frozen(self, monkeypatch):
        """Test that config is immutable."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        config = AIConfig.from_env()

        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            config.model = "different-model"
