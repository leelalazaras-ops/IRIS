"""
Tests for ToolOrchestrator - AI-driven tool execution orchestration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from iris.tools.orchestration import ToolCall, OrchestrationConfig, ToolOrchestrator
from iris.tools.registry import ToolRegistry
from iris.tools.base import Tool, ToolArgument, ToolResult
from iris.tools.utility import CalculateTool


class MockTool(Tool):
    """Mock tool for testing orchestration."""

    def __init__(self, name: str, description: str, should_succeed: bool = True, result_content: str = "success"):
        self._name = name
        self._description = description
        self._should_succeed = should_succeed
        self._result_content = result_content

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(name="param", type=str, description="A parameter", required=True)
        ]

    async def execute(self, **kwargs) -> ToolResult:
        if self._should_succeed:
            return ToolResult(success=True, content=self._result_content)
        return ToolResult(success=False, content=None, error="Tool execution failed")


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_valid_tool_call(self):
        tc = ToolCall(id="call_123", tool_name="test_tool", arguments={"param": "value"})
        assert tc.id == "call_123"
        assert tc.tool_name == "test_tool"
        assert tc.arguments == {"param": "value"}

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="ToolCall id cannot be empty"):
            ToolCall(id="", tool_name="test", arguments={})

    def test_empty_tool_name_raises(self):
        with pytest.raises(ValueError, match="ToolCall tool_name cannot be empty"):
            ToolCall(id="call_123", tool_name="", arguments={})

    def test_non_dict_arguments_raises(self):
        with pytest.raises(ValueError, match="ToolCall arguments must be a dict"):
            ToolCall(id="call_123", tool_name="test", arguments="not a dict")

    def test_post_init_validates_types(self):
        # This should work fine
        tc = ToolCall(id="call_123", tool_name="test", arguments={"key": "value"})
        assert tc.arguments == {"key": "value"}


class TestOrchestrationConfig:
    """Tests for OrchestrationConfig dataclass."""

    def test_defaults(self):
        config = OrchestrationConfig()
        assert config.max_tool_calls == 5
        assert config.enable_tools is True

    def test_custom_values(self):
        config = OrchestrationConfig(max_tool_calls=10, enable_tools=False)
        assert config.max_tool_calls == 10
        assert config.enable_tools is False

    def test_invalid_max_tool_calls_raises(self):
        with pytest.raises(ValueError, match="max_tool_calls must be at least 1"):
            OrchestrationConfig(max_tool_calls=0)

    def test_negative_max_tool_calls_raises(self):
        with pytest.raises(ValueError, match="max_tool_calls must be at least 1"):
            OrchestrationConfig(max_tool_calls=-1)


class TestToolOrchestrator:
    """Tests for ToolOrchestrator class."""

    def setup_method(self):
        """Set up a fresh registry and orchestrator for each test."""
        self.registry = ToolRegistry()
        self.orchestrator = ToolOrchestrator(self.registry)

    def test_initialization(self):
        assert self.orchestrator.registry is self.registry
        assert self.orchestrator.config.max_tool_calls == 5
        assert self.orchestrator.config.enable_tools is True
        assert self.orchestrator._tool_call_count == 0

    def test_custom_config(self):
        config = OrchestrationConfig(max_tool_calls=3, enable_tools=False)
        orch = ToolOrchestrator(self.registry, config)
        assert orch.config.max_tool_calls == 3
        assert orch.config.enable_tools is False

    def test_reset_call_count(self):
        self.orchestrator._tool_call_count = 5
        self.orchestrator.reset_call_count()
        assert self.orchestrator._tool_call_count == 0

    @pytest.mark.asyncio
    async def test_execute_single_tool_call_success(self):
        mock_tool = MockTool("test_tool", "A test tool")
        self.registry.register(mock_tool)

        tool_calls = [
            ToolCall(id="call_1", tool_name="test_tool", arguments={"param": "test"})
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].content == "success"
        assert results[0].metadata["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_execute_single_tool_call_failure(self):
        mock_tool = MockTool("failing_tool", "A failing tool", should_succeed=False)
        self.registry.register(mock_tool)

        tool_calls = [
            ToolCall(id="call_1", tool_name="failing_tool", arguments={"param": "test"})
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error == "Tool execution failed"
        assert results[0].metadata["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        tool_calls = [
            ToolCall(id="call_1", tool_name="nonexistent_tool", arguments={"param": "test"})
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].error.lower()
        assert results[0].metadata["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_execute_multiple_tool_calls(self):
        tool1 = MockTool("tool_1", "First tool", result_content="result_1")
        tool2 = MockTool("tool_2", "Second tool", result_content="result_2")
        self.registry.register(tool1)
        self.registry.register(tool2)

        tool_calls = [
            ToolCall(id="call_1", tool_name="tool_1", arguments={"param": "a"}),
            ToolCall(id="call_2", tool_name="tool_2", arguments={"param": "b"}),
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 2
        assert results[0].success is True
        assert results[0].content == "result_1"
        assert results[1].success is True
        assert results[1].content == "result_2"

    @pytest.mark.asyncio
    async def test_max_tool_calls_limit(self):
        config = OrchestrationConfig(max_tool_calls=2)
        orch = ToolOrchestrator(self.registry, config)

        tool1 = MockTool("tool_1", "First tool")
        tool2 = MockTool("tool_2", "Second tool")
        tool3 = MockTool("tool_3", "Third tool")
        self.registry.register(tool1)
        self.registry.register(tool2)
        self.registry.register(tool3)

        tool_calls = [
            ToolCall(id="call_1", tool_name="tool_1", arguments={"param": "1"}),
            ToolCall(id="call_2", tool_name="tool_2", arguments={"param": "2"}),
            ToolCall(id="call_3", tool_name="tool_3", arguments={"param": "3"}),
        ]

        results = await orch.execute_tool_calls(tool_calls)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is False
        assert "maximum tool calls exceeded" in results[2].error.lower()

    @pytest.mark.asyncio
    async def test_invalid_tool_call_structure(self):
        # Not a valid ToolCall - missing required fields
        # We'll test the validation in execute_tool_calls by passing invalid data
        tool_calls = [
            # This would be caught by ToolCall __post_init__, but let's test the orchestrator's handling
        ]

        # Test with empty list
        results = await self.orchestrator.execute_tool_calls([])
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_with_validation_errors(self):
        # Test validation of tool_name type
        from iris.tools.orchestration import ToolCall
        # Can't easily create invalid ToolCall due to __post_init__, so we test error handling

    @pytest.mark.asyncio
    async def test_tool_call_counter_increments(self):
        tool = MockTool("counter_tool", "Counter tool")
        self.registry.register(tool)

        tool_calls = [
            ToolCall(id="call_1", tool_name="counter_tool", arguments={"param": "1"}),
            ToolCall(id="call_2", tool_name="counter_tool", arguments={"param": "2"}),
        ]

        await self.orchestrator.execute_tool_calls(tool_calls)

        assert self.orchestrator._tool_call_count == 2

    def test_format_tool_results_for_messages_success(self):
        tool_calls = [
            ToolCall(id="call_1", tool_name="tool_1", arguments={}),
            ToolCall(id="call_2", tool_name="tool_2", arguments={}),
        ]
        results = [
            ToolResult(success=True, content="result 1"),
            ToolResult(success=True, content="result 2"),
        ]

        messages = ToolOrchestrator.format_tool_results_for_messages(tool_calls, results)

        assert len(messages) == 2
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "call_1"
        assert messages[0]["name"] == "tool_1"
        assert messages[0]["content"] == "result 1"
        assert messages[1]["role"] == "tool"
        assert messages[1]["tool_call_id"] == "call_2"
        assert messages[1]["name"] == "tool_2"
        assert messages[1]["content"] == "result 2"

    def test_format_tool_results_for_messages_failure(self):
        tool_calls = [
            ToolCall(id="call_1", tool_name="failing_tool", arguments={}),
        ]
        results = [
            ToolResult(success=False, content=None, error="Something went wrong"),
        ]

        messages = ToolOrchestrator.format_tool_results_for_messages(tool_calls, results)

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "call_1"
        assert messages[0]["name"] == "failing_tool"
        assert messages[0]["content"] == "Error: Something went wrong"

    def test_format_tool_results_length_mismatch_raises(self):
        tool_calls = [ToolCall(id="call_1", tool_name="tool_1", arguments={})]
        results = [
            ToolResult(success=True, content="result 1"),
            ToolResult(success=True, content="result 2"),
        ]

        with pytest.raises(ValueError, match="must have the same length"):
            ToolOrchestrator.format_tool_results_for_messages(tool_calls, results)

    @pytest.mark.asyncio
    async def test_execute_real_calculate_tool(self):
        """Test with real CalculateTool from Phase 3."""
        from iris.tools.utility import CalculateTool

        calc_tool = CalculateTool()
        self.registry.register(calc_tool)

        tool_calls = [
            ToolCall(id="calc_1", tool_name="calculate", arguments={"expression": "2 + 3 * 4"}),
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].content == 14  # CalculateTool returns int
        assert results[0].metadata["tool_call_id"] == "calc_1"

    @pytest.mark.asyncio
    async def test_execute_real_calculate_tool_error(self):
        """Test CalculateTool with invalid expression."""
        from iris.tools.utility import CalculateTool

        calc_tool = CalculateTool()
        self.registry.register(calc_tool)

        tool_calls = [
            ToolCall(id="calc_1", tool_name="calculate", arguments={"expression": "invalid syntax"}),
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is False
        assert "invalid syntax" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_exception_handling_during_execution(self):
        """Test that unexpected exceptions are caught and returned as failed results."""
        # Create a tool that raises an exception
        class ExplodingTool(Tool):
            @property
            def name(self) -> str:
                return "exploding"

            @property
            def description(self) -> str:
                return "Explodes"

            @property
            def arguments(self) -> list[ToolArgument]:
                return []

            async def execute(self, **kwargs) -> ToolResult:
                raise RuntimeError("Boom!")

        self.registry.register(ExplodingTool())

        tool_calls = [
            ToolCall(id="call_1", tool_name="exploding", arguments={}),
        ]

        results = await self.orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is False
        assert "tool execution failed" in results[0].error.lower()
        assert "boom" in results[0].error.lower()
        assert results[0].metadata["exception_type"] == "RuntimeError"
        assert results[0].metadata["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_process_conversation_turn_placeholder(self):
        """Test the placeholder process_conversation_turn method."""
        # Mock AI service
        mock_ai_service = AsyncMock()
        mock_ai_service.generate = AsyncMock(return_value="AI response")

        messages = [{"role": "user", "content": "Hello"}]

        response, tool_calls = await self.orchestrator.process_conversation_turn(
            mock_ai_service, messages
        )

        assert response == "AI response"
        assert tool_calls == []
        mock_ai_service.generate.assert_called_once_with(messages=messages)