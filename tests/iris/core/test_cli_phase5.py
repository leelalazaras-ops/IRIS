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
            # Check conversation history: user + assistant(with tool_calls) + tool result + final assistant
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "What is 2+2?"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "I'll calculate that for you."
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[1]["tool_calls"][0]["id"] == "call_1"
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[2]["name"] == "calculate"
            assert self.conversation.conversation_history[2]["content"] == "4"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "The result is 4."

    @pytest.mark.asyncio
    async def test_sequential_multiple_tool_calls(self):
        """Test AI requests multiple tool calls in sequence."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate = AsyncMock()
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
            # Mock the fallback generate call
            mock_ai_service.generate.return_value = "Here are both times."

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Get time twice")

            assert should_continue is True
            assert mock_ai_service.generate_with_tools.call_count == 2
            assert mock_ai_service.generate.call_count == 1
            # Verify tool calls were made: we should have two tool results in history
            # History: user, assistant1(tool_calls), tool1 result, assistant2(tool_calls), tool2 result, assistant final
            # Actually, with repetition detection, second identical call should be blocked
            # So: user, assistant1(tool_calls), tool1 result, assistant final (from fallback)
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Get time twice"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[1]["tool_calls"][0]["function"]["name"] == "get_current_time"
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
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
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "What is 10*5?"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Calculating..."
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["content"] == "50"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "The answer is 50."

    @pytest.mark.asyncio
    async def test_maximum_step_limit(self):
        """Test that execution stops at maximum tool calls."""
        # Set orchestrator to low limit for testing
        self.conversation.orchestrator.config.max_tool_calls = 2

        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate = AsyncMock()
            # AI requests DIFFERENT tool calls each round (so repetition
            # detection doesn't stop it) until the orchestrator limit is hit.
            mock_ai_service.generate_with_tools.side_effect = [
                ("Step 1", [
                    ToolCall(id="call_1", tool_name="calculate", arguments={"expression": "1+1"})
                ]),
                ("Step 2", [
                    ToolCall(id="call_2", tool_name="calculate", arguments={"expression": "2+2"})
                ]),
                ("Step 3", [  # Exceeds the orchestrator limit of 2
                    ToolCall(id="call_3", tool_name="calculate", arguments={"expression": "3+3"})
                ]),
                ("Final answer", [])  # Fallback response
            ]
            # Mock the fallback generate call
            mock_ai_service.generate.return_value = "Final answer"

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Keep calling")

            assert should_continue is True
            # Four AI iterations: three tool requests, then the final (no-tool) response
            assert mock_ai_service.generate_with_tools.call_count == 4
            assert mock_ai_service.generate.call_count == 0
            # Verify that the orchestrator's tool call count is exactly 2 (limit reached)
            assert self.conversation.orchestrator._tool_call_count == 2
            # History: user, asst1(tc), tool1, asst2(tc), tool2, asst3(tc), tool3(limit error), assistant final
            assert len(self.conversation.conversation_history) == 8
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Keep calling"
            assert self.conversation.conversation_history[7]["role"] == "assistant"
            assert self.conversation.conversation_history[7]["content"] == "Final answer"
            # The third tool result should be the limit-exceeded error
            tool_messages = [m for m in self.conversation.conversation_history if m["role"] == "tool"]
            assert len(tool_messages) == 3
            assert "Maximum tool calls exceeded" in tool_messages[2]["content"]

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
            # History: user, assistant1(tool_calls), tool1 error, assistant2(tool_calls), tool2 result, assistant final
            assert len(self.conversation.conversation_history) == 6
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Try tools"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Trying first tool..."
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert "not found" in self.conversation.conversation_history[2]["content"].lower()
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Trying second tool..."
            assert "tool_calls" in self.conversation.conversation_history[3]
            assert self.conversation.conversation_history[4]["role"] == "tool"
            assert self.conversation.conversation_history[4]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[4]["content"] != ""  # some time string
            assert self.conversation.conversation_history[5]["role"] == "assistant"
            assert self.conversation.conversation_history[5]["content"] == "Done."

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
            # History: user, assistant1(tool_calls), tool1 error, assistant2(tool_calls), tool2 result, assistant final
            assert len(self.conversation.conversation_history) == 6
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Calculate"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Calling tool..."
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert "argument validation failed" in self.conversation.conversation_history[2]["content"].lower()
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Got error, trying again..."
            assert "tool_calls" in self.conversation.conversation_history[3]
            assert self.conversation.conversation_history[4]["role"] == "tool"
            assert self.conversation.conversation_history[4]["tool_call_id"] == "call_2"
            assert self.conversation.conversation_history[4]["content"] == "10"
            assert self.conversation.conversation_history[5]["role"] == "assistant"
            assert self.conversation.conversation_history[5]["content"] == "Result is 10."

    @pytest.mark.asyncio
    async def test_repeated_tool_calls_loop_protection(self):
        """Test that repeated tool calls are limited by repetition detection."""
        self.conversation.orchestrator.config.max_tool_calls = 3

        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate = AsyncMock()
            # AI repeatedly calls the same tool - this should trigger repetition detection
            mock_ai_service.generate_with_tools.side_effect = [
                ("Calling tool 1...", [
                    ToolCall(id="call_1", tool_name="get_current_time", arguments={})
                ]),
                ("Calling tool 1 again...", [  # This should trigger repetition detection
                    ToolCall(id="call_2", tool_name="get_current_time", arguments={})
                ]),
                ("Calling tool 1 again...", [  # This should also trigger repetition detection
                    ToolCall(id="call_3", tool_name="get_current_time", arguments={})
                ]),
                ("All done.", [])  # Final response from fallback
            ]
            # Mock the fallback generate call
            mock_ai_service.generate.return_value = "All done."

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Call tool repeatedly")

            assert should_continue is True
            # generate_with_tools called twice: first executes the tool, second
            # request is detected as a repeat and triggers the fallback
            assert mock_ai_service.generate_with_tools.call_count == 2
            assert mock_ai_service.generate.call_count == 1
            # Should have executed exactly 1 tool call (then repetition detection stopped the loop)
            assert self.conversation.orchestrator._tool_call_count == 1
            # History: user, assistant(tool_calls), tool result, assistant final (from fallback)
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Call tool repeatedly"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "All done."

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

    @pytest.mark.asyncio
    async def test_single_get_current_time_call(self):
        """Test that AI calls get_current_time exactly once for 'what time is it now' and doesn't repeat."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            # First call: AI requests get_current_time tool
            # Second call: AI has the result and returns final answer (no tool calls)
            mock_ai_service.generate_with_tools.side_effect = [
                ("Let me check the current time for you.", [
                    ToolCall(id="call_1", tool_name="get_current_time", arguments={})
                ]),
                ("The current time is 2026-09-05 10:30:00.", [])  # Final response, no tools
            ]

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("what time is it now")

            assert should_continue is True
            # Should have called AI service exactly twice: once for tool request, once for final response
            assert mock_ai_service.generate_with_tools.call_count == 2
            # Verify conversation history: user request, assistant(tool_calls), tool result, assistant final response
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "what time is it now"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert self.conversation.conversation_history[1]["content"] == "Let me check the current time for you."
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[1]["tool_calls"][0]["function"]["name"] == "get_current_time"
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "The current time is 2026-09-05 10:30:00."

    # REGRESSION TESTS PER REQUIREMENT I

    @pytest.mark.asyncio
    async def test_same_tool_across_iterations_detected(self):
        """Regression test: same tool requested across multiple AI iterations is detected and not executed repeatedly."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate = AsyncMock()
            # AI requests the same tool twice in a row
            mock_ai_service.generate_with_tools.side_effect = [
                ("First request", [
                    ToolCall(id="call_1", tool_name="calculate", arguments={"expression": "2+2"})
                ]),
                ("Second request (same)", [  # Same tool+args - should be detected as repeat
                    ToolCall(id="call_2", tool_name="calculate", arguments={"expression": "2+2"})
                ]),
                ("Final answer", [])
            ]
            mock_ai_service.generate.return_value = "Final answer"

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("Calculate twice")

            assert should_continue is True
            # generate_with_tools called twice: first executes the tool, second
            # request is detected as a repeat and triggers the fallback
            assert mock_ai_service.generate_with_tools.call_count == 2
            assert mock_ai_service.generate.call_count == 1
            # Only one tool execution should happen
            assert self.conversation.orchestrator._tool_call_count == 1
            # History: user, assistant1(tool_calls), tool1 result, assistant final (from fallback)
            assert len(self.conversation.conversation_history) == 4
            assert self.conversation.conversation_history[0]["role"] == "user"
            assert self.conversation.conversation_history[0]["content"] == "Calculate twice"
            assert self.conversation.conversation_history[1]["role"] == "assistant"
            assert "tool_calls" in self.conversation.conversation_history[1]
            assert self.conversation.conversation_history[2]["role"] == "tool"
            assert self.conversation.conversation_history[2]["tool_call_id"] == "call_1"
            assert self.conversation.conversation_history[3]["role"] == "assistant"
            assert self.conversation.conversation_history[3]["content"] == "Final answer"

    @pytest.mark.asyncio
    async def test_get_messages_for_ai_never_starts_with_orphaned_tool(self):
        """Regression test: get_messages_for_ai never returns history beginning with orphaned role='tool'."""
        # Setup: manually create a history that starts with orphaned tool messages
        from iris.memory.models import MemoryContext

        # Create a context with orphaned tool messages at the start
        orphaned_context = MemoryContext(max_turns=20, summary_threshold=30)
        orphaned_context.turns = [
            {"role": "tool", "tool_call_id": "orphan_1", "name": "calculate", "content": "4"},
            {"role": "tool", "tool_call_id": "orphan_2", "name": "get_current_time", "content": "2026-09-05"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        # Inject this context into our conversation's memory manager
        self.conversation.memory_manager.context = orphaned_context

        # Get messages for AI - should strip the leading orphaned tool messages
        messages = self.conversation.memory_manager.get_messages_for_ai()

        # Verify: should NOT start with tool messages
        assert len(messages) > 0
        assert messages[0]["role"] != "tool"
        # Should start with the user message
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

        # Verify the orphaned tool messages were stripped
        orphaned_tool_count = sum(1 for m in messages if m.get("role") == "tool")
        assert orphaned_tool_count == 0  # All orphaned tools should be stripped

        # Verify we still have the valid conversation
        user_msg = next(m for m in messages if m.get("role") == "user")
        assert user_msg["content"] == "Hello"
        assistant_msg = next(m for m in messages if m.get("role") == "assistant")
        assert assistant_msg["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_what_time_is_it_now_exactly_one_tool_call(self):
        """Regression test: 'what time is it now' results in exactly one get_current_time call."""
        with patch.object(self.conversation, 'ai_service') as mock_ai_service:
            mock_ai_service.generate_with_tools = AsyncMock()
            mock_ai_service.generate = AsyncMock()

            # Mock the AI service responses
            mock_ai_service.generate_with_tools.side_effect = [
                ("Checking time...", [
                    ToolCall(id="time_call", tool_name="get_current_time", arguments={})
                ]),
                ("The time is 2026-09-05 12:00:00.", [])
            ]
            mock_ai_service.generate.return_value = "The time is 2026-09-05 12:00:00."

            self.conversation.ai_service = mock_ai_service
            self.conversation.conversation_history = []

            should_continue = await self.conversation.handle_user_input("what time is it now")

            assert should_continue is True
            # Exactly one tool execution should occur
            assert self.conversation.orchestrator._tool_call_count == 1
            # AI service called twice: once with tools (requested tool), once without (final response)
            assert mock_ai_service.generate_with_tools.call_count == 2
            assert mock_ai_service.generate.call_count == 0
            # Verify the tool call was get_current_time with empty args
            first_call_args = mock_ai_service.generate_with_tools.call_args_list[0]
            tools_passed = first_call_args[1]['tools']
            # Should have tools available
            assert len(tools_passed) > 0
            # Verify conversation ends with final answer
            assert len(self.conversation.conversation_history) >= 3
            # Find the final assistant message
            final_assistant_msg = self.conversation.conversation_history[-1]
            assert final_assistant_msg["role"] == "assistant"
            assert "2026-09-05" in final_assistant_msg["content"] or "12:00:00" in final_assistant_msg["content"]