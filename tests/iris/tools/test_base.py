"""
Tests for tool base abstractions.
"""

import pytest
from iris.tools.base import Tool, ToolArgument, ToolResult


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = ToolResult(
            success=True,
            content="test content",
        )

        assert result.success is True
        assert result.content == "test content"
        assert result.error is None
        assert result.metadata == {}

    def test_failed_result(self):
        """Test creating a failed result."""
        result = ToolResult(
            success=False,
            content=None,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.content is None
        assert result.error == "Something went wrong"

    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = ToolResult(
            success=True,
            content=42,
            metadata={"source": "test", "count": 1}
        )

        assert result.metadata["source"] == "test"
        assert result.metadata["count"] == 1

    def test_result_repr(self):
        """Test that repr doesn't expose full content."""
        result = ToolResult(success=True, content="sensitive data")
        repr_str = repr(result)

        assert "sensitive data" not in repr_str
        assert "ToolResult" in repr_str
        assert "success=True" in repr_str


class TestToolArgument:
    """Tests for ToolArgument dataclass."""

    def test_required_argument(self):
        """Test creating a required argument."""
        arg = ToolArgument(
            name="input",
            type=str,
            description="Input value",
        )

        assert arg.name == "input"
        assert arg.type == str
        assert arg.description == "Input value"
        assert arg.required is True
        assert arg.default is None

    def test_optional_argument(self):
        """Test creating an optional argument with default."""
        arg = ToolArgument(
            name="count",
            type=int,
            description="Count value",
            required=False,
            default=10,
        )

        assert arg.name == "count"
        assert arg.required is False
        assert arg.default == 10

    def test_optional_without_default_raises(self):
        """Test that optional argument without default raises error."""
        with pytest.raises(ValueError, match="must have a default value"):
            ToolArgument(
                name="bad",
                type=str,
                description="Bad arg",
                required=False,
            )


class MockTool(Tool):
    """Mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(name="required_arg", type=str, description="Required argument"),
            ToolArgument(name="optional_arg", type=int, description="Optional argument", required=False, default=0),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute mock tool."""
        return ToolResult(
            success=True,
            content=f"Executed with {kwargs}",
        )


class TestTool:
    """Tests for Tool abstract base class."""

    @pytest.mark.asyncio
    async def test_tool_properties(self):
        """Test tool properties."""
        tool = MockTool()

        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert len(tool.arguments) == 2

    def test_validate_arguments_success(self):
        """Test successful argument validation."""
        tool = MockTool()

        is_valid, error = tool.validate_arguments(required_arg="value", optional_arg=5)

        assert is_valid is True
        assert error is None

    def test_validate_arguments_missing_required(self):
        """Test validation fails with missing required argument."""
        tool = MockTool()

        is_valid, error = tool.validate_arguments(optional_arg=5)

        assert is_valid is False
        assert "required_arg" in error

    def test_validate_arguments_unexpected(self):
        """Test validation fails with unexpected argument."""
        tool = MockTool()

        is_valid, error = tool.validate_arguments(required_arg="value", unexpected=123)

        assert is_valid is False
        assert "unexpected" in error.lower()

    def test_validate_arguments_wrong_type(self):
        """Test validation fails with wrong type."""
        tool = MockTool()

        is_valid, error = tool.validate_arguments(required_arg="value", optional_arg="not_int")

        assert is_valid is False
        assert "optional_arg" in error
        assert "int" in error

    def test_validate_arguments_optional_missing(self):
        """Test validation succeeds with optional argument missing."""
        tool = MockTool()

        is_valid, error = tool.validate_arguments(required_arg="value")

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test tool execution."""
        tool = MockTool()

        result = await tool.execute(required_arg="test", optional_arg=10)

        assert result.success is True
        assert "test" in result.content

    def test_get_metadata(self):
        """Test tool metadata generation."""
        tool = MockTool()

        metadata = tool.get_metadata()

        assert metadata["name"] == "mock_tool"
        assert metadata["description"] == "A mock tool for testing"
        assert len(metadata["arguments"]) == 2
        assert metadata["arguments"][0]["name"] == "required_arg"
        assert metadata["arguments"][0]["required"] is True
        assert metadata["arguments"][1]["name"] == "optional_arg"
        assert metadata["arguments"][1]["required"] is False
        assert metadata["arguments"][1]["default"] == 0
