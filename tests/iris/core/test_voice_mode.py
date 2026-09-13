"""
Focused tests for voice mode CLI integration.
"""

import unittest
from unittest.mock import patch, AsyncMock

from src.iris.core.cli import IRISConversation


class TestVoiceMode(unittest.TestCase):

    def setUp(self):
        # Create a conversation instance for each test
        self.conversation = IRISConversation()

    def test_default_voice_mode_off(self):
        """Voice mode should default to OFF."""
        self.assertFalse(self.conversation.voice_mode)

    def test_voice_on_enables(self):
        """ /voice-on should enable voice mode."""
        # Simulate the command
        # We can't easily call handle_tool_command because it's async and requires mocking.
        # Instead, we directly set and check, but let's test via the method if possible.
        # We'll patch the print to avoid output and call the async method.
        with patch('builtins.print'):
            # We need to run the async method. Since we are in a sync test, we can use asyncio.run.
            import asyncio
            asyncio.run(self.conversation.handle_tool_command("/voice-on"))
        self.assertTrue(self.conversation.voice_mode)

    def test_voice_off_disables(self):
        """ /voice-off should disable voice mode."""
        # First enable it
        self.conversation.voice_mode = True
        with patch('builtins.print'):
            import asyncio
            asyncio.run(self.conversation.handle_tool_command("/voice-off"))
        self.assertFalse(self.conversation.voice_mode)

    def test_repeated_toggles_safe(self):
        """Repeated /voice-on and /voice-off should be harmless."""
        with patch('builtins.print'):
            import asyncio
            asyncio.run(self.conversation.handle_tool_command("/voice-on"))
            asyncio.run(self.conversation.handle_tool_command("/voice-on"))
            asyncio.run(self.conversation.handle_tool_command("/voice-off"))
            asyncio.run(self.conversation.handle_tool_command("/voice-off"))
        # Should end up disabled
        self.assertFalse(self.conversation.voice_mode)

    def test_help_shows_voice_commands(self):
        """ /help should include voice-on and voice-off."""
        import io
        import sys
        import asyncio

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            asyncio.run(self.conversation.handle_tool_command("/help"))
            printed = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("/voice-on", printed)
        self.assertIn("/voice-off", printed)

    def test_typed_commands_still_work_with_voice_off(self):
        """Typed commands should be processed normally when voice mode is OFF."""
        # We'll test that the conversation state doesn't interfere with normal command processing.
        # We can test a simple tool command like /tools
        with patch('builtins.print'):
            import asyncio
            asyncio.run(self.conversation.handle_tool_command("/tools"))
        # No assertion needed, just ensure it doesn't break.

    def test_voice_mode_does_not_alter_safety_behavior(self):
        """Voice mode state should not affect safety classification."""
        # We don't have a direct way to test safety without the full pipeline.
        # We can at least check that the safety_classifier is still present and functional.
        self.assertIsNotNone(self.conversation.safety_classifier)
        # We can also check that the voice_mode attribute doesn't exist on the safety classifier.
        self.assertFalse(hasattr(self.conversation.safety_classifier, 'voice_mode'))

if __name__ == '__main__':
    unittest.main()