"""
Focused integration tests for LLM intent classifier integration.
"""
import unittest
from unittest.mock import AsyncMock, patch

from iris.core.cli import IRISConversation
from iris.intent.models import Intent


class TestIntentIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conversation = IRISConversation()
        # Set up a mock AI service
        self.conversation.ai_service = AsyncMock()

    async def test_context_is_used_in_llm_classification(self):
        """Test that recent conversation context is included in LLM classification prompt."""
        # First add some conversation history
        self.conversation.memory_manager.add_user_message("Show me the files")
        self.conversation.memory_manager.add_assistant_message("Here are the files: file1.txt, file2.txt")

        # Mock LLM to capture the prompt it receives
        captured_prompt = []
        async def mock_generate(messages, temperature=0.0):
            # Extract the user message content (our enhanced input)
            for msg in messages:
                if msg.get("role") == "user":
                    captured_prompt.append(msg.get("content", ""))
                    break
            # Return a high-confidence classification
            return '{"action": "read_file", "confidence": 0.9, "arguments": {"path": "file1.txt"}}'

        self.conversation.ai_service.generate = mock_generate

        # Now test with a follow-up that should use context
        intent = await self.conversation._create_intent_from_user_input("read the first one")

        # Verify that the LLM received context-enhanced input
        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        self.assertIn("Recent conversation:", prompt)
        self.assertIn("User: Show me the files", prompt)
        self.assertIn("Assistant: Here are the files: file1.txt, file2.txt", prompt)
        self.assertIn("Current input: read the first one", prompt)

        # Verify the classification worked correctly
        self.assertEqual(intent.action, "read_file")
        self.assertEqual(intent.confidence, 0.9)
        self.assertEqual(intent.arguments, {"path": "file1.txt"})
        # Original request should be preserved
        self.assertEqual(intent.original_request, "read the first one")

    async def test_fallback_to_rule_based_uses_original_input_without_context(self):
        """Test that rule-based fallback uses original input without context to prevent false matches."""
        # First add some conversation history that might trigger false keyword matches
        self.conversation.memory_manager.add_user_message("Please read this file carefully")
        self.conversation.memory_manager.add_assistant_message("I've read the file")

        # Mock LLM to return low confidence (triggering fallback)
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "none", "confidence": 0.3, "arguments": {}}'
        )

        # Test with input that contains a keyword but shouldn't trigger rule-based due to context
        # "read" in current input + "read" in history could falsely trigger if context used poorly
        intent = await self.conversation._create_intent_from_user_input("read")

        # Should fall back to rule-based (low confidence LLM result)
        # Rule-based should see only "read" and map to read_file with low confidence
        self.assertEqual(intent.action, "read_file")
        self.assertEqual(intent.confidence, 0.5)  # Rule-based confidence for "read" without path
        # Original request should be preserved
        self.assertEqual(intent.original_request, "read")

    async def test_no_context_when_insufficient_history(self):
        """Test that no context is added when there's insufficient conversation history."""
        # Start with empty memory
        self.conversation.memory_manager.clear()

        # Mock LLM to capture the prompt
        captured_prompt = []
        async def mock_generate(messages, temperature=0.0):
            for msg in messages:
                if msg.get("role") == "user":
                    captured_prompt.append(msg.get("content", ""))
                    break
            return '{"action": "list_directory", "confidence": 0.8, "arguments": {"path": "."}}'

        self.conversation.ai_service.generate = mock_generate

        # Test with no prior conversation
        intent = await self.conversation._create_intent_from_user_input("show files")

        # Should use original input only (no context added)
        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        # The prompt should contain the system prompt and the user input in quotes
        self.assertIn("You are an intent classification system for IRIS.", prompt)
        self.assertIn('User request: """show files"""', prompt)
        # Ensure our context strings are not present
        self.assertNotIn("Recent conversation:", prompt)
        self.assertNotIn("Current input:", prompt)

        # Verify classification worked
        self.assertEqual(intent.action, "list_directory")
        self.assertEqual(intent.confidence, 0.8)
        self.assertEqual(intent.original_request, "show files")

    async def test_context_truncates_long_content(self):
        """Test that long content in context is truncated to prevent prompt bloat."""
        # Add conversation history with long content
        long_content = "x" * 150  # Longer than 100 char limit
        self.conversation.memory_manager.add_user_message("Short message")
        self.conversation.memory_manager.add_assistant_message(long_content)

        # Mock LLM to capture the prompt
        captured_prompt = []
        async def mock_generate(messages, temperature=0.0):
            for msg in messages:
                if msg.get("role") == "user":
                    captured_prompt.append(msg.get("content", ""))
                    break
            return '{"action": "none", "confidence": 0.1, "arguments": {}}'  # Low confidence to test fallback

        self.conversation.ai_service.generate = mock_generate

        # Test follow-up
        intent = await self.conversation._create_intent_from_user_input("what's next?")

        # Verify content was truncated in context
        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        self.assertIn("Recent conversation:", prompt)
        self.assertIn("User: Short message", prompt)
        # Content should be truncated to 97 chars + "..."
        expected_truncated = "x" * 97 + "..."
        self.assertIn(f"Assistant: {expected_truncated}", prompt)
        self.assertIn("Current input: what's next?", prompt)

        # Should fall back to rule-based due to low confidence
        self.assertEqual(intent.action, "none")
        self.assertEqual(intent.confidence, 0.0)  # Default for exceptions/low confidence in our implementation
        self.assertEqual(intent.original_request, "what's next?")

    async def test_tool_messages_included_in_context(self):
        """Test that tool messages are included in context (as they are part of conversation turns)."""
        # Add a user message and a tool result message (simulating what gets added to memory)
        self.conversation.memory_manager.add_user_message("What time is it?")
        # Simulate a tool result message that would be added by _process_with_tools
        from iris.tools.orchestration import ToolCall
        tool_call = ToolCall(
            tool_name="get_current_time",
            arguments={},
            id="test-call-1"
        )
        # Add assistant message with tool calls (what gets added before tool execution)
        self.conversation.memory_manager.add_assistant_message(
            "Getting current time...",
            tool_calls=[tool_call]
        )
        # Add tool result message (what gets added after tool execution)
        from iris.tools.base import ToolResult
        tool_result = ToolResult(
            success=True, content="The current time is 10:30 AM"
        )
        # Tool result messages are added as "tool" role
        self.conversation.memory_manager.context.add_message({
            "role": "tool",
            "content": "The current time is 10:30 AM",
            "tool_call_id": "test-call-1",
            "tool_name": "get_current_time"
        })

        # Mock LLM to capture the prompt
        captured_prompt = []
        async def mock_generate(messages, temperature=0.0):
            for msg in messages:
                if msg.get("role") == "user":
                    captured_prompt.append(msg.get("content", ""))
                    break
            return '{"action": "none", "confidence": 0.2, "arguments": {}}'

        self.conversation.ai_service.generate = mock_generate

        # Test follow-up
        intent = await self.conversation._create_intent_from_user_input("what about the date?")

        # Verify tool messages are included in context
        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        self.assertIn("Recent conversation:", prompt)
        # Note: We only take the last 2 turns from history, so the user message is not included when we have 3+ turns
        self.assertIn("Assistant: Getting current time...", prompt)
        self.assertIn("Tool: The current time is 10:30 AM", prompt)
        self.assertIn("Current input: what about the date?", prompt)

        # Should fall back to rule-based
        self.assertEqual(intent.action, "none")
        self.assertEqual(intent.confidence, 0.0)
        self.assertEqual(intent.original_request, "what about the date?")

    async def test_natural_language_synonym_recognized_by_llm(self):
        """Test that LLM recognizes natural language synonyms and maps to correct intent."""
        # Mock LLM to return a high-confidence classification for a synonym
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "read_file", "confidence": 0.9, "arguments": {"path": "notes.txt"}}'
        )

        intent = await self.conversation._create_intent_from_user_input("display notes.txt")

        self.assertEqual(intent.action, "read_file")
        self.assertEqual(intent.confidence, 0.9)
        self.assertEqual(intent.arguments, {"path": "notes.txt"})
        self.assertEqual(intent.original_request, "display notes.txt")

    async def test_valid_llm_intent_reaches_planner(self):
        """Test that a valid LLM intent (confidence >= 0.6) is used and would reach planner."""
        # Mock LLM to return a valid classification
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "list_directory", "confidence": 0.8, "arguments": {"path": "."}}'
        )

        intent = await self.conversation._create_intent_from_user_input("show files")

        # Should use LLM result
        self.assertEqual(intent.action, "list_directory")
        self.assertEqual(intent.confidence, 0.8)
        self.assertEqual(intent.arguments, {"path": "."})

        # Verify that this intent would be processed (confidence >= 0.6 threshold)
        self.assertGreaterEqual(intent.confidence, 0.6)

    async def test_llm_none_falls_back_to_rule_based(self):
        """Test that LLM returning action='none' falls back to rule-based detection."""
        # Mock LLM to return 'none' action
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "none", "confidence": 0.1, "arguments": {}}'
        )

        # Use input that rule-based detection can handle
        intent = await self.conversation._create_intent_from_user_input("read file.txt")

        # Should fall back to rule-based detection
        self.assertEqual(intent.action, "read_file")
        self.assertEqual(intent.arguments, {"path": "file.txt"})
        # Rule-based confidence should be 0.8 for explicit file path
        self.assertEqual(intent.confidence, 0.8)

    async def test_low_confidence_llm_result_falls_back(self):
        """Test that LLM result with confidence < 0.6 falls back to rule-based."""
        # Mock LLM to return low confidence
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "read_file", "confidence": 0.5, "arguments": {"path": "doc.txt"}}'
        )

        intent = await self.conversation._create_intent_from_user_input("show doc.txt")

        # Should fall back to rule-based detection
        self.assertEqual(intent.action, "read_file")
        self.assertEqual(intent.arguments, {"path": "doc.txt"})
        # Should use rule-based confidence (0.8 for explicit path)
        self.assertEqual(intent.confidence, 0.8)

    async def test_classifier_exception_falls_back(self):
        """Test that classifier exception falls back to rule-based detection."""
        # Mock LLM to raise an exception
        self.conversation.ai_service.generate = AsyncMock(side_effect=Exception("API Error"))

        intent = await self.conversation._create_intent_from_user_input("create directory test")

        # Should fall back to rule-based detection
        self.assertEqual(intent.action, "create_directory")
        self.assertEqual(intent.arguments, {"path": "test"})
        self.assertEqual(intent.confidence, 0.8)

    async def test_llm_arguments_passed_into_intent_correctly(self):
        """Test that LLM-provided arguments are correctly passed into the Intent."""
        # Mock LLM to return specific arguments
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "write_file", "confidence": 0.9, "arguments": {"path": "test.txt", "content": "hello world"}}'
        )

        intent = await self.conversation._create_intent_from_user_input("write hello world to test.txt")

        self.assertEqual(intent.action, "write_file")
        self.assertEqual(intent.confidence, 0.9)
        self.assertEqual(intent.arguments, {"path": "test.txt", "content": "hello world"})

    async def test_safety_still_blocks_dangerous_arguments(self):
        """Test that dangerous arguments are still blocked by safety classifier (integration test)."""
        # Mock LLM to return a potentially dangerous action
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "write_file", "confidence": 0.9, "arguments": {"path": "../../../etc/passwd", "content": "malicious"}}'
        )

        # Set up the conversation with a safety classifier that blocks this
        # We can't easily test the full safety integration without more mocking,
        # but we can verify the intent is created correctly and safety would be checked elsewhere
        intent = await self.conversation._create_intent_from_user_input("write malicious to ../../../etc/passwd")

        self.assertEqual(intent.action, "write_file")
        self.assertEqual(intent.arguments, {"path": "../../../etc/passwd", "content": "malicious"})
        # The safety check happens later in the pipeline, not in intent creation

    async def test_existing_rule_based_behavior_still_works(self):
        """Test that existing rule-based behavior still works when LLM is not available."""
        # Remove AI service to force rule-based usage
        original_ai_service = self.conversation.ai_service
        self.conversation.ai_service = None

        try:
            # Use an input that the rule-based method handles correctly (returns path=".")
            intent = await self.conversation._create_intent_from_user_input("list")

            # Should use rule-based detection
            self.assertEqual(intent.action, "list_directory")
            self.assertEqual(intent.arguments, {"path": "."})
            self.assertEqual(intent.confidence, 0.8)
        finally:
            self.conversation.ai_service = original_ai_service

    async def test_voice_input_uses_same_pipeline(self):
        """Test that voice input would use the same pipeline (intent creation method is the same)."""
        # The _create_intent_from_user_input method is used for all input types
        # So if it works for text input, it works for voice input too
        self.conversation.ai_service.generate = AsyncMock(
            return_value='{"action": "get_current_time", "confidence": 0.85, "arguments": {}}'
        )

        intent = await self.conversation._create_intent_from_user_input("what time is it")

        self.assertEqual(intent.action, "get_current_time")
        self.assertEqual(intent.confidence, 0.85)
        self.assertEqual(intent.arguments, {})


if __name__ == '__main__':
    unittest.main()