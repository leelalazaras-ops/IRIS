"""
Regression tests for the confirmation flow (Phase 7.5A).

Add tests ONLY - do not modify production code.
"""

from unittest.mock import AsyncMock, patch
import pytest

from iris.core.cli import IRISConversation
from iris.planning.models import ActionPlan, ActionStep
from iris.tools.base import ToolResult


class TestConfirmRegression:
    """Regression tests for /confirm and /cancel edge cases (Phase 7.5A)."""

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

        This documents CURRENT behavior (all steps attempted, state cleared
        after the loop). Production behavior is NOT changed by this test.
        """
        pending_step = self._make_step()
        self.conversation.pending_remaining_steps = [pending_step]
        self.conversation.pending_plan = ActionPlan(steps=[pending_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(success=False, content=None, error="Permission denied")
            await self.conversation.handle_tool_command("/confirm")
            mock_exec.assert_called_once_with(pending_step)
            # Pending state is cleared even on failure (documents current behavior)
            assert self.conversation.pending_remaining_steps is None
            assert self.conversation.pending_plan is None

    @pytest.mark.asyncio
    async def test_confirm_failure_continues_remaining_steps(self):
        """When the FIRST pending step fails, later pending steps still execute (current behavior).

        Plan: [FAIL, OK] -> /confirm attempts both; documents the continuation
        behavior for regression tracking. Production behavior is NOT changed.
        """
        fail_step = self._make_step(path="fail.txt")
        ok_step = self._make_step(path="ok.txt")
        self.conversation.pending_remaining_steps = [fail_step, ok_step]
        self.conversation.pending_plan = ActionPlan(steps=[fail_step, ok_step])

        with patch.object(self.conversation, "_execute_action_step", new_callable=AsyncMock) as mock_exec:
            # First call fails, second succeeds
            mock_exec.side_effect = [
                ToolResult(success=False, content=None, error="Permission denied"),
                ToolResult(success=True, content="ok"),
            ]
            await self.conversation.handle_tool_command("/confirm")

            # Both steps were attempted (current behavior: continue after failure)
            assert mock_exec.call_count == 2
            called_paths = [c.args[0].arguments.get("path") for c in mock_exec.call_args_list]
            assert called_paths == ["fail.txt", "ok.txt"]
            # State cleared after the loop
            assert self.conversation.pending_remaining_steps is None


def _make_intent():
    """Build a high-confidence intent for the pipeline tests."""
    from iris.intent.models import Intent
    return Intent(
        action="write_file",
        arguments={"path": "output.txt", "content": "hi"},
        confidence=0.8,
        original_request="placeholder"
    )
