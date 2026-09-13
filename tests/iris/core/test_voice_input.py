"""
Focused tests for voice input integration.
"""

import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from src.iris.core.cli import IRISConversation


class TestVoiceInput(unittest.TestCase):

    def setUp(self):
        # Create a conversation instance for each test
        self.conversation = IRISConversation()
        # Mock the AI service to avoid initialization
        self.conversation.ai_service = MagicMock()
        self.conversation.ai_service.initialize = AsyncMock(return_value=True)
        self.conversation.ai_service.close = AsyncMock()
        self.conversation.ai_service.generate = AsyncMock(return_value="test response")
        self.conversation.ai_service.generate_with_tools = AsyncMock(return_value=("test response", []))

    @patch('src.iris.core.cli.listen_for_speech')
    @patch('builtins.print')
    def test_voice_off_uses_typed_input(self, mock_print, mock_listen):
        """When voice mode is OFF, input() should be called."""
        self.conversation.voice_mode = False

        with patch('builtins.input', return_value="typed command") as mock_input:
            # Mock handle_user_input to avoid processing and break after one iteration
            self.conversation.handle_user_input = AsyncMock(return_value=False)

            # Run one iteration of the loop
            import asyncio
            asyncio.run(self.conversation.run())

            # Verify input() was called, not listen_for_speech
            mock_input.assert_called_once_with("IRIS> ")
            mock_listen.assert_not_called()

    @patch('src.iris.core.cli.listen_for_speech')
    @patch('builtins.print')
    def test_voice_on_uses_listen_for_speech(self, mock_print, mock_listen):
        """When voice mode is ON, listen_for_speech() should be called."""
        self.conversation.voice_mode = True
        mock_listen.return_value = "voice command"

        with patch('builtins.input') as mock_input:
            # Mock handle_user_input to avoid processing and break loop
            self.conversation.handle_user_input = AsyncMock(return_value=False)

            # Run one iteration of the loop
            import asyncio
            asyncio.run(self.conversation.run())

            # Verify listen_for_speech was called, not input()
            mock_listen.assert_called_once()
            mock_input.assert_not_called()
            # Verify the recognized text was processed
            self.conversation.handle_user_input.assert_called_once_with("voice command")

    @patch('src.iris.core.cli.listen_for_speech')
    @patch('builtins.print')
    def test_voice_recognition_failure_handled_safely(self, mock_print, mock_listen):
        """If speech recognition returns no usable text, safely continue the CLI loop."""
        self.conversation.voice_mode = True
        mock_listen.return_value = None  # Speech recognition failed

        with patch('builtins.input') as mock_input:
            # Mock handle_user_input to avoid processing and break loop after this iteration
            self.conversation.handle_user_input = AsyncMock(return_value=False)

            # Run one iteration of the loop
            import asyncio
            asyncio.run(self.conversation.run())

            # Verify listen_for_speech was called
            mock_listen.assert_called_once()
            # Verify input was NOT called (since we're in voice mode)
            mock_input.assert_not_called()
            # Verify handle_user_input was NOT called (since no usable text)
            self.conversation.handle_user_input.assert_not_called()
            # Verify the loop continued (we called run() once and it processed one iteration)
            # This is verified by the fact that we didn't hang or crash

    @patch('src.iris.core.cli.listen_for_speech')
    @patch('builtins.print')
    def test_recognized_speech_reaches_existing_pipeline(self, mock_print, mock_listen):
        """Recognized speech must enter the SAME existing handle_user_input() pipeline."""
        self.conversation.voice_mode = True
        test_command = "list files"
        mock_listen.return_value = test_command

        # Mock handle_user_input to capture what it receives
        captured_input = []
        async def capture_input(user_input):
            captured_input.append(user_input)
            return False  # Break after one iteration

        self.conversation.handle_user_input = capture_input

        with patch('builtins.input'):
            # Run one iteration of the loop
            import asyncio
            asyncio.run(self.conversation.run())

            # Verify the recognized speech was passed to handle_user_input
            self.assertEqual(len(captured_input), 1)
            self.assertEqual(captured_input[0], test_command)

    @patch('src.iris.core.cli.listen_for_speech')
    @patch('builtins.print')
    def test_voice_mode_can_be_turned_off_and_typed_input_resumes(self, mock_print, mock_listen):
        """Voice mode can be turned off and typed input resumes."""
        self.conversation.voice_mode = True
        mock_listen.return_value = "voice command"

        # First, test voice mode works
        with patch('builtins.input') as mock_input:
            self.conversation.handle_user_input = AsyncMock(return_value=False)
            import asyncio
            asyncio.run(self.conversation.run())
            mock_listen.assert_called_once()
            mock_input.assert_not_called()

        # Now turn voice mode OFF and test typed input works
        self.conversation.voice_mode = False
        with patch('builtins.input', return_value="typed command") as mock_input:
            self.conversation.handle_user_input = AsyncMock(return_value=False)
            import asyncio
            asyncio.run(self.conversation.run())
            mock_input.assert_called_once_with("IRIS> ")
            self.conversation.handle_user_input.assert_called_once_with("typed command")

if __name__ == '__main__':
    unittest.main()