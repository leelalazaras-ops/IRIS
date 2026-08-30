"""
Focused tests for Phase 5: controlled multi-step AI-driven tool execution.
"""
import pytest
from unittest.mock import AsyncMock, patch
from iris.core.cli import IRISConversation
from iris.tools.orchestration import ToolCall
from iris.tools.base import ToolResult


class TestCLIPhase5:
    """Tests for Phase 5 multi-step tool execution in CLI."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()

    @pytest.mark.asyncio
    async def test_single_tool_call(self):
        """Test AI requests one tool call, then returns final response."""
        # Mock AI service
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            # First call: AI requests a tool call
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate_with_tools.side_effect = [
                # First response: AI wants to call a tool
                ("I'll calculate that for you.", [
                    ToolCall(id="call_1", tool_name="calculate", arguments={"expression": "2+2"})
                ]),
                # Second response: AI has tool result, returns final answer
                ("The result is 4.", [])
            ]

            # Initialize with mock provider
            self.conversation.ai_service = mock_ai_service
            # Start with empty history; handle_user_input will add the user message
            self.conversation.conversation_history = []

            # Process user input
            should_continue = await self.conversation.handle_user_input("What is 2+2?")

            # Verify
            assert should_continue is True
            # Check that generate_with_tools was called twice
            assert mock_ai_service.generate_with_tools.call_count == 2
            # Check conversation history: user + tool result + final assistant
            assert len(self.conversation.conversation_history) == 3
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "What is 2+2?"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[1]["name"] == "calculate"
            assert self.conversation.conversation_history[1]["content"] == "4"
            assert self.conversation.conversation_history[2]["role"] == "assistant"
            assert self.conversation.conversation_history[2]["content"] == "The result is 4."

    @pytest.mark.asyncio
    async def test_sequential_multiple_tool_calls(self):
        """Test AI requests multiple tool calls in sequence."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # Simulate: first tool call, second tool call, then final response
            mock_ai_service.generate_with_tools.side_effect = [
                ("Getting first value.", [
                    ToolCall(id="call_1", tool_name="get_current_time", arguments={})
                ]),
                ("Getting second value.", [
                    ToolCall(id="call_2", tool_name="get_current_time", arguments={})
                ]),
                ("Here are both times.", [])
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Get time twice")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 3
            # Verify tool calls were made: we should have two tool results in history
            # History: user, tool1 result, tool2 result, assistant final
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Get time twice"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Here are both times."

    @pytest.mark.asyncio
    async def test_tool_result_propagation(self):
        """Test that tool results are properly propagated to AI."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # First: AI calls calculate tool
            mock_ai_service.generate_with_tools.side_effect = [
                ("Calculating...", [
                    ToolCall(id="call_1", tool_name="calculate", arguments={"expression": "10*5"})
                ]),
                ("The answer is 50.", [])
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            await self.conversation.handle_user_input("What is 10*5?")

            # Check that the second call included the tool result
            second_call = mock_ai_service.generate_with_tools.call_args_list[1]
            messages = second_call[1]['messages']
            # Find the tool message
            tool_messages = [m for m in messages if m["role"] == "tool"]
            assert len(tool_messages) == 1
            assert tool_messages[0]["tool_call_id"] == "call_1"
            assert tool_messages[0]["name"] == "calculate"
            assert tool_messages[0]["content"] == "50"  # ToolResult content
            # Also check history after processing
            assert len(self.conversation.conversation_history) == 3
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "What is 10*5?"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["content"] == "50"
            assert self.conversation.conversation_history[2]["role"] == "assistant"
            assert self.conversation.conversation_history[2]["content"] == "The answer is 50."

    @pytest.mark.asyncio
    async def test_maximum_step_limit(self):
        """Test that execution stops at maximum tool calls."""
        # Set orchestrator to low limit for testing
        self.conversation.orchestrator.config.max_tool_calls = 2

        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # AI keeps requesting tool calls (more than limit)
            mock_ai_service.generate_with_tools.side_effect = [
                ("Step 1", [
                    ToolCall(id="call_1", tool_name="get_current_time", arguments={})
                ]),
                ("Step 2", [
                    ToolCall(id="call_2", tool_name="get_current_time", arguments={})
                ]),
                ("Step 3", [  # This should not be executed due to limit
                    ToolCall(id="call_3", tool_name="get_current_time", arguments={})
                ]),
                ("Final answer", [])
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Keep calling")

            assert should_continue is True
            # Should have called AI service 4 times: two tool calls, one exceeding limit (error), and final
            assert mock_ai_service.generate_with_tools.call_count == 4
            # Verify that the orchestrator's tool call count is exactly 2 (only the first two were executed)
            assert self.conversation.orchestrator._tool_call_count == 2
            # History: user, tool1 result, tool2 result, tool3 error, assistant final
            assert len(self.conversation.conversation_history) == 5
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Keep calling"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[3]["role"] == "tool"
            assert self.conversation.conversation_history[3]["tool_call_id"] == "call_3"
            assert "maximum tool calls exceeded" in self.conversation.conversation_history[3]["content"].lower()
            assert self.conversation.conversation_history[4]["role"] == "assistant"
            assert self.conversation.conversation_history[4]["content"] == "Final answer"

    @pytest.mark.asyncio
    async def test_tool_failure_continues(self):
        """Test that tool failure doesn't crash loop; AI can decide to continue."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # First tool call fails, second succeeds, then final
            mock_ai_service.generate_with_tools.side_effect = [
                ("Trying first tool...", [
                    ToolCall(id="call_1", tool_name="nonexistent_tool", arguments={})
                ]),
                ("Trying second tool...", [
                    ToolCall(id="call_2", tool_name="get_current_time", arguments={})
                ]),
                ("Done.", [])
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Try tools")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 3
            # Check that both tool calls were attempted (first fails, second succeeds)
            # History: user, tool1 error, tool2 result, assistant final
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Try tools"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["tool_call_id"] == "call_1"
            assert "not found" in self.conversation.conversation_history[1]["content"].lower()
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[2]["content"] != ""  # some time string
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Done."

    @pytest.mark.asyncio
    async def test_malformed_tool_call_handled(self):
        """Test that malformed tool calls (invalid arguments) are handled gracefully."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # AI calls tool with invalid arguments (wrong type)
            mock_ai_service.generate_with_tools.side_effect = [
                ("Calling tool...", [
                    ToolCall(id="call_1", tool_name="calculate", arguments={"expression": 123})  # Should be string
                ]),
                ("Got error, trying again...", [
                    ToolCall(id="call_2", tool_name="calculate", arguments={"expression": "5+5"})
                ]),
                ("Result is 10.", [])
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Calculate")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 3
            # First tool call should have failed validation
            # History: user, tool1 error, tool2 result, assistant final
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Calculate"
            assert self.conversation.conversation_history[1]["role"] == "tool"
            assert self.conversation.conversation_history[1]["tool_call_id"] == "call_1"
            assert "argument validation failed" in self.conversation.conversation_history[1]["content"].lower()
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[2]["content"] == "10"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Result is 10."

    @pytest.mark.asyncio
    async def test_repeated_tool_calls_loop_protection(self):
        """Test that repeated tool calls are limited by max_tool_calls."""
        self.conversation.orchestrator.config.max_tool_calls = 3

        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # AI repeatedly calls the same tool
            mock_ai_service.generate_with_tools.side_effect = [
                ("Calling tool...", [
                    ToolCall(id=f"call_{i}", tool_name="get_current_time", arguments={})
                ]) for i in range(1, 6)  # 5 tool calls
            ] + [("All done.", [])]  # Final response

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Call tool repeatedly")

            assert should_continue is True
            # Should have called AI service 6 times: 5 tool calls (3 succeed, 2 exceed limit and return error) + final
            assert mock_ai_service.generate_with_tools.call_count == 6
            # Should have executed exactly 3 tool calls (the limit)
            assert self.conversation.orchestrator._tool_call_count == 3
            # History: user, 3 tool results, 2 limit exceeded errors, assistant final
            assert len(self.conversation.conversation_history) == 7
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Call tool repeatedly"
            for i in range(1, 4):
                assert self.conversation.conversation_history[i]["role"] == "tool"
                assert self.conversation.conversation_history[i]["tool_call_id"] == f"call_{i}"
            # Next two should be limit exceeded errors
            assert self.conversation.conversation_history[4]["role"] == "tool"
            assert self.conversation.conversation_history[4]["tool_call_id"] == "call_4"
            assert "maximum tool calls exceeded" in self.conversation.conversation_history[4]["content"].lower()
            assert self.conversation.conversation_history[5]["role"] == "tool"
            assert self.conversation.conversation_history[5]["tool_call_id"] == "call_5"
            assert "maximum tool calls exceeded" in self.conversation.conversation_history[5]["content"].lower()
            assert self.conversation.conversation_history[6]["role"] == "assistant"
            assert self.conversation.conversation_history[6]["content"] == "All done."

    @pytest.mark.asyncio
    async def test_normal_conversation_without_tools(self):
        """Test normal conversation without tools works exactly as before."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # AI returns no tool calls, just a response
            mock_ai_service.generate_with_tools.return_value = (
                "Hello! How can I help you today?",
                []  # No tool calls
            )

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Hello")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 1
            # Conversation history should have user and assistant messages
            assert len(self.conversation.conversation_history) == 2
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Hello"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Hello! How can I help you today?"

    @pytest.mark.asyncio
    async def test_backward_compatibility(self):
        """Test that existing behavior without tools is unchanged."""
        # This is similar to normal conversation without tools, but we also
        # want to ensure that the orchestrator's state doesn't affect anything
        # when tools are not used.
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate_with_tools.return_value = (
                "Just a chat.",
                []
            )

            self.conversation.ai_service = mock_ai_service
            # Reset orchestrator call count to ensure it's clean
            self.conversation.orchestrator._tool_call_count = 0
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Test")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 1
            # Orchestrator tool call count should remain 0
            assert self.conversation.orchestrator._tool_call_count == 0
            # Conversation history should be correct
            assert len(self.conversation.conversation_history) == 2
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Test"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Just a chat."