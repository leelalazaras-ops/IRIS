"""
Tests for Phase 7 CLI integration.
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock
from iris.core.cli import IRISConversation
from iris.intent.models import Intent
from iris.planning.models import ActionPlan, ActionStep
from iris.tools.base import ToolResult


class TestCLIPhase7:
    """Tests for Phase 7 Intent & Action Engine integration in CLI."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        # Start with empty history; handle_user_input will add the user message
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True

    # --- Intent Creation Tests ---

    def test_create_intent_read_file_with_path(self):
        """Test _create_intent_from_user_input for read_file with explicit path."""
        intent = self.conversation._create_intent_from_user_input("read file test.txt")
        assert intent.action == "read_file"
        assert "path" in intent.arguments
        assert intent.confidence == 0.8  # As per implementation
        assert intent.original_request == "read file test.txt"

    def test_create_intent_read_file_default_path(self):
        """Test _create_intent_from_user_input for read_file without explicit path."""
        intent = self.conversation._create_intent_from_user_input("read file")
        assert intent.action == "read_file"
        assert intent.arguments.get("path") == "."
        assert intent.confidence == 0.5  # Lower confidence when no path

    def test_create_intent_write_file_with_path_and_content(self):
        """Test _create_intent_from_user_input for write_file with path and content."""
        # Updated implementation: extracts path and content from input
        intent = self.conversation._create_intent_from_user_input("write hello to test.txt")
        assert intent.action == "write_file"
        # Should extract path="test.txt", content="hello"
        assert intent.arguments.get("path") == "test.txt"
        assert intent.arguments.get("content") == "hello"
        assert intent.confidence == 0.8  # Higher confidence when extraction succeeds

    def test_create_intent_list_directory(self):
        """Test _create_intent_from_user_input for list_directory."""
        intent = self.conversation._create_intent_from_user_input("list directory")
        assert intent.action == "list_directory"
        assert intent.confidence == 0.8

    def test_create_intent_unknown_low_confidence(self):
        """Test _create_intent_from_user_input for unknown input returns low confidence."""
        intent = self.conversation._create_intent_from_user_input("foobar baz qux")
        # The implementation returns an Intent with low confidence (0.3) and action get_current_time?
        # Actually, from the code: if no keyword matches, it defaults to get_current_time with confidence 0.3.
        # We'll check that it returns an Intent and confidence is low (<0.5).
        assert isinstance(intent, Intent)
        assert intent.confidence < 0.5

    # --- Calculate Expression Extraction Tests ---
    def test_create_intent_calculate_simple_expression(self):
        """Test _create_intent_from_user_input for calculate with simple expression."""
        intent = self.conversation._create_intent_from_user_input("calculate 25 * 4")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "25 * 4"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate 25 * 4"

    def test_create_intent_compute_division(self):
        """Test _create_intent_from_user_input for compute with division."""
        intent = self.conversation._create_intent_from_user_input("compute 100 / 5")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "100 / 5"
        assert intent.confidence == 0.7
        assert intent.original_request == "compute 100 / 5"

    def test_create_intent_solve_addition(self):
        """Test _create_intent_from_user_input for solve with addition."""
        intent = self.conversation._create_intent_from_user_input("solve 12 + 8")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "12 + 8"
        assert intent.confidence == 0.7
        assert intent.original_request == "solve 12 + 8"

    def test_create_intent_what_is_with_parentheses(self):
        """Test _create_intent_from_user_input for what is with parentheses."""
        intent = self.conversation._create_intent_from_user_input("what is 7 * (3 + 2)")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "7 * (3 + 2)"
        assert intent.confidence == 0.7
        assert intent.original_request == "what is 7 * (3 + 2)"

    def test_create_intent_calculate_fallback_to_default(self):
        """Test _create_intent_from_user_input for calculate falls back to default expression."""
        intent = self.conversation._create_intent_from_user_input("calculate")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "2+2"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate"

    def test_create_intent_calculate_fallback_with_extra_words(self):
        """Test _create_intent_from_user_input for calculate falls back when no meaningful expression."""
        intent = self.conversation._create_intent_from_user_input("calculate please")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "2+2"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate please"

    # --- Confidence Threshold and Routing Tests ---

    @pytest.mark.asyncio
    async def test_high_confidence_intent_uses_planner_flow(self):
        """Test that high confidence intent (>=0.7) uses the intent flow."""
        # Use an input that matches a keyword with high confidence, e.g., "read file test.txt"
        high_conf_input = "read file test.txt"

        # Mock the planner's plan method to see if it's called
        with patch.object(self.conversation, 'planner') as mock_planner:
            # Create a mock that returns an ActionPlan directly (not a coroutine)
            mock_plan = ActionPlan(
                steps=[ActionStep(tool_name="read_file", arguments={"path": "test.txt"})]
            )
            mock_planner.plan.return_value = mock_plan
            # Mock the safety classifier
            with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                mock_safety.is_blocked.return_value = False
                mock_safety.requires_confirmation.return_value = False
                # Mock the AI service's generate method to avoid real AI calls
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Here is the content.")
                    # Mock the orchestrator's execute_tool_calls to avoid executing real tools
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="file content")
                        ])
                        # Call handle_user_input
                        await self.conversation.handle_user_input(high_conf_input)
                        # Verify that the planner's plan method was called (indicating intent flow was used)
                        mock_planner.plan.assert_called_once()
                        # Verify that the AI service was called for final response
                        mock_ai.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_confidence_intent_falls_back_to_standard_processing(self):
        """Test that low confidence intent (<0.7) falls back to standard tool processing."""
        # Use an input that doesn't match any keywords -> low confidence (0.3)
        low_conf_input = "foobar"

        # Mock the AI service's generate method because the fallback will use it
        with patch.object(self.conversation, 'ai_service') as mock_ai:
            mock_ai.generate = AsyncMock(return_value="Fallback response")
            # Mock the AI service's generate_with_tools method (called in _process_with_tools)
            mock_ai.generate_with_tools = AsyncMock(return_value=("AI response with tools", []))
            # Mock the orchestrator
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.reset_call_count = Mock()  # Not awaited
                mock_orch.execute_tool_calls = AsyncMock(return_value=[
                    ToolResult(success=True, content="test")
                ])
                # Mock the tool registry
                with patch.object(self.conversation, 'tool_registry') as mock_reg:
                    mock_reg.list_tools = Mock(return_value=[])
                    # Mock the tool schema converter
                    with patch('iris.core.cli.ToolSchemaConverter') as mock_converter_class:
                        mock_converter_instance = Mock()
                        mock_converter_instance.registry_to_openai_functions.return_value = []
                        mock_converter_class.return_value = mock_converter_instance

                        # Call handle_user_input
                        await self.conversation.handle_user_input(low_conf_input)

                        # Verify that the AI service's generate_with_tools was called (indicating fallback to standard processing)
                        mock_ai.generate_with_tools.assert_called_once()

    # --- Dry-run Mode Tests ---

    @pytest.mark.asyncio
    async def test_dry_run_command_toggles_mode(self):
        """Test that /dry-run command toggles dry_run_mode."""
        assert self.conversation.dry_run_mode is False
        # Simulate handling the /dry-run command
        result = await self.conversation.handle_tool_command("/dry-run")
        assert result is True
        assert self.conversation.dry_run_mode is True
        # Toggle again
        result = await self.conversation.handle_tool_command("/dry-run")
        assert result is True
        assert self.conversation.dry_run_mode is False

    @pytest.mark.asyncio
    async def test_dry_run_mode_simulates_confirmation_required_action(self):
        """Test that in dry-run mode, confirmation-required actions are simulated."""
        # Set dry_run mode to True
        self.conversation.dry_run_mode = True
        # We need to set up a scenario where we have a confirmation-required action pending.
        # Let's use a patched _create_intent_from_user_input to return a high confidence confirmation-required intent.
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",  # We are pretending this is a high confidence intent
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.9,  # High confidence
                original_request="write hello to test.txt"
            )
            # Now we need to mock the planner to return a plan for write_file
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[ActionStep(
                        tool_name="write_file",
                        arguments={"path": "test.txt", "content": "hello"},
                        description="Write file: test.txt"
                    )]
                )
                mock_planner.plan.return_value = mock_plan
                # Mock the safety classifier to say write_file requires confirmation
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = True  # write_file requires confirmation
                    # Mock the dry-run execution method
                    with patch.object(self.conversation, '_execute_action_step_dry_run', new_callable=AsyncMock) as mock_dry_run:
                        mock_dry_run.return_value = ToolResult(success=True, content="Written")
                        # Mock AI service for final response
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Dry run successful.")
                            # Call handle_user_input
                            await self.conversation.handle_user_input("write hello to test.txt")
                            # In dry-run mode, we expect the action to be simulated (not stored as pending)
                            # and a final response generated.
                            mock_dry_run.assert_called_once()
                            mock_ai.generate.assert_called_once()
                            # After dry-run, there should be no pending confirmation
                            assert self.conversation.pending_confirmation is None

    # --- Confirm/Cancel Command Tests ---

    @pytest.mark.asyncio
    async def test_confirm_command_executes_pending_action(self):
        """Test that /confirm command executes the pending confirmation-required action."""
        # First, we need to set up a pending confirmation.
        # We'll simulate the state after an intent that requires confirmation was detected.
        expected_action = ActionStep(
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            description="Write file: test.txt"
        )
        self.conversation.pending_confirmation = expected_action
        self.conversation.pending_plan = ActionPlan(steps=[self.conversation.pending_confirmation])
        # Mock the execution method
        with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolResult(success=True, content="Written")
            # Call handle_tool_command with /confirm
            await self.conversation.handle_tool_command("/confirm")
            # Verify the action was executed with the expected action (saved before call)
            mock_execute.assert_called_once_with(expected_action)
            # Verify pending confirmation was cleared
            assert self.conversation.pending_confirmation is None
            assert self.conversation.pending_plan is None

    @pytest.mark.asyncio
    async def test_cancel_command_clears_pending_action(self):
        """Test that /cancel command clears the pending confirmation without execution."""
        # Set up a pending confirmation
        self.conversation.pending_confirmation = ActionStep(
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            description="Write file: test.txt"
        )
        self.conversation.pending_plan = ActionPlan(steps=[self.conversation.pending_confirmation])
        # Call handle_tool_command with /cancel
        await self.conversation.handle_tool_command("/cancel")
        # Verify pending confirmation was cleared
        assert self.conversation.pending_confirmation is None
        assert self.conversation.pending_plan is None
        # Note: No execution should have happened

    @pytest.mark.asyncio
    async def test_confirm_with_no_pending_action(self):
        """Test that /confirm when no pending action informs the user."""
        # Ensure no pending confirmation
        self.conversation.pending_confirmation = None
        self.conversation.pending_plan = None
        # We'll need to capture output. Let's use capsys via fixture, but for simplicity we'll just call and assume it prints.
        # We'll test by checking that it returns True and does not crash.
        result = await self.conversation.handle_tool_command("/confirm")
        assert result is True
        # The state should remain unchanged
        assert self.conversation.pending_confirmation is None

    # --- Safe Action Execution Tests ---

    @pytest.mark.asyncio
    async def test_safe_action_executes_without_confirmation(self):
        """Test that a safe action (e.g., read_file) executes without requiring confirmation."""
        # We'll set up a scenario where the intent is read_file (safe) and confidence is high.
        # Note: read_file with a path has confidence 0.8, which is above the threshold.
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="read_file",
                arguments={"path": "test.txt"},
                confidence=0.8,
                original_request="read file test.txt"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[ActionStep(
                        tool_name="read_file",
                        arguments={"path": "test.txt"},
                        description="Read file: test.txt"
                    )]
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False  # read_file is safe
                    # Mock orchestrator to execute the tool call
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="file content")
                        ])
                        # Mock AI service for final response
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Here is the content.")
                            # Call handle_user_input
                            await self.conversation.handle_user_input("read file test.txt")
                            # Verify that the orchestrator was called (action executed)
                            mock_orch.execute_tool_calls.assert_called_once()
                            # Verify that no pending confirmation was set (since it's safe)
                            assert self.conversation.pending_confirmation is None
                            # Verify final response was generated
                            mock_ai.generate.assert_called_once()

    # --- Blocked Action Tests ---

    @pytest.mark.asyncio
    async def test_blocked_action_is_handled_as_failure(self):
        """Test that a blocked action results in a failure and no pending confirmation."""
        # We need to mock the safety classifier to return BLOCKED for a tool.
        # According to the implementation, unknown tools (not in registry) are blocked.
        # So we'll mock the registry to return False for has_tool.
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="unknown_tool",  # This tool is not in the registry
                arguments={"path": "test.txt"},
                confidence=0.8,
                original_request="do unknown thing"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[ActionStep(
                        tool_name="unknown_tool",
                        arguments={"path": "test.txt"},
                        description="Do unknown thing"
                    )]
                )
                mock_planner.plan.return_value = mock_plan
                # Mock the registry in the safety classifier to return False for has_tool
                with patch.object(self.conversation.tool_registry, 'has_tool', return_value=False):
                    # Mock safety classifier methods
                    with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                        mock_safety.is_blocked.return_value = True  # This will be overridden by the registry check, but we set it for clarity
                        mock_safety.requires_confirmation.return_value = False
                        # Mock orchestrator (should not be called for blocked actions in the intent flow? Let's see)
                        # In the code, if blocked, we create a failed tool result and add to memory, then continue.
                        with patch.object(self.conversation, 'orchestrator') as mock_orch:
                            mock_orch.execute_tool_calls = AsyncMock(return_value=[])  # Should not be called
                            # Mock AI service for final response
                            with patch.object(self.conversation, 'ai_service') as mock_ai:
                                mock_ai.generate = AsyncMock(return_value="Action blocked.")
                                # Call handle_user_input
                                await self.conversation.handle_user_input("do unknown thing")
                                # Verify that the orchestrator was NOT called (because we handled blocked internally)
                                mock_orch.execute_tool_calls.assert_not_called()
                                # Verify final response was generated
                                mock_ai.generate.assert_called_once()
                                # There should be no pending confirmation
                                assert self.conversation.pending_confirmation is None

    # --- Edge Case: Empty Plan ---

    @pytest.mark.asyncio
    async def test_empty_plan_falls_back_to_standard_processing(self):
        """Test that if the planner returns an empty plan, we fall back to standard processing."""
        # Use an input that matches a keyword but the planner returns empty plan (e.g., unknown action that maps to no tool)
        # We'll mock the planner to return an empty plan for a known intent action.
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(action="unknown_action", arguments={}, confidence=0.8, original_request="unknown action")
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(steps=[])  # Empty plan
                mock_planner.plan.return_value = mock_plan
                # Mock the AI service for fallback
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Standard response")
                    mock_ai.generate_with_tools = AsyncMock(return_value=("Standard response with tools", []))
                    await self.conversation.handle_user_input("unknown action")
                    # Verify that the AI service's generate_with_tools was called (indicating fallback to standard processing)
                    mock_ai.generate_with_tools.assert_called_once()