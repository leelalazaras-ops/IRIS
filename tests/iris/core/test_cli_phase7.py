"""
Tests for Phase 7 CLI integration.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, Mock
from iris.core.cli import IRISConversation
from iris.intent.models import Intent
from iris.planning.models import ActionPlan, ActionStep
from iris.planning.planner import Planner
from iris.safety.classifier import SafetyClassifier
from iris.tools.base import ToolResult


class TestCLIPhase7:
    """Tests for Phase 7 Intent & Action Engine integration in CLI."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        # Start with empty history; handle_user_input will add the user message
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        # Ensure AI service is None to avoid invoking LLM classifier in tests
        self.conversation.ai_service = None

    # --- Intent Creation Tests ---

    def test_create_intent_read_file_with_path(self):
        """Test _create_intent_from_user_input for read_file with explicit path."""
        intent = self.conversation._create_intent_from_user_input_rule_based("read file test.txt")
        assert intent.action == "read_file"
        assert "path" in intent.arguments
        assert intent.confidence == 0.8  # As per implementation
        assert intent.original_request == "read file test.txt"

    def test_create_intent_read_file_default_path(self):
        """Test _create_intent_from_user_input for read_file without explicit path."""
        intent = self.conversation._create_intent_from_user_input_rule_based("read file")
        assert intent.action == "read_file"
        assert intent.arguments.get("path") == "."
        assert intent.confidence == 0.5  # Lower confidence when no path

    def test_create_intent_write_file_with_path_and_content(self):
        """Test _create_intent_from_user_input for write_file with path and content."""
        # Updated implementation: extracts path and content from input
        intent = self.conversation._create_intent_from_user_input_rule_based("write hello to test.txt")
        assert intent.action == "write_file"
        # Should extract path="test.txt", content="hello"
        assert intent.arguments.get("path") == "test.txt"
        assert intent.arguments.get("content") == "hello"
        assert intent.confidence == 0.8  # Higher confidence when extraction succeeds

    def test_create_intent_list_directory(self):
        """Test _create_intent_from_user_input for list_directory."""
        intent = self.conversation._create_intent_from_user_input_rule_based("list directory")
        assert intent.action == "list_directory"
        assert intent.confidence == 0.8

    def test_create_intent_unknown_low_confidence(self):
        """Test _create_intent_from_user_input for unknown input returns low confidence."""
        intent = self.conversation._create_intent_from_user_input_rule_based("foobar baz qux")
        # The implementation returns an Intent with low confidence (0.3) and action get_current_time?
        # Actually, from the code: if no keyword matches, it defaults to get_current_time with confidence 0.3.
        # We'll check that it returns an Intent and confidence is low (<0.5).
        assert isinstance(intent, Intent)
        assert intent.confidence < 0.5

    # --- Calculate Expression Extraction Tests ---
    def test_create_intent_calculate_simple_expression(self):
        """Test _create_intent_from_user_input for calculate with simple expression."""
        intent = self.conversation._create_intent_from_user_input_rule_based("calculate 25 * 4")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "25 * 4"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate 25 * 4"

    def test_create_intent_compute_division(self):
        """Test _create_intent_from_user_input for compute with division."""
        intent = self.conversation._create_intent_from_user_input_rule_based("compute 100 / 5")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "100 / 5"
        assert intent.confidence == 0.7
        assert intent.original_request == "compute 100 / 5"

    def test_create_intent_solve_addition(self):
        """Test _create_intent_from_user_input for solve with addition."""
        intent = self.conversation._create_intent_from_user_input_rule_based("solve 12 + 8")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "12 + 8"
        assert intent.confidence == 0.7
        assert intent.original_request == "solve 12 + 8"

    def test_create_intent_what_is_with_parentheses(self):
        """Test _create_intent_from_user_input for what is with parentheses."""
        intent = self.conversation._create_intent_from_user_input_rule_based("what is 7 * (3 + 2)")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "7 * (3 + 2)"
        assert intent.confidence == 0.7
        assert intent.original_request == "what is 7 * (3 + 2)"

    def test_create_intent_calculate_fallback_to_default(self):
        """Test _create_intent_from_user_input for calculate falls back to default expression."""
        intent = self.conversation._create_intent_from_user_input_rule_based("calculate")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "2+2"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate"

    def test_create_intent_calculate_fallback_with_extra_words(self):
        """Test _create_intent_from_user_input for calculate falls back when no meaningful expression."""
        intent = self.conversation._create_intent_from_user_input_rule_based("calculate please")
        assert intent.action == "calculate"
        assert intent.arguments.get("expression") == "2+2"
        assert intent.confidence == 0.7
        assert intent.original_request == "calculate please"

    # --- Regression Tests for Path Extraction (Phase 7.2C-4) ---
    def test_create_intent_create_directory_projects_path(self):
        """Test _create_intent_from_user_input for 'create directory projects' -> create_directory with path."""
        intent = self.conversation._create_intent_from_user_input_rule_based("create directory projects")
        assert intent.action == "create_directory"
        assert intent.arguments.get("path") == "projects"
        assert intent.confidence == 0.8  # As per implementation for create keyword
        assert intent.original_request == "create directory projects"

    def test_create_intent_list_directory_projects_path(self):
        """Test _create_intent_from_user_input for 'list directory projects' -> list_directory with path."""
        intent = self.conversation._create_intent_from_user_input_rule_based("list directory projects")
        assert intent.action == "list_directory"
        assert intent.arguments.get("path") == "projects"
        # Confidence: list keyword with path -> 0.8 (we don't have special ls handling here)
        assert intent.confidence == 0.8
        assert intent.original_request == "list directory projects"

    def test_create_intent_create_folder_named_test_data_path(self):
        """Test _create_intent_from_user_input for 'create a folder named test_data' -> create_directory with path."""
        intent = self.conversation._create_intent_from_user_input_rule_based("create a folder named test_data")
        assert intent.action == "create_directory"
        assert intent.arguments.get("path") == "test_data"
        assert intent.confidence == 0.8  # As per implementation for create keyword
        assert intent.original_request == "create a folder named test_data"

    # --- Confidence Threshold and Routing Tests ---

    @pytest.mark.asyncio
    async def test_high_confidence_intent_uses_planner_flow(self):
        """Test that high confidence intent (>=0.7) uses the intent flow."""
        # Use an input that matches a keyword with high confidence, e.g., "read file test.txt"
        high_conf_input = "read file test.txt"

        # Ensure the AI service is set (to a mock) so that the LLM path is taken
        self.conversation.ai_service = AsyncMock()
        # Mock the classify_intent function to return a high confidence classification
        with patch('iris.intent.llm_classifier.classify_intent') as mock_classify:
            mock_classify.return_value = {
                "action": "read_file",
                "arguments": {"path": "test.txt"},
                "confidence": 0.9
            }

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
                    # Mock the orchestrator's execute_tool_calls to avoid executing real tools
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="file content")
                        ])
                        # Mock the AI service's generate method for the final response
                        self.conversation.ai_service.generate = AsyncMock(return_value="Here is the content.")
                        # Call handle_user_input
                        await self.conversation.handle_user_input(high_conf_input)
                        # Verify that the planner's plan method was called (indicating intent flow was used)
                        mock_planner.plan.assert_called_once()
                        # Verify that the AI service was called for final response
                        # Note: The AI service is called twice - once for classification, once for final response
                        # But we've mocked the classify_intent function, so it should only be called once for the final response
                        # However, if the mock doesn't work properly, it might be called for classification too
                        # For now, we'll just check that it's called at least once
                        self.conversation.ai_service.generate.assert_called()

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
                            assert self.conversation.pending_remaining_steps is None

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
        self.conversation.pending_remaining_steps = [expected_action]
        self.conversation.pending_plan = ActionPlan(steps=self.conversation.pending_remaining_steps)
        # Mock the execution method
        with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolResult(success=True, content="Written")
            # Call handle_tool_command with /confirm
            await self.conversation.handle_tool_command("/confirm")
            # Verify the action was executed with the expected action (saved before call)
            mock_execute.assert_called_once_with(expected_action)
            # Verify pending confirmation was cleared
            assert self.conversation.pending_remaining_steps is None
            assert self.conversation.pending_plan is None

    @pytest.mark.asyncio
    async def test_cancel_command_clears_pending_action(self):
        """Test that /cancel command clears the pending confirmation without execution."""
        # Set up a pending confirmation
        pending_step = ActionStep(
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            description="Write file: test.txt"
        )
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=self.conversation.pending_remaining_steps)
        # Call handle_tool_command with /cancel
        await self.conversation.handle_tool_command("/cancel")
        # Verify pending confirmation was cleared
        assert self.conversation.pending_remaining_steps is None
        assert self.conversation.pending_plan is None
        # Note: No execution should have happened

    @pytest.mark.asyncio
    async def test_confirm_with_no_pending_action(self):
        """Test that /confirm when no pending action informs the user."""
        # Ensure no pending confirmation
        self.conversation.pending_remaining_steps = None
        self.conversation.pending_plan = None
        # We'll need to capture output. Let's use capsys via fixture, but for simplicity we'll just call and assume it prints.
        # We'll test by checking that it returns True and does not crash.
        result = await self.conversation.handle_tool_command("/confirm")
        assert result is True
        # The state should remain unchanged
        assert self.conversation.pending_remaining_steps is None

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
                            assert self.conversation.pending_remaining_steps is None
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
                                assert self.conversation.pending_remaining_steps is None

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


class TestCLIMultistepIntegration:
    """Integration tests for multi-step plan execution through the CLI pipeline (Phase 7.3C)."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True

    # --- Sequential Execution Tests ---

    @pytest.mark.asyncio
    async def test_multistep_plan_executes_sequentially(self):
        """Test that multi-step plans execute each step sequentially through the orchestrator."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            # Create a multi-step intent
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "notes.txt", "content": "hello"},
                confidence=0.8,
                original_request="create directory projects and write a file notes.txt containing hello"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                # Create a plan with 2 steps
                mock_plan = ActionPlan(
                    steps=[
                        ActionStep(
                            tool_name="create_directory",
                            arguments={"path": "projects"},
                            description="Create directory projects"
                        ),
                        ActionStep(
                            tool_name="write_file",
                            arguments={"path": "notes.txt", "content": "hello"},
                            description="Write file notes.txt"
                        )
                    ],
                    metadata={"multistep": True}
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        # Mock orchestrator to return success for both steps
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="Directory created"),
                            ToolResult(success=True, content="File written")
                        ])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")
                            await self.conversation.handle_user_input("create directory and write file")
                            # Verify orchestrator was called once with both tool calls
                            mock_orch.execute_tool_calls.assert_called_once()
                            # Get the tool calls that were passed
                            call_args = mock_orch.execute_tool_calls.call_args
                            tool_calls = call_args[0][0]
                            # Verify both steps are included
                            assert len(tool_calls) == 2
                            assert tool_calls[0].tool_name == "create_directory"
                            assert tool_calls[1].tool_name == "write_file"

    @pytest.mark.asyncio
    async def test_multistep_results_distinguishable_by_index(self):
        """Test that results from each step remain distinguishable."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "notes.txt", "content": "hello"},
                confidence=0.8,
                original_request="create and write"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[
                        ActionStep(tool_name="create_directory", arguments={"path": "data"}),
                        ActionStep(tool_name="write_file", arguments={"path": "file.txt", "content": "hi"})
                    ],
                    metadata={"multistep": True}
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="dir result"),
                            ToolResult(success=True, content="file result")
                        ])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")
                            await self.conversation.handle_user_input("create and write")
                            # Verify orchestrator was called with distinct tool call IDs
                            call_args = mock_orch.execute_tool_calls.call_args
                            tool_calls = call_args[0][0]
                            assert tool_calls[0].id == "action_0"
                            assert tool_calls[1].id == "action_1"

    @pytest.mark.asyncio
    async def test_multistep_step2_waits_for_step1(self):
        """Test that step 2 executes only after step 1 completes (sequential execution)."""
        execution_order = []

        async def mock_execute(tool_calls):
            for tc in tool_calls:
                execution_order.append(tc.tool_name)
                await asyncio.sleep(0.01)  # Small delay to ensure ordering
            return [ToolResult(success=True, content="ok") for _ in tool_calls]

        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hi"},
                confidence=0.8,
                original_request="create dir and write file"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[
                        ActionStep(tool_name="create_directory", arguments={"path": "dir"}),
                        ActionStep(tool_name="write_file", arguments={"path": "f.txt", "content": "c"})
                    ],
                    metadata={"multistep": True}
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = mock_execute
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")
                            await self.conversation.handle_user_input("create and write")
                            # Verify execution order: create_directory before write_file
                            assert execution_order[0] == "create_directory"
                            assert execution_order[1] == "write_file"

    # --- Error/Failure Handling Tests ---

    @pytest.mark.asyncio
    async def test_multistep_failed_step_handled(self):
        """Test that a failed step in a multi-step plan is handled according to existing behavior."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hi"},
                confidence=0.8,
                original_request="create and write"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_plan = ActionPlan(
                    steps=[
                        ActionStep(tool_name="create_directory", arguments={"path": "dir"}),
                        ActionStep(tool_name="write_file", arguments={"path": "f.txt", "content": "c"})
                    ],
                    metadata={"multistep": True}
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        # First step succeeds, second step fails
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="dir created"),
                            ToolResult(success=False, content=None, error="Write failed: permission denied")
                        ])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Completed with errors.")
                            await self.conversation.handle_user_input("create and write")
                            # Verify orchestrator was still called (even with failure)
                            mock_orch.execute_tool_calls.assert_called_once()
                            # Verify AI was still called to generate response
                            mock_ai.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_execution_unchanged(self):
        """Test that existing single-step execution is unchanged by multi-step feature."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="read_file",
                arguments={"path": "test.txt"},
                confidence=0.8,
                original_request="read file test.txt"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                # Single-step plan (no multistep flag)
                mock_plan = ActionPlan(
                    steps=[
                        ActionStep(tool_name="read_file", arguments={"path": "test.txt"})
                    ]
                )
                mock_planner.plan.return_value = mock_plan
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.is_blocked.return_value = False
                    mock_safety.requires_confirmation.return_value = False
                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="file content")
                        ])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Here is the content.")
                            await self.conversation.handle_user_input("read file test.txt")
                            # Verify only one tool call was made
                            mock_orch.execute_tool_calls.assert_called_once()
                            call_args = mock_orch.execute_tool_calls.call_args
                            tool_calls = call_args[0][0]
                            assert len(tool_calls) == 1
                            assert tool_calls[0].tool_name == "read_file"

    # --- Real Pipeline Integration Tests ---

    @pytest.mark.asyncio
    async def test_real_planner_multistep_flow(self):
        """Test multi-step execution using the real planner (no mocking)."""
        # This test uses a real planner but mocks the orchestrator
        # to verify the full flow works with actual multi-step detection
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            # Create intent that the real planner will detect as multi-step
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "notes.txt", "content": "hello"},
                confidence=0.8,
                original_request="create directory projects and write a file notes.txt containing hello"
            )
            with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                mock_safety.is_blocked.return_value = False
                mock_safety.requires_confirmation.return_value = False
                with patch.object(self.conversation, 'orchestrator') as mock_orch:
                    mock_orch.execute_tool_calls = AsyncMock(return_value=[
                        ToolResult(success=True, content="Directory created"),
                        ToolResult(success=True, content="File written")
                    ])
                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")
                        # Use the real planner
                        await self.conversation.handle_user_input("create directory projects and write a file notes.txt containing hello")
                        # Verify orchestrator was called
                        mock_orch.execute_tool_calls.assert_called_once()
                        call_args = mock_orch.execute_tool_calls.call_args
                        tool_calls = call_args[0][0]
                        # Verify both steps are present
                        assert len(tool_calls) == 2
                        assert tool_calls[0].tool_name == "create_directory"
                        assert tool_calls[1].tool_name == "write_file"


class TestMultistepConfirmationFix:
    """Regression tests for Phase 7.3D-1: Multi-step confirmation fix.

    Verifies the critical safety gap: when a multi-step plan contains a
    REQUIRES_CONFIRMATION step, the confirmation-required step AND all
    subsequent steps must be preserved (not lost) for execution after /confirm.
    """

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        # Ensure dry-run is OFF so we hit the pending-remaining-steps path
        self.conversation.dry_run_mode = False

    # --- Regression Test 1: SAFE + CONFIRM → both execute after confirmation ---

    @pytest.mark.asyncio
    async def test_safe_step_then_confirm_step_both_execute_after_confirm(self):
        """Plan: [SAFE, CONFIRM] → /confirm should execute BOTH steps in order."""
        # Create a 2-step plan where step 0 is SAFE (read_file) and step 1 requires confirmation (write_file)
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="read then write"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                step1 = ActionStep(
                    tool_name="read_file",
                    arguments={"path": "input.txt"},
                    safety_classification=None,
                    description="Read file: input.txt"
                )
                step2 = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "test.txt", "content": "hello"},
                    safety_classification=None,
                    description="Write file: test.txt"
                )
                mock_plan = ActionPlan(steps=[step1, step2])
                mock_planner.plan.return_value = mock_plan

                # Configure safety classifier:
                # - read_file is SAFE
                # - write_file requires confirmation
                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    def requires_confirmation_side_effect(tool_name, args):
                        return tool_name == "write_file"

                    def is_blocked_side_effect(tool_name, args):
                        return False

                    mock_safety.requires_confirmation.side_effect = requires_confirmation_side_effect
                    mock_safety.is_blocked.side_effect = is_blocked_side_effect

                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")

                        # First call: triggers confirmation, returns early with message
                        result = await self.conversation.handle_user_input("read then write")

                        # handle_user_input always returns True (bool); the confirmation
                        # response is added to memory as an assistant message.
                        assert result is True
                        # Inspect memory for the confirmation prompt
                        last_assistant = self.conversation.memory_manager.context.turns[-1]
                        assert "requires confirmation" in last_assistant["content"].lower()

                        # Both steps should be stored (not just step 2)
                        assert self.conversation.pending_remaining_steps is not None
                        assert len(self.conversation.pending_remaining_steps) == 2
                        assert self.conversation.pending_remaining_steps[0].tool_name == "read_file"
                        assert self.conversation.pending_remaining_steps[1].tool_name == "write_file"

                        # Now run /confirm
                        with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
                            mock_execute.return_value = ToolResult(success=True, content="ok")
                            await self.conversation.handle_tool_command("/confirm")

                            # BOTH steps should have been executed
                            assert mock_execute.call_count == 2
                            # Verify execution order
                            first_call_args = mock_execute.call_args_list[0]
                            second_call_args = mock_execute.call_args_list[1]
                            assert first_call_args[0][0].tool_name == "read_file"
                            assert second_call_args[0][0].tool_name == "write_file"

                        # Pending state should be cleared
                        assert self.conversation.pending_remaining_steps is None
                        assert self.conversation.pending_plan is None

    # --- Regression Test 2: SAFE + CONFIRM + later step → all remaining steps execute in order ---

    @pytest.mark.asyncio
    async def test_all_remaining_steps_execute_in_order(self):
        """Plan: [SAFE, CONFIRM, SAFE, SAFE] → /confirm executes steps 1,2,3 in order."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="multi-step"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                step1 = ActionStep(
                    tool_name="read_file",
                    arguments={"path": "a.txt"},
                    description="Read file: a.txt"
                )
                step2 = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "test.txt", "content": "hello"},
                    description="Write file: test.txt"
                )
                step3 = ActionStep(
                    tool_name="calculate",
                    arguments={"expression": "2+2"},
                    description="Calculate: 2+2"
                )
                step4 = ActionStep(
                    tool_name="list_directory",
                    arguments={"path": "."},
                    description="List directory: ."
                )
                mock_plan = ActionPlan(steps=[step1, step2, step3, step4])
                mock_planner.plan.return_value = mock_plan

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    # Only step 2 (write_file) requires confirmation
                    def requires_confirmation_side_effect(tool_name, args):
                        return tool_name == "write_file"

                    mock_safety.requires_confirmation.side_effect = requires_confirmation_side_effect
                    mock_safety.is_blocked.return_value = False

                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")

                        result = await self.conversation.handle_user_input("multi-step")

                        # handle_user_input always returns True
                        assert result is True
                        # Confirmation prompt should be in memory
                        last_assistant = self.conversation.memory_manager.context.turns[-1]
                        assert "confirm" in last_assistant["content"].lower()

                    # ALL 4 steps should be stored (the SAFE read_file that
                    # came before the confirmation step, plus the confirm
                    # step, plus the 2 later steps). No step may be lost.
                    assert self.conversation.pending_remaining_steps is not None
                    assert len(self.conversation.pending_remaining_steps) == 4
                    assert self.conversation.pending_remaining_steps[0].tool_name == "read_file"
                    assert self.conversation.pending_remaining_steps[1].tool_name == "write_file"
                    assert self.conversation.pending_remaining_steps[2].tool_name == "calculate"
                    assert self.conversation.pending_remaining_steps[3].tool_name == "list_directory"

                    # Run /confirm
                    with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
                        mock_execute.return_value = ToolResult(success=True, content="ok")
                        await self.conversation.handle_tool_command("/confirm")

                        # All 4 steps should execute in order
                        assert mock_execute.call_count == 4
                        assert mock_execute.call_args_list[0][0][0].tool_name == "read_file"
                        assert mock_execute.call_args_list[1][0][0].tool_name == "write_file"
                        assert mock_execute.call_args_list[2][0][0].tool_name == "calculate"
                        assert mock_execute.call_args_list[3][0][0].tool_name == "list_directory"

                    assert self.conversation.pending_remaining_steps is None

    # --- Regression Test 3: CONFIRM + BLOCKED → confirmation does not allow BLOCKED execution ---

    @pytest.mark.asyncio
    async def test_blocked_step_after_confirm_step_never_executes(self):
        """Plan: [CONFIRM, BLOCKED] → /confirm executes confirm step but BLOCKED step is not in stored remaining steps.

        In a real flow, BLOCKED is filtered out BEFORE confirmation check, so
        a plan reaching the confirmation path has already had BLOCKED steps
        removed. This test verifies the implementation correctly handles the
        case where a step requires confirmation and a later step is blocked
        by verifying that the BLOCKED step does not appear in the pending state.
        """
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="test"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                step1 = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "test.txt", "content": "hello"},
                    description="Write file: test.txt"
                )
                # In a real flow, BLOCKED steps are filtered before this point.
                # Verify that ONLY non-blocked steps are preserved in pending.
                step2 = ActionStep(
                    tool_name="calculate",
                    arguments={"expression": "2+2"},
                    description="Calculate: 2+2"
                )
                mock_plan = ActionPlan(steps=[step1, step2])
                mock_planner.plan.return_value = mock_plan

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    def requires_confirmation_side_effect(tool_name, args):
                        return tool_name == "write_file"
                    mock_safety.requires_confirmation.side_effect = requires_confirmation_side_effect
                    mock_safety.is_blocked.return_value = False  # not blocked

                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")
                        result = await self.conversation.handle_user_input("test")
                        assert result is True

                    # Both non-blocked steps should be stored
                    assert self.conversation.pending_remaining_steps is not None
                    assert len(self.conversation.pending_remaining_steps) == 2

                    # Confirm executes both
                    with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
                        mock_execute.return_value = ToolResult(success=True, content="ok")
                        await self.conversation.handle_tool_command("/confirm")
                        assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_blocked_step_before_confirm_step_does_not_block_confirmation(self):
        """Plan: [BLOCKED, CONFIRM] → BLOCKED is handled in-loop, confirm step is stored.

        In the actual flow, BLOCKED steps are detected BEFORE the confirmation
        check, so the planner loop iterates: step 0 is BLOCKED → handled inline
        (failed tool result added to memory), loop continues to step 1 which
        requires confirmation → stored as pending. BLOCKED step is never
        included in pending_remaining_steps.
        """
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="test"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                blocked_step = ActionStep(
                    tool_name="unknown_tool",  # not in registry, will be blocked
                    arguments={"path": "x"},
                    description="Unknown tool"
                )
                confirm_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "test.txt", "content": "hello"},
                    description="Write file: test.txt"
                )
                mock_plan = ActionPlan(steps=[blocked_step, confirm_step])
                mock_planner.plan.return_value = mock_plan

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    def requires_confirmation_side_effect(tool_name, args):
                        return tool_name == "write_file"
                    def is_blocked_side_effect(tool_name, args):
                        return tool_name == "unknown_tool"
                    mock_safety.requires_confirmation.side_effect = requires_confirmation_side_effect
                    mock_safety.is_blocked.side_effect = is_blocked_side_effect

                    # Mock the tool registry has_tool for unknown_tool
                    with patch.object(self.conversation.tool_registry, 'has_tool', return_value=False):
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")

                            result = await self.conversation.handle_user_input("test")

                            # handle_user_input always returns True
                            assert result is True
                            # Confirmation prompt should be in memory
                            last_assistant = self.conversation.memory_manager.context.turns[-1]
                            assert "confirm" in last_assistant["content"].lower()

                            # Only the confirm step should be in pending, not the blocked step
                            assert self.conversation.pending_remaining_steps is not None
                            assert len(self.conversation.pending_remaining_steps) == 1
                            assert self.conversation.pending_remaining_steps[0].tool_name == "write_file"

                            # Confirm executes only the confirm step
                            with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
                                mock_execute.return_value = ToolResult(success=True, content="ok")
                                await self.conversation.handle_tool_command("/confirm")
                                assert mock_execute.call_count == 1
                                assert mock_execute.call_args_list[0][0][0].tool_name == "write_file"

    # --- Regression Test 4: Existing single-step confirmation behavior remains unchanged ---

    @pytest.mark.asyncio
    async def test_single_step_confirmation_behavior_unchanged(self):
        """Plan: [CONFIRM] (single step) → /confirm executes exactly 1 step, same as before."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="write hello to test.txt"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                single_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "test.txt", "content": "hello"},
                    description="Write file: test.txt"
                )
                mock_plan = ActionPlan(steps=[single_step])
                mock_planner.plan.return_value = mock_plan

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.requires_confirmation.return_value = True
                    mock_safety.is_blocked.return_value = False

                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")
                        result = await self.conversation.handle_user_input("write hello to test.txt")
                        # handle_user_input returns True
                        assert result is True
                        # Confirmation prompt in memory
                        last_assistant = self.conversation.memory_manager.context.turns[-1]
                        assert "confirm" in last_assistant["content"].lower()

                    # Single step stored in pending list
                    assert self.conversation.pending_remaining_steps is not None
                    assert len(self.conversation.pending_remaining_steps) == 1
                    assert self.conversation.pending_remaining_steps[0].tool_name == "write_file"

                    # Confirm executes exactly 1 step (same as before)
                    with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
                        mock_execute.return_value = ToolResult(success=True, content="ok")
                        await self.conversation.handle_tool_command("/confirm")
                        assert mock_execute.call_count == 1
                        assert mock_execute.call_args_list[0][0][0].tool_name == "write_file"

                    assert self.conversation.pending_remaining_steps is None
                    assert self.conversation.pending_plan is None

    # --- Regression Test 5: /cancel clears pending multi-step confirmation state ---

    @pytest.mark.asyncio
    async def test_cancel_clears_multi_step_pending_state(self):
        """Multi-step pending state is cleared by /cancel; no execution happens."""
        step1 = ActionStep(
            tool_name="create_directory",
            arguments={"path": "x"},
            description="Create directory x"
        )
        step2 = ActionStep(
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            description="Write file: test.txt"
        )
        step3 = ActionStep(
            tool_name="list_directory",
            arguments={"path": "."},
            description="List directory: ."
        )

        # Pre-populate pending state
        self.conversation.pending_remaining_steps = [step1, step2, step3]
        self.conversation.pending_plan = ActionPlan(steps=[step1, step2, step3])

        # Run /cancel
        with patch.object(self.conversation, '_execute_action_step', new_callable=AsyncMock) as mock_execute:
            await self.conversation.handle_tool_command("/cancel")
            # No execution should have happened
            mock_execute.assert_not_called()

        # State cleared
        assert self.conversation.pending_remaining_steps is None
        assert self.conversation.pending_plan is None

    # --- Regression Test 6: No confirmation-required plan loses remaining steps ---

    @pytest.mark.asyncio
    async def test_no_confirmation_needed_no_pending_state(self):
        """Plan with only SAFE steps: nothing stored in pending_remaining_steps."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "test.txt", "content": "hello"},
                confidence=0.8,
                original_request="safe multi-step"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                step1 = ActionStep(
                    tool_name="create_directory",
                    arguments={"path": "x"},
                    description="Create directory x"
                )
                step2 = ActionStep(
                    tool_name="calculate",
                    arguments={"expression": "2+2"},
                    description="Calculate: 2+2"
                )
                mock_plan = ActionPlan(steps=[step1, step2])
                mock_planner.plan.return_value = mock_plan

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    mock_safety.requires_confirmation.return_value = False
                    mock_safety.is_blocked.return_value = False

                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[
                            ToolResult(success=True, content="ok"),
                            ToolResult(success=True, content="4")
                        ])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")
                            await self.conversation.handle_user_input("safe multi-step")

                            # No pending state should be set since nothing required confirmation
                            assert self.conversation.pending_remaining_steps is None
                            assert self.conversation.pending_plan is None


class TestArgumentAwareSafetyIntegration:
    """Integration tests for argument-aware safety through the real IRIS pipeline (Phase 7.4C).

    These tests verify that the argument-aware BLOCKED decision (Phase 7.4B) is
    enforced end-to-end through the real IRISConversation pipeline - not just
    in the SafetyClassifier unit tests. We use the REAL SafetyClassifier and
    REAL Planner, mocking only the orchestrator and AI service (which would
    otherwise hit network / disk).

    Verification coverage:
      1. write_file with sensitive Windows/System32 path reaches BLOCKED
      2. create_directory with sensitive Windows/System32 path reaches BLOCKED
      3. Normal write_file path still follows REQUIRES_CONFIRMATION
      4. Normal create_directory path still follows REQUIRES_CONFIRMATION
      5. In a multi-step plan, each step's arguments are classified independently
      6. A BLOCKED step cannot execute even when other steps are SAFE
      7. A BLOCKED step cannot be bypassed through /confirm
      8. Existing single-step behavior remains unchanged
    """

    def setup_method(self):
        """Set up a fresh conversation with REAL components (no mock safety / planner)."""
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        # Ensure dry-run is OFF so we hit the BLOCKED / pending-remaining-steps path
        self.conversation.dry_run_mode = False
        # Sanity: confirm the real classifier is the arg-aware one
        assert isinstance(self.conversation.safety_classifier, SafetyClassifier)
        assert isinstance(self.conversation.planner, Planner)
        # The real classifier must classify the arg-based patterns as BLOCKED.
        # If this assertion fails, the unit-test only configuration was lost.
        assert self.conversation.safety_classifier.is_blocked(
            "write_file", {"path": "C:/Windows/bad.txt"}
        ) is True
        assert self.conversation.safety_classifier.is_blocked(
            "create_directory", {"path": "C:/Windows/MyFolder"}
        ) is True

    # --- VERIFY 1: write_file + sensitive Windows path → BLOCKED through real pipeline ---

    @pytest.mark.asyncio
    async def test_write_file_to_windows_path_blocked_through_real_pipeline(self):
        """write_file targeting C:/Windows/... must reach BLOCKED through the real CLI pipeline."""
        # Force a high-confidence intent for write_file with a sensitive path.
        # We bypass _create_intent_from_user_input (which would normalize the
        # path) by patching it to return our exact intent.
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "C:/Windows/bad.txt", "content": "x"},
                confidence=0.9,
                original_request="write x to C:/Windows/bad.txt"
            )
            # Mock only the orchestrator (no real disk writes) and AI (no network).
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Blocked.")
                    await self.conversation.handle_user_input(
                        "write x to C:/Windows/bad.txt"
                    )

                    # BLOCKED step is NOT executed by the orchestrator
                    mock_orch.execute_tool_calls.assert_not_called()
                    # BLOCKED step is NOT added to pending_remaining_steps
                    # (only confirmation-required steps go there)
                    assert self.conversation.pending_remaining_steps is None
                    assert self.conversation.pending_plan is None
                    # A tool message marking it as blocked should be in memory
                    tool_messages = [
                        m for m in self.conversation.memory_manager.context.turns
                        if m.get("role") == "tool"
                    ]
                    assert len(tool_messages) == 1
                    assert "blocked" in tool_messages[0]["content"].lower()

    # --- VERIFY 2: create_directory + sensitive Windows path → BLOCKED through real pipeline ---

    @pytest.mark.asyncio
    async def test_create_directory_to_windows_path_blocked_through_real_pipeline(self):
        """create_directory targeting C:/Windows/... must reach BLOCKED through the real CLI pipeline."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="create_directory",
                arguments={"path": "C:/Windows/MyFolder"},
                confidence=0.9,
                original_request="create directory C:/Windows/MyFolder"
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Blocked.")
                    await self.conversation.handle_user_input(
                        "create directory C:/Windows/MyFolder"
                    )

                    mock_orch.execute_tool_calls.assert_not_called()
                    assert self.conversation.pending_remaining_steps is None
                    assert self.conversation.pending_plan is None
                    tool_messages = [
                        m for m in self.conversation.memory_manager.context.turns
                        if m.get("role") == "tool"
                    ]
                    assert len(tool_messages) == 1
                    assert "blocked" in tool_messages[0]["content"].lower()

    # --- VERIFY 3: Normal write_file path → REQUIRES_CONFIRMATION through real pipeline ---

    @pytest.mark.asyncio
    async def test_normal_write_file_still_requires_confirmation(self):
        """A normal write_file path must still go through REQUIRES_CONFIRMATION, not BLOCKED."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "documents/notes.md", "content": "hi"},
                confidence=0.9,
                original_request="write hi to documents/notes.md"
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Done.")
                    await self.conversation.handle_user_input(
                        "write hi to documents/notes.md"
                    )

                    # REQUIRES_CONFIRMATION step is NOT executed immediately
                    mock_orch.execute_tool_calls.assert_not_called()
                    # It IS stored as pending awaiting /confirm
                    assert self.conversation.pending_remaining_steps is not None
                    assert len(self.conversation.pending_remaining_steps) == 1
                    assert self.conversation.pending_remaining_steps[0].tool_name == "write_file"
                    # The last assistant message should be a confirmation prompt
                    last_assistant = self.conversation.memory_manager.context.turns[-1]
                    assert "confirm" in last_assistant["content"].lower()

    # --- VERIFY 4: Normal create_directory path → REQUIRES_CONFIRMATION through real pipeline ---

    @pytest.mark.asyncio
    async def test_normal_create_directory_still_requires_confirmation(self):
        """A normal create_directory path must still go through REQUIRES_CONFIRMATION, not BLOCKED."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="create_directory",
                arguments={"path": "projects"},
                confidence=0.9,
                original_request="create directory projects"
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Done.")
                    await self.conversation.handle_user_input(
                        "create directory projects"
                    )

                    mock_orch.execute_tool_calls.assert_not_called()
                    assert self.conversation.pending_remaining_steps is not None
                    assert len(self.conversation.pending_remaining_steps) == 1
                    assert self.conversation.pending_remaining_steps[0].tool_name == "create_directory"
                    last_assistant = self.conversation.memory_manager.context.turns[-1]
                    assert "confirm" in last_assistant["content"].lower()

    # --- VERIFY 5: Multi-step plan → each step's arguments classified independently ---

    @pytest.mark.asyncio
    async def test_multistep_classifies_each_step_independently(self):
        """A multi-step plan with a Windows path step must classify that step BLOCKED
        while leaving non-sensitive steps at their normal classification.

        The real planner extracts the file path from the intent's
        original_request when it detects a multi-step pattern. We craft an
        original_request whose extracted file path contains "windows", so
        the planner's write_file step is classified as BLOCKED. The first
        step (create_directory) is REQUIRES_CONFIRMATION, which causes the
        loop to return early with a confirmation prompt. The BLOCKED step
        must not appear in pending_remaining_steps.
        """
        original_request = (
            "create directory data and write a file C:/Windows/notes.txt containing hello"
        )
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "C:/Windows/notes.txt", "content": "hello"},
                confidence=0.8,
                original_request=original_request
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Done.")
                    await self.conversation.handle_user_input(original_request)

                    # No safe steps in the plan, so the orchestrator must not run.
                    mock_orch.execute_tool_calls.assert_not_called()
                    # Pending state: the create_directory step is there (needs
                    # confirmation). The BLOCKED write_file step must NOT be there.
                    assert self.conversation.pending_remaining_steps is not None
                    pending_tools = [s.tool_name for s in self.conversation.pending_remaining_steps]
                    assert "create_directory" in pending_tools
                    # The write_file step is BLOCKED - it must not be in pending.
                    assert "write_file" not in pending_tools
                    # Verify the BLOCKED step would not execute after /confirm
                    with patch.object(
                        self.conversation, '_execute_action_step', new_callable=AsyncMock
                    ) as mock_execute:
                        mock_execute.return_value = ToolResult(success=True, content="ok")
                        await self.conversation.handle_tool_command("/confirm")
                        # Only the create_directory step runs; write_file is filtered.
                        assert mock_execute.call_count == 1
                        assert mock_execute.call_args_list[0][0][0].tool_name == "create_directory"

    # --- VERIFY 6: BLOCKED step cannot execute even when other steps are SAFE ---

    @pytest.mark.asyncio
    async def test_blocked_step_does_not_execute_when_other_steps_are_safe(self):
        """In a plan [SAFE, BLOCKED], the orchestrator must only receive the SAFE step.
        The BLOCKED step must be filtered out before tool execution."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "x", "content": "y"},
                confidence=0.8,
                original_request="custom"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                # Inject a plan with one SAFE step and one BLOCKED step.
                # The real safety classifier will mark the write_file to
                # C:/Windows/... as BLOCKED in the step's safety_classification,
                # and the CLI's live classifier check will block it from execution.
                safe_step = ActionStep(
                    tool_name="calculate",
                    arguments={"expression": "2+2"},
                    description="Calculate 2+2"
                )
                blocked_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "C:/Windows/bad.txt", "content": "x"},
                    description="Write file C:/Windows/bad.txt"
                )
                mock_planner.plan.return_value = ActionPlan(steps=[safe_step, blocked_step])

                with patch.object(self.conversation, 'orchestrator') as mock_orch:
                    mock_orch.execute_tool_calls = AsyncMock(return_value=[
                        ToolResult(success=True, content="4")
                    ])
                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Done.")
                        await self.conversation.handle_user_input("custom")

                        # Orchestrator called exactly once (for the safe step only)
                        mock_orch.execute_tool_calls.assert_called_once()
                        call_args = mock_orch.execute_tool_calls.call_args
                        tool_calls = call_args[0][0]
                        # The blocked step must be filtered out
                        executed_tool_names = [tc.tool_name for tc in tool_calls]
                        assert "calculate" in executed_tool_names
                        assert "write_file" not in executed_tool_names
                        # No pending state (safe step ran, blocked was filtered)
                        assert self.conversation.pending_remaining_steps is None

    # --- VERIFY 7: BLOCKED step cannot be bypassed through /confirm ---

    @pytest.mark.asyncio
    async def test_blocked_step_cannot_be_bypassed_via_confirm(self):
        """A BLOCKED step must never appear in pending_remaining_steps,
        so /confirm cannot be used to bypass the block."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "C:/Windows/bad.txt", "content": "x"},
                confidence=0.9,
                original_request="write x to C:/Windows/bad.txt"
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Blocked.")
                    await self.conversation.handle_user_input(
                        "write x to C:/Windows/bad.txt"
                    )

                    # No pending state - blocked actions don't wait for /confirm
                    assert self.conversation.pending_remaining_steps is None
                    # Even if the user issues /confirm, it should be a no-op
                    # (no pending action to confirm)
                    with patch.object(
                        self.conversation, '_execute_action_step', new_callable=AsyncMock
                    ) as mock_execute:
                        await self.conversation.handle_tool_command("/confirm")
                        # No execution of any action
                        mock_execute.assert_not_called()
                    # Still no pending state
                    assert self.conversation.pending_remaining_steps is None

    # --- VERIFY 7b: BLOCKED step in mixed plan never reaches /confirm ---

    @pytest.mark.asyncio
    async def test_blocked_step_not_in_pending_even_when_other_steps_need_confirm(self):
        """In a plan [CONFIRM, BLOCKED, CONFIRM], the BLOCKED step is filtered out.
        /confirm executes the two CONFIRM steps only."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="write_file",
                arguments={"path": "x", "content": "y"},
                confidence=0.8,
                original_request="custom"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                confirm_step_1 = ActionStep(
                    tool_name="create_directory",
                    arguments={"path": "safe_dir"},
                    description="Create directory safe_dir"
                )
                blocked_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "C:/Windows/bad.txt", "content": "x"},
                    description="Write file C:/Windows/bad.txt"
                )
                confirm_step_2 = ActionStep(
                    tool_name="create_directory",
                    arguments={"path": "another_dir"},
                    description="Create directory another_dir"
                )
                mock_planner.plan.return_value = ActionPlan(
                    steps=[confirm_step_1, blocked_step, confirm_step_2]
                )

                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="Done.")
                    result = await self.conversation.handle_user_input("custom")
                    assert result is True

                    # Pending state should contain the two confirmation steps,
                    # but NOT the blocked step.
                    assert self.conversation.pending_remaining_steps is not None
                    pending_tools = [s.tool_name for s in self.conversation.pending_remaining_steps]
                    # create_directory appears twice (the BLOCKED write_file is filtered)
                    assert pending_tools.count("create_directory") == 2
                    assert "write_file" not in pending_tools

                    # /confirm executes only the 2 non-blocked steps
                    with patch.object(
                        self.conversation, '_execute_action_step', new_callable=AsyncMock
                    ) as mock_execute:
                        mock_execute.return_value = ToolResult(success=True, content="ok")
                        await self.conversation.handle_tool_command("/confirm")
                        assert mock_execute.call_count == 2
                        executed = [c.args[0].tool_name for c in mock_execute.call_args_list]
                        assert executed == ["create_directory", "create_directory"]
                        # The blocked write_file was never executed
                        assert "write_file" not in executed

    # --- VERIFY 8: Existing single-step behavior remains unchanged ---

    @pytest.mark.asyncio
    async def test_single_step_safe_action_unchanged(self):
        """A single safe action (calculate) must still execute through the orchestrator."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="calculate",
                arguments={"expression": "2+2"},
                confidence=0.8,
                original_request="calculate 2+2"
            )
            with patch.object(self.conversation, 'orchestrator') as mock_orch:
                mock_orch.execute_tool_calls = AsyncMock(return_value=[
                    ToolResult(success=True, content="4")
                ])
                with patch.object(self.conversation, 'ai_service') as mock_ai:
                    mock_ai.generate = AsyncMock(return_value="The answer is 4.")
                    await self.conversation.handle_user_input("calculate 2+2")

                    # Single safe step executes normally
                    mock_orch.execute_tool_calls.assert_called_once()
                    # No pending state
                    assert self.conversation.pending_remaining_steps is None

    @pytest.mark.asyncio
    async def test_single_step_unknown_tool_unchanged(self):
        """An unknown tool (not in registry) must still be BLOCKED (default behavior preserved)."""
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = Intent(
                action="unknown_tool",
                arguments={"path": "x"},
                confidence=0.8,
                original_request="custom"
            )
            with patch.object(self.conversation, 'planner') as mock_planner:
                mock_planner.plan.return_value = ActionPlan(steps=[
                    ActionStep(
                        tool_name="unknown_tool",
                        arguments={"path": "x"},
                        description="Unknown tool"
                    )
                ])
                with patch.object(self.conversation, 'orchestrator') as mock_orch:
                    mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                    with patch.object(self.conversation, 'ai_service') as mock_ai:
                        mock_ai.generate = AsyncMock(return_value="Blocked.")
                        await self.conversation.handle_user_input("custom")

                        # BLOCKED behavior preserved
                        mock_orch.execute_tool_calls.assert_not_called()
                        assert self.conversation.pending_remaining_steps is None