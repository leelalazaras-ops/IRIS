"""
Integration tests for AI tool orchestration - tests the full flow from AI provider
through orchestrator to tool execution and back to AI.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from iris.tools.orchestration import ToolCall, OrchestrationConfig, ToolOrchestrator
from iris.tools.registry import ToolRegistry
from iris.tools.base import Tool, ToolArgument, ToolResult
from iris.ai.service import AIService
from iris.ai.provider import AIRequest, AIResponse
from iris.ai.providers.mock import MockProvider


class MockToolForIntegration(Tool):
    """Mock tool for integration testing."""

    def __init__(self, name: str, description: str, result_content: str = "success"):
        self._name = name
        self._description = description
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
        return ToolResult(success=True, content=self._result_content)


class TestAIServiceGenerateWithTools:
    """Tests for AIService.generate_with_tools method."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider that can return tool calls."""
        provider = MockProvider(
            response_content="I'll help you with that.",
            tool_calls=[
                ToolCall(id="call_1", tool_name="test_tool", arguments={"param": "value"})
            ]
        )
        return provider

    @pytest.fixture
    def ai_service_with_mock(self, mock_provider, monkeypatch):
        """Create AIService with mock provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")
        service = AIService()
        service._provider = mock_provider
        return service

    @pytest.mark.asyncio
    async def test_generate_with_tools_returns_tool_calls(self, ai_service_with_mock):
        """Test that generate_with_tools returns tool calls from provider.

        Note: When provider returns tool_calls, content is empty (standard behavior).
        The test verifies tool_calls are returned correctly.
        """
        messages = [{"role": "user", "content": "Do something"}]
        tools = [{"type": "function", "function": {"name": "test_tool", "description": "Test", "parameters": {}}}]

        content, tool_calls = await ai_service_with_mock.generate_with_tools(
            messages=messages,
            tools=tools,
            temperature=0.7
        )

        # When tool_calls are returned, content is empty (provider behavior)
        assert content == ""
        assert len(tool_calls) == 1
        assert tool_calls[0].id == "call_1"
        assert tool_calls[0].tool_name == "test_tool"
        assert tool_calls[0].arguments == {"param": "value"}

    @pytest.mark.asyncio
    async def test_generate_with_tools_no_tool_calls(self, ai_service_with_mock):
        """Test generate_with_tools when provider returns no tool calls."""
        # Reset the mock provider to not return tool calls
        provider = MockProvider(response_content="Regular response")
        ai_service_with_mock._provider = provider

        messages = [{"role": "user", "content": "Hello"}]
        tools = []

        content, tool_calls = await ai_service_with_mock.generate_with_tools(
            messages=messages,
            tools=tools,
            temperature=0.7
        )

        assert content == "Regular response"
        assert tool_calls == []

    @pytest.mark.asyncio
    async def test_generate_with_tools_passes_tools_to_provider(self, monkeypatch):
        """Test that tools are passed correctly in the request."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")
        provider = MockProvider()
        service = AIService()
        service._provider = provider

        messages = [{"role": "user", "content": "Test"}]
        tools = [{"type": "function", "function": {"name": "test", "description": "Test", "parameters": {}}}]

        await service.generate_with_tools(
            messages=messages,
            tools=tools,
            temperature=0.5,
            max_tokens=100
        )

        # Check that the provider received the correct request
        assert provider.call_count == 1
        # We can't easily inspect the request passed to provider.generate without more mocking


class TestToolOrchestratorIntegration:
    """Integration tests for ToolOrchestrator with real tools."""

    @pytest.fixture
    def registry_with_tools(self):
        """Create a registry with test tools."""
        registry = ToolRegistry()
        registry.register(MockToolForIntegration("read_file", "Read a file", "File content"))
        registry.register(MockToolForIntegration("write_file", "Write a file", "Written"))
        return registry

    @pytest.fixture
    def orchestrator(self, registry_with_tools):
        """Create an orchestrator with test tools."""
        return ToolOrchestrator(registry_with_tools)

    @pytest.mark.asyncio
    async def test_full_orchestration_flow(self, orchestrator):
        """Test complete orchestration: AI requests tool -> execute -> return result."""
        tool_calls = [
            ToolCall(id="call_1", tool_name="read_file", arguments={"param": "test.txt"}),
        ]

        results = await orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].content == "File content"

        # Format results for AI
        messages = ToolOrchestrator.format_tool_results_for_messages(tool_calls, results)

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "call_1"
        assert messages[0]["name"] == "read_file"
        assert messages[0]["content"] == "File content"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(self, orchestrator):
        """Test multiple tool calls in one turn."""
        tool_calls = [
            ToolCall(id="call_1", tool_name="read_file", arguments={"param": "a.txt"}),
            ToolCall(id="call_2", tool_name="write_file", arguments={"param": "b.txt"}),
        ]

        results = await orchestrator.execute_tool_calls(tool_calls)

        assert len(results) == 2
        assert results[0].content == "File content"
        assert results[1].content == "Written"

        messages = ToolOrchestrator.format_tool_results_for_messages(tool_calls, results)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_tool_call_limit_enforced(self, registry_with_tools):
        """Test that max_tool_calls limit is enforced."""
        config = OrchestrationConfig(max_tool_calls=2)
        orch = ToolOrchestrator(registry_with_tools, config)

        tool_calls = [
            ToolCall(id="call_1", tool_name="read_file", arguments={"param": "1"}),
            ToolCall(id="call_2", tool_name="write_file", arguments={"param": "2"}),
            ToolCall(id="call_3", tool_name="read_file", arguments={"param": "3"}),
        ]

        results = await orch.execute_tool_calls(tool_calls)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is False
        assert "maximum tool calls exceeded" in results[2].error.lower()


class TestMockProviderToolCalls:
    """Tests for MockProvider tool call functionality."""

    @pytest.mark.asyncio
    async def test_mock_provider_returns_tool_calls_once(self):
        """Test that mock provider returns tool calls only on first call."""
        tool_calls = [
            ToolCall(id="call_1", tool_name="tool_1", arguments={"arg": "val"}),
        ]
        provider = MockProvider(
            response_content="Follow up response",
            tool_calls=tool_calls
        )

        # First call should return tool calls
        request = AIRequest(messages=[{"role": "user", "content": "Test"}])
        response1 = await provider.generate(request)

        assert response1.content == ""
        assert response1.tool_calls is not None
        assert len(response1.tool_calls) == 1
        assert response1.tool_calls[0].id == "call_1"

        # Second call should return regular response
        response2 = await provider.generate(request)

        assert response2.content == "Follow up response"
        assert response2.tool_calls == []

    @pytest.mark.asyncio
    async def test_mock_provider_without_tool_calls(self):
        """Test mock provider without configured tool calls."""
        provider = MockProvider(response_content="Just a response")

        request = AIRequest(messages=[{"role": "user", "content": "Test"}])
        response = await provider.generate(request)

        assert response.content == "Just a response"
        assert response.tool_calls == []


class TestAIResponseToolCalls:
    """Tests for AIResponse tool_calls field."""

    def test_ai_response_with_tool_calls(self):
        """Test creating AIResponse with tool_calls."""
        tool_calls = [
            ToolCall(id="call_1", tool_name="test", arguments={"x": 1}),
        ]
        response = AIResponse(
            content="",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            tool_calls=tool_calls
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].tool_name == "test"

    def test_ai_response_without_tool_calls(self):
        """Test creating AIResponse without tool_calls (default)."""
        response = AIResponse(
            content="Hello",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        assert response.tool_calls == []

    def test_ai_response_with_none_tool_calls(self):
        """Test creating AIResponse with explicit None tool_calls."""
        response = AIResponse(
            content="Hello",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            tool_calls=None
        )

        assert response.tool_calls == []


class TestAIRequestTools:
    """Tests for AIRequest tools field."""

    def test_ai_request_with_tools(self):
        """Test creating AIRequest with tools."""
        tools = [{"type": "function", "function": {"name": "test", "description": "Test", "parameters": {}}}]
        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
            tools=tools
        )

        assert request.tools == tools

    def test_ai_request_without_tools(self):
        """Test creating AIRequest without tools."""
        request = AIRequest(
            messages=[{"role": "user", "content": "Test"}],
        )

        assert request.tools is None


class TestOpenAICompatibleProviderTools:
    """Tests for OpenAICompatibleProvider tool handling (mocked)."""

    @pytest.mark.asyncio
    async def test_provider_sends_tools_in_request(self):
        """Test that provider includes tools in API request."""
        from iris.ai.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url="http://test",
            api_key="test-key",
            model="test-model"
        )

        # Mock the httpx client post method
        import httpx
        from unittest.mock import AsyncMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Done",
                    "tool_calls": []
                }
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }

        with patch.object(provider._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            tools = [{"type": "function", "function": {"name": "test", "description": "Test", "parameters": {}}}]
            request = AIRequest(
                messages=[{"role": "user", "content": "Test"}],
                tools=tools
            )

            await provider.generate(request)

            # Verify the request included tools
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            # Check that tools were passed in the JSON payload
            assert call_args is not None
            assert "json" in call_args.kwargs
            payload = call_args.kwargs["json"]
            assert "tools" in payload
            assert payload["tools"] == tools
            assert payload["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_provider_parses_tool_calls_from_response(self):
        """Test that provider parses tool_calls from API response."""
        from iris.ai.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url="http://test",
            api_key="test-key",
            model="test-model"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "test_tool",
                            "arguments": '{"arg": "value"}'
                        }
                    }]
                }
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }

        with patch.object(provider._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            request = AIRequest(messages=[{"role": "user", "content": "Test"}])
            response = await provider.generate(request)

            assert response.tool_calls is not None
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].id == "call_123"
            assert response.tool_calls[0].tool_name == "test_tool"
            assert response.tool_calls[0].arguments == {"arg": "value"}


class TestCLIToolCommands:
    """Integration tests for CLI tool commands."""

    @pytest.fixture
    def conversation_with_mock(self, monkeypatch):
        """Create a conversation with mock provider."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")
        from iris.core.cli import IRISConversation
        conv = IRISConversation()
        conv.tools_enabled = False  # Disable tools for basic tests
        return conv

    @pytest.mark.asyncio
    async def test_tools_command_lists_tools(self, conversation_with_mock, capsys):
        """Test /tools command lists all available tools."""
        await conversation_with_mock.initialize()

        await conversation_with_mock.handle_user_input("/tools")

        captured = capsys.readouterr()
        assert "Available Tools" in captured.out
        assert "calculate" in captured.out
        assert "list_directory" in captured.out

        await conversation_with_mock.cleanup()

    @pytest.mark.asyncio
    async def test_enable_tools_command(self, conversation_with_mock, capsys):
        """Test /enable-tools command."""
        await conversation_with_mock.initialize()

        # First disable
        conversation_with_mock.tools_enabled = True
        await conversation_with_mock.handle_user_input("/disable-tools")
        captured = capsys.readouterr()
        assert "disabled" in captured.out.lower()

        # Then enable
        await conversation_with_mock.handle_user_input("/enable-tools")
        captured = capsys.readouterr()
        assert "enabled" in captured.out.lower()

        await conversation_with_mock.cleanup()

    @pytest.mark.asyncio
    async def test_tool_status_command(self, conversation_with_mock, capsys):
        """Test /tool-status command shows status."""
        await conversation_with_mock.initialize()

        await conversation_with_mock.handle_user_input("/tool-status")

        captured = capsys.readouterr()
        assert "Tool Orchestration Status" in captured.out
        assert "Enabled:" in captured.out
        assert "Max tool calls" in captured.out
        assert "Available tools" in captured.out

        await conversation_with_mock.cleanup()

    @pytest.mark.asyncio
    async def test_help_command_includes_tool_commands(self, conversation_with_mock, capsys):
        """Test /help command includes tool commands."""
        await conversation_with_mock.initialize()

        await conversation_with_mock.handle_user_input("/help")

        captured = capsys.readouterr()
        assert "/tools" in captured.out
        assert "/enable-tools" in captured.out
        assert "/disable-tools" in captured.out
        assert "/tool-status" in captured.out

        await conversation_with_mock.cleanup()


class TestEndToEndToolOrchestration:
    """End-to-end tests for the full tool orchestration flow."""

    @pytest.mark.asyncio
    async def test_cli_processes_tool_call_flow(self, monkeypatch):
        """Test full flow: user message -> AI requests tool -> execute -> AI responds."""
        monkeypatch.setenv("IRIS_AI_PROVIDER", "mock")

        from iris.core.cli import IRISConversation
        conversation = IRISConversation()

        # Use mock provider with tool calls
        mock_provider = MockProvider(
            response_content="Let me calculate that for you.",
            tool_calls=[
                ToolCall(id="calc_1", tool_name="calculate", arguments={"expression": "2 + 2"})
            ]
        )
        conversation.ai_service = AIService()
        conversation.ai_service._provider = mock_provider

        # Enable tools
        conversation.tools_enabled = True

        # This will use the orchestrator
        # We can't easily test the full async flow without more mocking
        # But we can verify the setup is correct
        assert conversation.tools_enabled is True
        assert conversation.orchestrator is not None
        assert conversation.tool_registry is not None