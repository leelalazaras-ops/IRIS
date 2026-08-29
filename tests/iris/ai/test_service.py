"""
Tests for AI service.
"""

import pytest
from unittest.mock import AsyncMock, patch

from iris.ai.service import AIService
from iris.ai.config import AIConfig
from iris.ai.provider import AIResponse
from iris.ai.providers.mock import MockProvider
from iris.ai.providers.openai_compatible import OpenAICompatibleProvider
from iris.ai.exceptions import ConfigurationError


class TestAIService:
    """Tests for AIService."""

    @pytest.mark.asyncio
    async def test_service_with_mock_provider(self, monkeypatch):
        """Test service using mock provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        response = await service.generate(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert isinstance(response, str)
        assert len(response) > 0

        await service.close()

    @pytest.mark.asyncio
    async def test_service_with_metadata(self, monkeypatch):
        """Test service generate_with_metadata method."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        response = await service.generate_with_metadata(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
            max_tokens=50,
        )

        assert isinstance(response, AIResponse)
        assert response.content
        assert response.model
        assert "mock" in response.metadata

        await service.close()

    @pytest.mark.asyncio
    async def test_service_loads_config_from_env(self, monkeypatch):
        """Test that service loads configuration from environment."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")
        monkeypatch.setenv("IRIS_AI_MODEL", "custom-model")
        monkeypatch.setenv("IRIS_AI_TIMEOUT", "45.0")

        service = AIService()

        assert service.config.provider == "mock"
        assert service.config.model == "custom-model"
        assert service.config.timeout == 45.0

        await service.close()

    @pytest.mark.asyncio
    async def test_service_with_explicit_config(self, monkeypatch):
        """Test service with explicitly provided configuration."""
        config = AIConfig(
            provider="mock",
            base_url=None,
            api_key=None,
            model="test-model",
            timeout=60.0,
        )

        service = AIService(config=config)

        assert service.config.provider == "mock"
        assert service.config.model == "test-model"
        assert service.config.timeout == 60.0

        await service.close()

    @pytest.mark.asyncio
    async def test_provider_created_lazily(self, monkeypatch):
        """Test that provider is created on first use."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        # Provider should not exist yet
        assert service._provider is None

        # Generate triggers provider creation
        await service.generate(
            messages=[{"role": "user", "content": "Test"}],
        )

        # Provider should now exist
        assert service._provider is not None
        assert isinstance(service._provider, MockProvider)

        await service.close()

    @pytest.mark.asyncio
    async def test_provider_reused_across_calls(self, monkeypatch):
        """Test that the same provider instance is reused."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        await service.generate(messages=[{"role": "user", "content": "First"}])
        first_provider = service._provider

        await service.generate(messages=[{"role": "user", "content": "Second"}])
        second_provider = service._provider

        assert first_provider is second_provider

        await service.close()

    @pytest.mark.asyncio
    async def test_openai_compatible_provider_creation(self, monkeypatch):
        """Test creating OpenAI-compatible provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.setenv("IRIS_AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("IRIS_AI_API_KEY", "test-key")
        monkeypatch.setenv("IRIS_AI_MODEL", "gpt-4")

        service = AIService()

        # Trigger provider creation
        provider = service._get_provider()

        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.base_url == "https://api.example.com/v1"
        assert provider.model == "gpt-4"

        await service.close()

    @pytest.mark.asyncio
    async def test_unknown_provider_error(self, monkeypatch):
        """Test error when provider type is unknown."""
        config = AIConfig(
            provider="unknown-provider",
            base_url=None,
            api_key=None,
            model="test-model",
            timeout=30.0,
        )

        service = AIService(config=config)

        with pytest.raises(ConfigurationError) as exc_info:
            service._get_provider()

        assert "Unknown provider" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close_cleans_up_provider(self, monkeypatch):
        """Test that close() cleans up the provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        # Create provider
        await service.generate(messages=[{"role": "user", "content": "Test"}])
        assert service._provider is not None

        # Close service
        await service.close()

        # Provider should be cleared
        assert service._provider is None

    @pytest.mark.asyncio
    async def test_temperature_parameter(self, monkeypatch):
        """Test that temperature parameter is passed through."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        # Should not raise
        await service.generate(
            messages=[{"role": "user", "content": "Test"}],
            temperature=0.9,
        )

        await service.close()

    @pytest.mark.asyncio
    async def test_max_tokens_parameter(self, monkeypatch):
        """Test that max_tokens parameter is passed through."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        # Should not raise
        await service.generate(
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=150,
        )

        await service.close()

    @pytest.mark.asyncio
    async def test_multiple_messages(self, monkeypatch):
        """Test generating with multiple conversation messages."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        service = AIService()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        response = await service.generate(messages=messages)

        assert isinstance(response, str)
        assert len(response) > 0

        await service.close()
