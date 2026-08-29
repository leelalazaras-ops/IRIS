"""
Tests for CLI tool integration.
"""

import pytest
from iris.core.cli import IRISConversation
from iris.tools.registry import ToolRegistry


class TestCLIToolIntegration:
    """Tests for tool integration with CLI."""

    def test_cli_initializes_tool_registry(self):
        """Test that CLI initializes tool registry."""
        conversation = IRISConversation()

        assert conversation.tool_registry is not None
        assert isinstance(conversation.tool_registry, ToolRegistry)

    def test_cli_registers_all_tools(self):
        """Test that all expected tools are registered."""
        conversation = IRISConversation()
        registry = conversation.tool_registry

        expected_tools = [
            "list_directory",
            "create_directory",
            "read_file",
            "write_file",
            "get_system_info",
            "get_current_directory",
            "get_environment_info",
            "get_current_time",
            "calculate",
        ]

        tool_names = registry.get_tool_names()

        for tool_name in expected_tools:
            assert tool_name in tool_names

        assert len(tool_names) == len(expected_tools)

    @pytest.mark.asyncio
    async def test_handle_tools_command(self, capsys):
        """Test /tools command lists all tools."""
        conversation = IRISConversation()

        should_continue = await conversation.handle_tool_command("/tools")

        assert should_continue is True

        captured = capsys.readouterr()
        output = captured.out

        # Should show available tools
        assert "Available Tools" in output
        assert "list_directory" in output
        assert "calculate" in output
        assert "get_system_info" in output

    @pytest.mark.asyncio
    async def test_handle_help_command(self, capsys):
        """Test /help command shows help."""
        conversation = IRISConversation()

        should_continue = await conversation.handle_tool_command("/help")

        assert should_continue is True

        captured = capsys.readouterr()
        output = captured.out

        # Should show commands
        assert "Commands" in output or "help" in output.lower()
        assert "/tools" in output

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, capsys):
        """Test unknown command shows error."""
        conversation = IRISConversation()

        should_continue = await conversation.handle_tool_command("/unknown")

        assert should_continue is True

        captured = capsys.readouterr()
        output = captured.out

        assert "Unknown command" in output or "unknown" in output.lower()

    @pytest.mark.asyncio
    async def test_regular_conversation_still_works(self, monkeypatch):
        """Test that regular conversation flow is not broken."""
        # Set up mock provider
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Regular message should work
        should_continue = await conversation.handle_user_input("Hello")

        assert should_continue is True
        assert len(conversation.conversation_history) == 2  # User + assistant

    @pytest.mark.asyncio
    async def test_tool_command_does_not_affect_conversation_history(self, monkeypatch):
        """Test that tool commands don't affect conversation history."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        # Add a regular message
        await conversation.handle_user_input("Hello")
        initial_length = len(conversation.conversation_history)

        # Tool command should not add to history
        await conversation.handle_user_input("/tools")

        assert len(conversation.conversation_history) == initial_length

    @pytest.mark.asyncio
    async def test_empty_input_handling(self, monkeypatch):
        """Test empty input is handled correctly."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        should_continue = await conversation.handle_user_input("")

        assert should_continue is True
        assert len(conversation.conversation_history) == 0

    @pytest.mark.asyncio
    async def test_exit_command_still_works(self, monkeypatch):
        """Test that exit command still works."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        should_continue = await conversation.handle_user_input("exit")

        assert should_continue is False

    @pytest.mark.asyncio
    async def test_quit_command_still_works(self, monkeypatch):
        """Test that quit command still works."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        conversation = IRISConversation()
        await conversation.initialize()

        should_continue = await conversation.handle_user_input("quit")

        assert should_continue is False
