"""
Focused tests for Text-to-Speech integration in IRIS CLI.
"""
import unittest
from unittest.mock import patch, AsyncMock
import asyncio

from iris.core.cli import IRISConversation
from iris.ai.service import AIService
from iris.ai.exceptions import ProviderError


class TestTTSIntegration(unittest.TestCase):

    def setUp(self):
        """Set up a conversation instance for each test."""
        self.conversation = IRISConversation()
        # We'll initialize in each test as needed

    def tearDown(self):
        """Clean up after each test."""
        # Clean up if conversation was initialized
        if hasattr(self.conversation, 'ai_service') and self.conversation.ai_service:
            asyncio.run(self.conversation.cleanup())

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_voice_off_does_not_call_speak_text(self, mock_print, mock_speak_text):
        """When voice mode is OFF, speak_text must NOT be called."""
        self.conversation.voice_mode = False
        # Initialize conversation
        await self.conversation.initialize()
        # Mock the AI service to return a fixed response
        async def mock_generate(*args, **kwargs):
            return "Test response"
        self.conversation.ai_service.generate = mock_generate

        await self.conversation.handle_user_input("Hello")

        # speak_text should not be called
        mock_speak_text.assert_not_called()
        # But the response should still be printed
        mock_print.assert_called()

        await self.conversation.cleanup()

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_voice_on_calls_speak_text(self, mock_print, mock_speak_text):
        """When voice mode is ON, speak_text should be called with the response."""
        self.conversation.voice_mode = True
        # Initialize conversation
        await self.conversation.initialize()
        # Mock the AI service to return a fixed response
        async def mock_generate(*args, **kwargs):
            return "Test response"
        self.conversation.ai_service.generate = mock_generate

        await self.conversation.handle_user_input("Hello")

        # speak_text should be called once with the response
        mock_speak_text.assert_called_once_with("Test response")
        # The response should still be printed
        mock_print.assert_called()

        await self.conversation.cleanup()

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_terminal_response_still_printed(self, mock_print, mock_speak_text):
        """The terminal response must still be printed when voice mode is ON."""
        self.conversation.voice_mode = True
        # Initialize conversation
        await self.conversation.initialize()
        self.conversation.ai_service.generate = AsyncMock(return_value="Test response")

        await self.conversation.handle_user_input("Hello")

        # Check that print was called
        mock_print.assert_called()

        await self.conversation.cleanup()

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_tts_failure_does_not_crash(self, mock_print, mock_speak_text):
        """TTS failure must be handled safely: IRIS must not crash and text response still available."""
        self.conversation.voice_mode = True
        # Initialize conversation
        await self.conversation.initialize()
        # Make speak_text raise an exception
        mock_speak_text.side_effect = Exception("TTS failure")
        # Mock the AI service to return a fixed response
        async def mock_generate(*args, **kwargs):
            return "Test response"
        self.conversation.ai_service.generate = mock_generate

        # This should not raise an exception
        await self.conversation.handle_user_input("Hello")

        # Even though TTS failed, the response should still be printed
        mock_print.assert_called()
        # speak_text was called (and failed)
        mock_speak_text.assert_called_once_with("Test response")

        await self.conversation.cleanup()

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_safety_confirmation_responses_follow_pipeline(self, mock_print, mock_speak_text):
        """Safety/confirmation responses should still follow the existing pipeline and be spoken if voice ON."""
        self.conversation.voice_mode = True
        # Initialize conversation
        await self.conversation.initialize()
        # Mock the AI service to return a confirmation-like response
        async def mock_generate(*args, **kwargs):
            return "⚠️  Action requires confirmation: test\nType '/confirm' to proceed or '/cancel' to abort."
        self.conversation.ai_service.generate = mock_generate

        await self.conversation.handle_user_input("do something dangerous")

        # The confirmation prompt should be spoken
        mock_speak_text.assert_called_once_with("⚠️  Action requires confirmation: test\nType '/confirm' to proceed or '/cancel' to abort.")
        # And printed
        mock_print.assert_called()

        await self.conversation.cleanup()

    @patch('iris.core.cli.speak_text')
    @patch('iris.core.cli.print')
    async def test_voice_can_be_turned_off_and_on(self, mock_print, mock_speak_text):
        """Voice can be turned off and TTS stops being turned; turning it back on resumes TTS."""
        # Initialize conversation
        await self.conversation.initialize()
        # Start with voice off
        self.conversation.voice_mode = False
        async def mock_generate(*args, **kwargs):
            return "First response"
        self.conversation.ai_service.generate = mock_generate

        await self.conversation.handle_user_input("Hello")
        mock_speak_text.assert_not_called()

        # Turn voice on
        self.conversation.voice_mode = True
        async def mock_generate2(*args, **kwargs):
            return "Second response"
        self.conversation.ai_service.generate = mock_generate2

        await self.conversation.handle_user_input("Hello")
        mock_speak_text.assert_called_once_with("Second response")

        # Turn voice off again
        self.conversation.voice_mode = False
        async def mock_generate3(*args, **kwargs):
            return "Third response"
        self.conversation.ai_service.generate = mock_generate3

        await self.conversation.handle_user_input("Hello")
        # speak_text should have been called only once (for the second response)
        self.assertEqual(mock_speak_text.call_count, 1)

        await self.conversation.cleanup()


if __name__ == '__main__':
    unittest.main()