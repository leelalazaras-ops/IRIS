"""
Tests for mock AI provider.
"""

import pytest

from iris.ai.provider import AIRequest
from iris.ai.providers.mock import MockProvider


class TestMockProvider:
    """Tests for MockProvider."""

    @pytest.mark.asyncio
    async def test_default_response(self):
        """Test mock provider with default response."""
        provider = MockProvider()

        request = AIRequest(
            messages=[{"role": "user", "content": "Hello"}],
        )

        response = await provider.generate(request)

        assert response.content == "This is a mock response."
        assert response.model == "mock-model-v1"
        assert response.metadata["mock"] is True

    @pytest.mark.asyncio
    async def test_custom_response(self):
        """Test mock provider with custom response content."""
        provider = MockProvider(response_content="Custom test response")

        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
        )

        response = await provider.generate(request)

        assert response.content == "Custom test response"

    @pytest.mark.asyncio
    async def test_call_count_tracking(self):
        """Test that mock provider tracks call count."""
        provider = MockProvider()

        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
        )

        # First call
        response1 = await provider.generate(request)
        assert response1.metadata["call_count"] == 1
        assert provider.call_count == 1

        # Second call
        response2 = await provider.generate(request)
        assert response2.metadata["call_count"] == 2
        assert provider.call_count == 2

        # Third call
        response3 = await provider.generate(request)
        assert response3.metadata["call_count"] == 3
        assert provider.call_count == 3

    @pytest.mark.asyncio
    async def test_usage_calculation(self):
        """Test that mock provider calculates usage metrics."""
        provider = MockProvider(response_content="Short response")

        request = AIRequest(
            messages=[{"role": "user", "content": "Hello"}],
        )

        response = await provider.generate(request)

        assert "prompt_tokens" in response.usage
        assert "completion_tokens" in response.usage
        assert "total_tokens" in response.usage
        assert response.usage["total_tokens"] == (
            response.usage["prompt_tokens"] + response.usage["completion_tokens"]
        )

    @pytest.mark.asyncio
    async def test_close_no_error(self):
        """Test that close() completes without error."""
        provider = MockProvider()

        # Should not raise
        await provider.close()
