"""
Tests for OpenAI-compatible provider.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, Mock

from iris.ai.provider import AIRequest
from iris.ai.providers.openai_compatible import OpenAICompatibleProvider
from iris.ai.exceptions import (
    AuthenticationError,
    TimeoutError,
    ResponseError,
    ProviderError,
)


@pytest.fixture
def mock_client(monkeypatch):
    """Create a mock HTTP client."""
    client = Mock()
    client.aclose = AsyncMock()
    return client


class TestOpenAICompatibleProvider:
    """Tests for OpenAICompatibleProvider."""

    @pytest.mark.asyncio
    async def test_successful_generation(self, monkeypatch):
        """Test successful API call and response parsing."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chatcmpl-123",
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello, world!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
        )

        response = await provider.generate(request)

        assert response.content == "Hello, world!"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 15
        assert response.metadata["finish_reason"] == "stop"

        # Verify request was made correctly
        provider._client.post.assert_called_once()
        call_args = provider._client.post.call_args
        assert call_args[0][0] == "https://api.example.com/v1/chat/completions"
        assert call_args[1]["json"]["model"] == "gpt-4"
        assert call_args[1]["json"]["messages"] == [{"role": "user", "content": "Hello"}]
        assert call_args[1]["json"]["temperature"] == 0.7
        assert call_args[1]["json"]["max_tokens"] == 100
        # Verify stream is set to false for non-streaming response
        assert call_args[1]["json"]["stream"] is False

        await provider.close()

    @pytest.mark.asyncio
    async def test_authentication_error(self, monkeypatch):
        """Test handling of authentication errors (401)."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="invalid-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 401

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(AuthenticationError) as exc_info:
            await provider.generate(request)

        assert "authentication failed" in str(exc_info.value).lower()
        assert exc_info.value.details["status_code"] == 401

        await provider.close()

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, monkeypatch):
        """Test handling of rate limit errors (429)."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 429

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert "rate limit" in str(exc_info.value).lower()

        await provider.close()

    @pytest.mark.asyncio
    async def test_server_error(self, monkeypatch):
        """Test handling of server errors (5xx)."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "error": {"message": "Internal server error"}
        }
        mock_response.text = "Internal server error"

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert "Internal server error" in str(exc_info.value)

        await provider.close()

    @pytest.mark.asyncio
    async def test_timeout_error(self, monkeypatch):
        """Test handling of timeout errors."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=1.0,
        )

        provider._client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(TimeoutError) as exc_info:
            await provider.generate(request)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.details["timeout"] == 1.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, monkeypatch):
        """Test handling of invalid JSON responses."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "{broken json"

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(ResponseError) as exc_info:
            await provider.generate(request)

        assert "parse" in str(exc_info.value).lower()

        await provider.close()

    @pytest.mark.asyncio
    async def test_missing_choices_in_response(self, monkeypatch):
        """Test handling of responses without choices."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chatcmpl-123",
            "model": "gpt-4",
            "choices": [],
        }

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        with pytest.raises(ResponseError) as exc_info:
            await provider.generate(request)

        assert "no choices" in str(exc_info.value).lower()

        await provider.close()

    @pytest.mark.asyncio
    async def test_malformed_response_structure(self, monkeypatch):
        """Test handling of malformed response structures with missing message key."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        # Completely invalid structure - not even a dict
        mock_response.json.return_value = {
            "id": "chatcmpl-123",
            "choices": ["not_a_dict"],  # Should be list of dicts
        }

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])

        # Should raise either ResponseError or ProviderError for malformed structure
        with pytest.raises((ResponseError, ProviderError)) as exc_info:
            await provider.generate(request)

        # Verify it's an error (either type is acceptable)
        assert exc_info.value is not None

        await provider.close()

    @pytest.mark.asyncio
    async def test_request_with_metadata(self, monkeypatch):
        """Test that metadata is passed through to API."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {},
        }

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
            metadata={"top_p": 0.9, "presence_penalty": 0.5},
        )

        await provider.generate(request)

        call_args = provider._client.post.call_args
        payload = call_args[1]["json"]
        assert payload["top_p"] == 0.9
        assert payload["presence_penalty"] == 0.5

        await provider.close()

    @pytest.mark.asyncio
    async def test_base_url_trailing_slash_handling(self):
        """Test that trailing slashes in base_url are handled correctly."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1/",  # Note the trailing slash
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {},
        }

        provider._client.post = AsyncMock(return_value=mock_response)

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])
        await provider.generate(request)

        call_args = provider._client.post.call_args
        # Should not have double slashes
        assert call_args[0][0] == "https://api.example.com/v1/chat/completions"

        await provider.close()

    @pytest.mark.asyncio
    async def test_close_cleanup(self):
        """Test that close() properly cleans up resources."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4",
            timeout=30.0,
        )

        provider._client.aclose = AsyncMock()

        await provider.close()

        provider._client.aclose.assert_called_once()
