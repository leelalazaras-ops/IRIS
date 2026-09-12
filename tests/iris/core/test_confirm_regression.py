"""
Regression tests for the confirmation flow (Phase 7.5A / 7.5B / 7.5C).

Phase 7.5B: /confirm stops executing pending steps at the first failure
(failure-safe confirmation). Prior successful steps remain executed.

Phase 7.5C: /status is a read-only view of pending confirmation actions.
"""

from unittest.mock import AsyncMock, patch
import pytest

from iris.core.cli import IRISConversation
from iris.planning.models import ActionPlan, ActionStep
from iris.tools.base import ToolResult


class TestConfirmRegression:
    """Regression tests for /confirm and /cancel edge cases (Phase 7.5A/7.5B)."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        self.conversation.dry_run_mode = False

    def _make_step(self, tool_name="write_file", path="test.txt", **kwargs):
        """Helper to build an ActionStep."""
        arguments = {"path": path}
        if "content" in kwargs:
            arguments["content"] = kwargs["content"]
        return ActionStep(
            tool_name=tool_name,
            arguments=arguments,
            description=f"{tool_name}: {path}"
        )

    # 1. /confirm after /cancel is a no-op.

    @pytest.mark.asyncio
    async def test_confirm_after_cancel_is_no_op(self):
        """After /cancel clears pending state, a subsequent /confirm must not execute anything."""
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        # Cancel first
        await self.conversation.handle_tool_command("/cancel")
        assert self.conversation.pending_remaining_steps is None
        assert self.conversation.pending_plan is None

        # Now confirm - must be a no-op
        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            result = await self.conversation.handle_tool_command("/confirm")
            assert result is True
            mock_exec.assert_not_called()
            assert self.conversation.pending_remaining_steps is None

    # 2. Double /confirm is a no-op.

    @pytest.mark.asyncio
    async def test_double_confirm_is_no_op(self):
        """A second /confirm after the first one completed must not re-execute steps."""
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            # First confirm executes the step
            await self.conversation.handle_tool_command("/confirm")
            mock_exec.assert_called_once_with(pending_step)
            assert self.conversation.pending_remaining_steps is None

            # Second confirm is a no-op
            mock_exec.reset_mock()
            result = await self.conversation.handle_tool_command("/confirm")
            assert result is True
            mock_exec.assert_not_called()
            assert self.conversation.pending_remaining_steps is None

    # 3. SAFE -> CONFIRM -> BLOCKED keeps BLOCKED out of pending state.

    @pytest.mark.asyncio
    async def test_safe_confirm_blocked_keeps_blocked_out_of_pending(self):
        """Plan: [SAFE, CONFIRM, BLOCKED] -> pending holds SAFE+CONFIRM only; BLOCKED filtered out.

        Then /confirm executes exactly 2 steps and the BLOCKED step never runs.
        """
        with patch.object(self.conversation, '_create_intent_from_user_input') as mock_create_intent:
            mock_create_intent.return_value = _make_intent()
            with patch.object(self.conversation, 'planner') as mock_planner:
                safe_step = ActionStep(
                    tool_name="read_file",
                    arguments={"path": "input.txt"},
                    description="Read file: input.txt"
                )
                confirm_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "output.txt", "content": "hi"},
                    description="Write file: output.txt"
                )
                blocked_step = ActionStep(
                    tool_name="write_file",
                    arguments={"path": "C:/Windows/bad.txt", "content": "x"},
                    description="Write file: C:/Windows/bad.txt"
                )
                mock_planner.plan.return_value = ActionPlan(
                    steps=[safe_step, confirm_step, blocked_step]
                )

                with patch.object(self.conversation, 'safety_classifier') as mock_safety:
                    def requires_confirmation_side_effect(tool_name, args):
                        # write_file requires confirmation
                        return tool_name == "write_file"

                    def is_blocked_side_effect(tool_name, args):
                        # Only the Windows-path write is BLOCKED
                        return (
                            tool_name == "write_file"
                            and "windows" in str(args.get("path", "")).lower()
                        )

                    mock_safety.requires_confirmation.side_effect = requires_confirmation_side_effect
                    mock_safety.is_blocked.side_effect = is_blocked_side_effect

                    with patch.object(self.conversation, 'orchestrator') as mock_orch:
                        mock_orch.execute_tool_calls = AsyncMock(return_value=[])
                        with patch.object(self.conversation, 'ai_service') as mock_ai:
                            mock_ai.generate = AsyncMock(return_value="Done.")

                            await self.conversation.handle_user_input("placeholder")

                            # Pending state: SAFE + CONFIRM present, BLOCKED filtered out
                            pending = self.conversation.pending_remaining_steps
                            assert pending is not None
                            assert len(pending) == 2
                            assert pending[0].tool_name == "read_file"
                            assert pending[1].tool_name == "write_file"
                            paths = [s.arguments.get("path") for s in pending]
                            assert "C:/Windows/bad.txt" not in paths

                            # /confirm executes exactly the 2 non-blocked steps
                            with patch.object(
                                self.conversation, '_execute_action_step', new_callable=AsyncMock
                            ) as mock_exec:
                                mock_exec.return_value = ToolResult(success=True, content="ok")
                                await self.conversation.handle_tool_command("/confirm")
                                assert mock_exec.call_count == 2
                                executed_paths = [
                                    c.args[0].arguments.get("path") for c in mock_exec.call_args_list
                                ]
                                assert "C:/Windows/bad.txt" not in executed_paths

    # 4. Empty pending state / empty pending plan is a no-op.

    @pytest.mark.asyncio
    async def test_confirm_with_empty_pending_list_is_no_op(self):
        """Empty pending list (not None) - /confirm must be a no-op, not crash."""
        self.conversation.pending_remaining_steps = []
        self.conversation.pending_plan = ActionPlan(steps=[])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            result = await self.conversation.handle_tool_command("/confirm")
            assert result is True
            mock_exec.assert_not_called()
            assert self.conversation.pending_remaining_steps is None

    # 5. /confirm with trailing whitespace behaves consistently with the command parser.

    @pytest.mark.asyncio
    async def test_confirm_with_trailing_whitespace(self):
        """/confirm with trailing whitespace is parsed the same as /confirm."""
        # The command parser strips input before dispatch, so "/confirm "
        # must be routed to the confirm branch. With pending state set,
        # the step must execute - proving whitespace did not break parsing.
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            result = await self.conversation.handle_tool_command("/confirm ")
            assert result is True
            # Parsed as /confirm -> step executed (whitespace not part of command name)
            mock_exec.assert_called_once()
            assert self.conversation.pending_remaining_steps is None

    # 6. Confirm execution failure has explicit regression coverage.

    @pytest.mark.asyncio
    async def test_confirm_execution_failure_clears_pending(self):
        """When a pending step fails during /confirm, pending state is still cleared.

        Phase 7.5B: a failing step stops the /confirm loop; the failure is
        reported normally and the pending state is cleared.
        """
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(success=False, content=None, error="Permission denied")
            await self.conversation.handle_tool_command("/confirm")
            mock_exec.assert_called_once_with(pending_step)
            # Pending state is cleared even on failure
            assert self.conversation.pending_remaining_steps is None
            assert self.conversation.pending_plan is None

    @pytest.mark.asyncio
    async def test_confirm_failure_stops_remaining_steps(self):
        """When the FIRST pending step fails, subsequent pending steps must NOT execute.

        Plan: [FAIL, OK] -> /confirm executes only the failing step, then
        stops (Phase 7.5B failure-safe confirmation) and clears pending state.
        """
        fail_step = self._make_step(path="fail.txt")
        ok_step = self._make_step(path="ok.txt")
        self.conversation.pending_remaining_steps = [fail_step, ok_step]
        self.conversation.pending_plan = ActionPlan(steps=[fail_step, ok_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = [
                ToolResult(success=False, content=None, error="Permission denied"),
                ToolResult(success=True, content="ok"),
            ]
            await self.conversation.handle_tool_command("/confirm")

            # Only the failing step was attempted; the later step never runs
            assert mock_exec.call_count == 1
            assert mock_exec.call_args_list[0].args[0] is fail_step
            # Pending state is cleared after the failure
            assert self.conversation.pending_remaining_steps is None
            assert self.conversation.pending_plan is None

    @pytest.mark.asyncio
    async def test_confirm_failure_keeps_earlier_successful_steps(self):
        """Steps that succeeded before a failure remain executed (no rollback).

        Plan: [OK, FAIL, NEVER] -> /confirm executes OK and FAIL, then stops;
        the third step never runs. The earlier success is not rolled back.
        """
        ok_step = self._make_step(path="ok.txt")
        fail_step = self._make_step(path="fail.txt")
        never_step = self._make_step(path="never.txt")
        self.conversation.pending_remaining_steps = [ok_step, fail_step, never_step]
        self.conversation.pending_plan = ActionPlan(
            steps=[ok_step, fail_step, never_step]
        )

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = [
                ToolResult(success=True, content="ok"),
                ToolResult(success=False, content=None, error="Permission denied"),
                ToolResult(success=True, content="never"),
            ]
            await self.conversation.handle_tool_command("/confirm")

            # Execution stopped at the failing step: [OK, FAIL] attempted, NEVER skipped
            assert mock_exec.call_count == 2
            called_paths = [c.args[0].arguments.get("path") for c in mock_exec.call_args_list]
            assert called_paths == ["ok.txt", "fail.txt"]
            # Pending state cleared
            assert self.conversation.pending_remaining_steps is None
            assert self.conversation.pending_plan is None


class TestStatusCommand:
    """Regression tests for the /status command (Phase 7.5C)."""

    def setup_method(self):
        """Set up a fresh conversation for each test."""
        self.conversation = IRISConversation()
        self.conversation.conversation_history = []
        self.conversation.tools_enabled = True
        self.conversation.dry_run_mode = False

    def _make_step(self, tool_name="write_file", path="test.txt", **kwargs):
        """Helper to build an ActionStep."""
        arguments = {"path": path}
        if "content" in kwargs:
            arguments["content"] = kwargs["content"]
        return ActionStep(
            tool_name=tool_name,
            arguments=arguments,
            description=f"{tool_name}: {path}"
        )

    @pytest.mark.asyncio
    async def test_status_no_pending_actions(self):
        """When no pending actions exist, /status shows 'No pending confirmation actions.'"""
        self.conversation.pending_remaining_steps = None
        self.conversation.pending_plan = None

        # Capture output
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        await self.conversation.handle_tool_command("/status")

        sys.stdout = old_stdout
        output = buffer.getvalue()

        assert "No pending confirmation actions." in output
        # Should not crash and should return True
        assert await self.conversation.handle_tool_command("/status") is True

    @pytest.mark.asyncio
    async def test_status_one_pending_action(self):
        """With one pending action, /status shows count and description."""
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        # Capture output
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        await self.conversation.handle_tool_command("/status")

        sys.stdout = old_stdout
        output = buffer.getvalue()

        assert "⚠️  Confirmation pending (1 action)" in output
        assert pending_step.description in output
        assert await self.conversation.handle_tool_command("/status") is True

    @pytest.mark.asyncio
    async def test_status_multiple_pending_actions_in_order(self):
        """With multiple pending actions, /status shows them in correct order."""
        step1 = self._make_step(path="first.txt")
        step2 = self._make_step(path="second.txt")
        step3 = self._make_step(path="third.txt")
        self.conversation.pending_remaining_steps = [step1, step2, step3]
        self.conversation.pending_plan = ActionPlan(steps=[step1, step2, step3])

        # Capture output
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        await self.conversation.handle_tool_command("/status")

        sys.stdout = old_stdout
        output = buffer.getvalue()

        assert "⚠️  Confirmation pending (3 actions)" in output
        lines = output.strip().split('\n')
        # Find the lines with step descriptions
        step_lines = [line for line in lines if '. ' in line and ('write_file:' in line or 'first.txt' in line or 'second.txt' in line or 'third.txt' in line)]
        assert len(step_lines) == 3
        assert "1. write_file: first.txt" in step_lines[0] or "first.txt" in step_lines[0]
        assert "2. write_file: second.txt" in step_lines[1] or "second.txt" in step_lines[1]
        assert "3. write_file: third.txt" in step_lines[2] or "third.txt" in step_lines[2]
        assert await self.conversation.handle_tool_command("/status") is True

    @pytest.mark.asyncio
    async def test_status_does_not_execute_pending_actions(self):
        """Calling /status does not execute any of the pending actions."""
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            await self.conversation.handle_tool_command("/status")
            mock_exec.assert_not_called()
            # State should remain unchanged
            assert self.conversation.pending_remaining_steps == [pending_step]
            assert self.conversation.pending_plan is not None

    @pytest.mark.asyncio
    async def test_status_does_not_clear_pending_state(self):
        """Calling /status does not clear the pending state."""
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        await self.conversation.handle_tool_command("/status")
        # State should remain unchanged
        assert self.conversation.pending_remaining_steps == [pending_step]
        assert self.conversation.pending_plan is not None
        # Calling again should still show the same state
        await self.conversation.handle_tool_command("/status")
        assert self.conversation.pending_remaining_steps == [pending_step]
        assert self.conversation.pending_plan is not None


def _make_intent():
    """Build a high-confidence intent for the pipeline tests."""
    from iris.intent.models import Intent
    return Intent(
        action="write_file",
        arguments={"path": "output.txt", "content": "hi"},
        confidence=0.8,
        original_request="placeholder"
    )
