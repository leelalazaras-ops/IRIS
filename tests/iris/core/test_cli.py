"""
Tests for the IRIS CLI conversation interface.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from io import StringIO

from iris.core.cli import IRISConversation, main
from iris.ai.service import AIService
from iris.ai.exceptions import AIError, ConfigurationError, ProviderError


class TestIRISConversation:
    """Tests for IRISConversation class."""

    @pytest.mark.asyncio
    async def test_initialization_success(self, monkeypatch):
        """Test successful initialization with mock provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        result = await conversation.initialize()

        assert result is True
        assert conversation.ai_service is not None
        assert isinstance(conversation.ai_service, AIService)
        assert conversation.conversation_history == []

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_initialization_config_error(self, monkeypatch, capsys):
        """Test initialization with missing configuration."""
        # Set up invalid config - missing required fields
        monkeypatch.setenv("IRIS_AI_PROVIDER", "openai-compatible")
        monkeypatch.delenv("IRIS_AI_BASE_URL", raising=False)
        monkeypatch.delenv("IRIS_AI_API_KEY", raising=False)

        conversation = IRISConversation()
        result = await conversation.initialize()

        assert result is False
        assert conversation.ai_service is None

        captured = capsys.readouterr()
        assert "Configuration error" in captured.out
        assert "IRIS_AI_BASE_URL" in captured.out

    @pytest.mark.asyncio
    async def test_handle_empty_input(self, monkeypatch):
        """Test that empty input is handled gracefully."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Empty string
        result = await conversation.handle_user_input("")
        assert result is True
        assert len(conversation.conversation_history) == 0

        # Whitespace only
        result = await conversation.handle_user_input("   \n\t  ")
        assert result is True
        assert len(conversation.conversation_history) == 0

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_handle_exit_command(self, monkeypatch):
        """Test exit command."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        result = await conversation.handle_user_input("exit")
        assert result is False

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_handle_quit_command(self, monkeypatch):
        """Test quit command."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        result = await conversation.handle_user_input("quit")
        assert result is False

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_handle_exit_case_insensitive(self, monkeypatch):
        """Test that exit/quit commands are case insensitive."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Test various cases
        assert await conversation.handle_user_input("EXIT") is False

        conversation2 = IRISConversation()
        await conversation2.initialize()
        assert await conversation2.handle_user_input("QuIt") is False

        await conversation.cleanup()
        await conversation2.cleanup()

    @pytest.mark.asyncio
    async def test_successful_message_exchange(self, monkeypatch, capsys):
        """Test successful user message and AI response."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        result = await conversation.handle_user_input("Hello, IRIS!")
        assert result is True

        # Check conversation history
        assert len(conversation.conversation_history) == 2
        assert conversation.conversation_history[0]["role"] == "user"
        assert conversation.conversation_history[0]["content"] == "Hello, IRIS!"
        assert conversation.conversation_history[1]["role"] == "assistant"
        assert len(conversation.conversation_history[1]["content"]) > 0

        # Check output
        captured = capsys.readouterr()
        assert "IRIS:" in captured.out

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_conversation_history_accumulates(self, monkeypatch):
        """Test that conversation history accumulates across messages."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # First message
        await conversation.handle_user_input("First message")
        assert len(conversation.conversation_history) == 2

        # Second message
        await conversation.handle_user_input("Second message")
        assert len(conversation.conversation_history) == 4

        # Verify order
        assert conversation.conversation_history[0]["content"] == "First message"
        assert conversation.conversation_history[1]["role"] == "assistant"
        assert conversation.conversation_history[2]["content"] == "Second message"
        assert conversation.conversation_history[3]["role"] == "assistant"

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_ai_error_handling(self, monkeypatch, capsys):
        """Test handling of AI errors during generation."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Disable tools to test standard conversation behavior (Phase 2)
        conversation.tools_enabled = False

        # Mock the generate method to raise an error
        async def mock_error(*args, **kwargs):
            raise ProviderError("Test provider error")

        conversation.ai_service.generate = mock_error

        result = await conversation.handle_user_input("This will fail")

        # Should continue despite error
        assert result is True

        # History should not contain the failed message
        assert len(conversation.conversation_history) == 0

        # Error should be displayed
        captured = capsys.readouterr()
        assert "AI Error" in captured.out
        assert "Test provider error" in captured.out

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_generic_error_handling(self, monkeypatch, capsys):
        """Test handling of generic errors."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Disable tools to test standard conversation behavior (Phase 2)
        conversation.tools_enabled = False

        # Mock the generate method to raise a generic error
        async def mock_error(*args, **kwargs):
            raise Exception("Generic error")

        conversation.ai_service.generate = mock_error

        result = await conversation.handle_user_input("This will fail")

        # Should continue despite error
        assert result is True

        # History should not contain the failed message
        assert len(conversation.conversation_history) == 0

        # Error should be displayed
        captured = capsys.readouterr()
        assert "Error:" in captured.out

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_sensitive_data_sanitization(self, monkeypatch, capsys):
        """Test that sensitive data is not exposed in error messages."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        conversation.tools_enabled = False
        await conversation.initialize()

        # Mock error with sensitive data
        async def mock_error_with_key(*args, **kwargs):
            raise Exception("Error: API key sk-1234567890 is invalid")

        conversation.ai_service.generate = mock_error_with_key

        await conversation.handle_user_input("Test")

        captured = capsys.readouterr()
        # Should not contain the actual error message with the key
        assert "sk-1234567890" not in captured.out
        assert "check your configuration" in captured.out.lower()

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_sensitive_token_sanitization(self, monkeypatch, capsys):
        """Test that tokens are sanitized from error messages."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        conversation.tools_enabled = False
        await conversation.initialize()

        # Mock error with token
        async def mock_error_with_token(*args, **kwargs):
            raise Exception("Invalid token: bearer_xyz123")

        conversation.ai_service.generate = mock_error_with_token

        await conversation.handle_user_input("Test")

        captured = capsys.readouterr()
        assert "bearer_xyz123" not in captured.out
        assert "check your configuration" in captured.out.lower()

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_closes_service(self, monkeypatch):
        """Test that cleanup properly closes the AI service."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        assert conversation.ai_service is not None
        service = conversation.ai_service

        # Mock close to verify it's called
        close_called = False

        async def mock_close():
            nonlocal close_called
            close_called = True

        service.close = mock_close

        await conversation.cleanup()
        assert close_called is True

    @pytest.mark.asyncio
    async def test_cleanup_with_no_service(self):
        """Test cleanup when service was never initialized."""
        conversation = IRISConversation()

        # Should not raise an error
        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_whitespace_trimming(self, monkeypatch):
        """Test that user input is properly trimmed."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        await conversation.handle_user_input("  Hello  \n")

        # Message should be trimmed in history
        assert conversation.conversation_history[0]["content"] == "Hello"

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_multiple_conversations_independent(self, monkeypatch):
        """Test that multiple conversation instances are independent."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conv1 = IRISConversation()
        conv2 = IRISConversation()

        await conv1.initialize()
        await conv2.initialize()

        await conv1.handle_user_input("Message to conv1")
        await conv2.handle_user_input("Message to conv2")

        # Histories should be independent
        assert len(conv1.conversation_history) == 2
        assert len(conv2.conversation_history) == 2
        assert conv1.conversation_history[0]["content"] == "Message to conv1"
        assert conv2.conversation_history[0]["content"] == "Message to conv2"

        await conv1.cleanup()
        await conv2.cleanup()


class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    @pytest.mark.asyncio
    async def test_conversation_with_mock_provider_end_to_end(self, monkeypatch):
        """Test complete conversation flow with mock provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Simulate a conversation
        messages = ["Hello", "What is AI?", "Thank you"]

        for msg in messages:
            result = await conversation.handle_user_input(msg)
            assert result is True

        # Should have 6 messages (3 user + 3 assistant)
        assert len(conversation.conversation_history) == 6

        # Verify alternating roles
        for i, msg in enumerate(conversation.conversation_history):
            if i % 2 == 0:
                assert msg["role"] == "user"
            else:
                assert msg["role"] == "assistant"

        await conversation.cleanup()

    @pytest.mark.asyncio
    async def test_error_recovery_continues_conversation(self, monkeypatch):
        """Test that conversation continues after an error."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        conversation.tools_enabled = False
        await conversation.initialize()

        # Successful message
        result = await conversation.handle_user_input("First message")
        assert result is True
        assert len(conversation.conversation_history) == 2

        # Inject an error
        original_generate = conversation.ai_service.generate

        async def failing_generate(*args, **kwargs):
            raise ProviderError("Temporary error")

        conversation.ai_service.generate = failing_generate

        # This should fail but continue
        result = await conversation.handle_user_input("This fails")
        assert result is True
        assert len(conversation.conversation_history) == 2  # No change

        # Restore working generate
        conversation.ai_service.generate = original_generate

        # Successful message again
        result = await conversation.handle_user_input("Second message")
        assert result is True
        assert len(conversation.conversation_history) == 4

        await conversation.cleanup()
