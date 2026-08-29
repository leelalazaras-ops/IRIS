"""
Tests for AI provider interface and data models.
"""

import pytest

from iris.ai.provider import AIRequest, AIResponse, AIProvider


class TestAIRequest:
    """Tests for AIRequest dataclass."""

    def test_valid_request(self):
        """Test creating a valid request."""
        request = AIRequest(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.8,
            max_tokens=100,
        )

        assert request.messages == [{"role": "user", "content": "Hello"}]
        assert request.temperature == 0.8
        assert request.max_tokens == 100
        assert request.metadata == {}

    def test_request_with_defaults(self):
        """Test request with default values."""
        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
        )

        assert request.temperature == 0.7
        assert request.max_tokens is None
        assert request.metadata == {}

    def test_request_with_metadata(self):
        """Test request with custom metadata."""
        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
            metadata={"custom_param": "value"},
        )

        assert request.metadata == {"custom_param": "value"}

    def test_empty_messages_error(self):
        """Test that empty messages raise an error."""
        with pytest.raises(ValueError) as exc_info:
            AIRequest(messages=[])

        assert "messages cannot be empty" in str(exc_info.value)

    def test_temperature_too_low(self):
        """Test that temperature below 0.0 raises an error."""
        with pytest.raises(ValueError) as exc_info:
            AIRequest(
                messages=[{"role": "user", "content": "Test"}],
                temperature=-0.1,
            )

        assert "temperature must be between 0.0 and 2.0" in str(exc_info.value)

    def test_temperature_too_high(self):
        """Test that temperature above 2.0 raises an error."""
        with pytest.raises(ValueError) as exc_info:
            AIRequest(
                messages=[{"role": "user", "content": "Test"}],
                temperature=2.1,
            )

        assert "temperature must be between 0.0 and 2.0" in str(exc_info.value)

    def test_negative_max_tokens(self):
        """Test that negative max_tokens raises an error."""
        with pytest.raises(ValueError) as exc_info:
            AIRequest(
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=-1,
            )

        assert "max_tokens must be positive" in str(exc_info.value)

    def test_zero_max_tokens(self):
        """Test that zero max_tokens raises an error."""
        with pytest.raises(ValueError) as exc_info:
            AIRequest(
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=0,
            )

        assert "max_tokens must be positive" in str(exc_info.value)


class TestAIResponse:
    """Tests for AIResponse dataclass."""

    def test_valid_response(self):
        """Test creating a valid response."""
        response = AIResponse(
            content="Hello, world!",
            model="gpt-4",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"finish_reason": "stop"},
        )

        assert response.content == "Hello, world!"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 15
        assert response.metadata["finish_reason"] == "stop"

    def test_response_with_defaults(self):
        """Test response with default values."""
        response = AIResponse(
            content="Test response",
            model="test-model",
        )

        assert response.usage == {}
        assert response.metadata == {}


class TestAIProvider:
    """Tests for AIProvider abstract base class."""

    def test_cannot_instantiate_abstract_provider(self):
        """Test that AIProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AIProvider()

    def test_subclass_must_implement_generate(self):
        """Test that subclasses must implement generate method."""

        class IncompleteProvider(AIProvider):
            async def close(self):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_subclass_must_implement_close(self):
        """Test that subclasses must implement close method."""

        class IncompleteProvider(AIProvider):
            async def generate(self, request):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()
