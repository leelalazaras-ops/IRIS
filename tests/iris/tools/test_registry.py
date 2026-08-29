"""
Tests for tool registry.
"""

import pytest
from iris.tools.base import Tool, ToolArgument, ToolResult
from iris.tools.registry import ToolRegistry, ToolRegistryError


class SimpleTool(Tool):
    """Simple test tool."""

    @property
    def name(self) -> str:
        return "simple_tool"

    @property
    def description(self) -> str:
        return "A simple test tool"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(name="value", type=str, description="A value"),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Got: {kwargs['value']}")


class AnotherTool(Tool):
    """Another test tool."""

    @property
    def name(self) -> str:
        return "another_tool"

    @property
    def description(self) -> str:
        return "Another test tool"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content="executed")


class FailingTool(Tool):
    """Tool that raises exceptions."""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that fails"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Tool execution failed!")


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_registry_initialization(self):
        """Test registry starts empty."""
        registry = ToolRegistry()

        assert len(registry) == 0
        assert registry.get_tool_names() == []

    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)

        assert len(registry) == 1
        assert "simple_tool" in registry
        assert registry.has_tool("simple_tool")

    def test_register_duplicate_tool_raises(self):
        """Test registering duplicate tool raises error."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = SimpleTool()

        registry.register(tool1)

        with pytest.raises(ToolRegistryError, match="already registered"):
            registry.register(tool2)

    def test_register_invalid_type_raises(self):
        """Test registering non-tool raises error."""
        registry = ToolRegistry()

        with pytest.raises(ValueError, match="Expected Tool instance"):
            registry.register("not a tool")

    def test_get_tool(self):
        """Test retrieving a tool."""
        registry = ToolRegistry()
        tool = SimpleTool()
        registry.register(tool)

        retrieved = registry.get("simple_tool")

        assert retrieved is not None
        assert retrieved.name == "simple_tool"

    def test_get_nonexistent_tool(self):
        """Test retrieving nonexistent tool returns None."""
        registry = ToolRegistry()

        result = registry.get("nonexistent")

        assert result is None

    def test_has_tool(self):
        """Test checking tool existence."""
        registry = ToolRegistry()
        tool = SimpleTool()
        registry.register(tool)

        assert registry.has_tool("simple_tool") is True
        assert registry.has_tool("nonexistent") is False

    def test_contains_operator(self):
        """Test 'in' operator."""
        registry = ToolRegistry()
        tool = SimpleTool()
        registry.register(tool)

        assert "simple_tool" in registry
        assert "nonexistent" not in registry

    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        registry.register(SimpleTool())
        registry.register(AnotherTool())

        tools = registry.list_tools()

        assert len(tools) == 2
        tool_names = [t["name"] for t in tools]
        assert "simple_tool" in tool_names
        assert "another_tool" in tool_names

    def test_get_tool_names(self):
        """Test getting tool names."""
        registry = ToolRegistry()
        registry.register(SimpleTool())
        registry.register(AnotherTool())

        names = registry.get_tool_names()

        assert len(names) == 2
        assert "another_tool" in names
        assert "simple_tool" in names
        # Should be sorted
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """Test executing a tool through registry."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        result = await registry.execute("simple_tool", value="test")

        assert result.success is True
        assert "test" in result.content

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """Test executing nonexistent tool returns error."""
        registry = ToolRegistry()

        result = await registry.execute("nonexistent")

        assert result.success is False
        assert "not found" in result.error
        assert "available_tools" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_with_validation_error(self):
        """Test execution with invalid arguments."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        # Missing required argument
        result = await registry.execute("simple_tool")

        assert result.success is False
        assert "validation failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_wrong_type(self):
        """Test execution with wrong argument type."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        # Wrong type for 'value'
        result = await registry.execute("simple_tool", value=123)

        assert result.success is False
        assert "validation failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_that_raises(self):
        """Test executing tool that raises exception."""
        registry = ToolRegistry()
        registry.register(FailingTool())

        result = await registry.execute("failing_tool")

        assert result.success is False
        assert "execution failed" in result.error.lower()
        assert result.metadata["exception_type"] == "RuntimeError"

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        removed = registry.unregister("simple_tool")

        assert removed is True
        assert len(registry) == 0
        assert "simple_tool" not in registry

    def test_unregister_nonexistent_tool(self):
        """Test unregistering nonexistent tool."""
        registry = ToolRegistry()

        removed = registry.unregister("nonexistent")

        assert removed is False

    def test_clear_registry(self):
        """Test clearing all tools from registry."""
        registry = ToolRegistry()
        registry.register(SimpleTool())
        registry.register(AnotherTool())

        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get_tool_names() == []

    def test_len_operator(self):
        """Test len() operator."""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register(SimpleTool())
        assert len(registry) == 1

        registry.register(AnotherTool())
        assert len(registry) == 2
