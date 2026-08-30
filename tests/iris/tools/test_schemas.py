"""
Tests for ToolSchemaConverter - converts IRIS tools to OpenAI function calling format.
"""

import pytest
from iris.tools.schemas import ToolSchemaConverter
from iris.tools.base import Tool, ToolArgument, ToolResult
from typing import Any, List


class SampleTool(Tool):
    """Sample tool for testing schema conversion."""

    @property
    def name(self) -> str:
        return "sample_tool"

    @property
    def description(self) -> str:
        return "A sample tool for testing"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(name="required_arg", type=str, description="A required string", required=True),
            ToolArgument(name="optional_arg", type=int, description="An optional integer", required=False, default=42),
            ToolArgument(name="float_arg", type=float, description="A float value", required=False, default=0.0),
            ToolArgument(name="bool_arg", type=bool, description="A boolean flag", required=False, default=False),
            ToolArgument(name="array_arg", type=list, description="An array of strings", required=False, default=[]),
            ToolArgument(name="object_arg", type=dict, description="An object", required=False, default={}),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content="done")


class NoArgsTool(Tool):
    """Tool with no arguments."""

    @property
    def name(self) -> str:
        return "no_args_tool"

    @property
    def description(self) -> str:
        return "Tool with no arguments"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content="done")


class TestPythonTypeToJsonSchemaType:
    """Tests for python_type_to_json_schema_type function."""

    def test_string_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(str) == "string"

    def test_integer_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(int) == "integer"

    def test_number_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(float) == "number"

    def test_boolean_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(bool) == "boolean"

    def test_array_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(list) == "array"

    def test_object_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(dict) == "object"

    def test_none_type(self):
        assert ToolSchemaConverter.python_type_to_json_schema_type(type(None)) == "null"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported Python type"):
            ToolSchemaConverter.python_type_to_json_schema_type(object)


class TestToolToOpenAIFunction:
    """Tests for tool_to_openai_function function."""

    def test_converts_tool_with_all_argument_types(self):
        tool = SampleTool()
        result = ToolSchemaConverter.tool_to_openai_function(tool)

        assert result["type"] == "function"
        assert result["function"]["name"] == "sample_tool"
        assert result["function"]["description"] == "A sample tool for testing"

        params = result["function"]["parameters"]
        assert params["type"] == "object"
        assert "required_arg" in params["properties"]
        assert "optional_arg" in params["properties"]
        assert "float_arg" in params["properties"]
        assert "bool_arg" in params["properties"]
        assert "array_arg" in params["properties"]
        assert "object_arg" in params["properties"]

        # Check required field
        assert params["required"] == ["required_arg"]

        # Check property details
        req_prop = params["properties"]["required_arg"]
        assert req_prop["type"] == "string"
        assert req_prop["description"] == "A required string"

        opt_prop = params["properties"]["optional_arg"]
        assert opt_prop["type"] == "integer"
        assert opt_prop["description"] == "An optional integer"

        bool_prop = params["properties"]["bool_arg"]
        assert bool_prop["type"] == "boolean"

        array_prop = params["properties"]["array_arg"]
        assert array_prop["type"] == "array"

        object_prop = params["properties"]["object_arg"]
        assert object_prop["type"] == "object"

    def test_converts_tool_with_no_arguments(self):
        tool = NoArgsTool()
        result = ToolSchemaConverter.tool_to_openai_function(tool)

        assert result["type"] == "function"
        assert result["function"]["name"] == "no_args_tool"
        assert result["function"]["description"] == "Tool with no arguments"

        params = result["function"]["parameters"]
        assert params["type"] == "object"
        assert params["properties"] == {}
        # required is only included when there are required arguments
        assert "required" not in params or params["required"] == []


class TestRegistryToOpenAIFunctions:
    """Tests for registry_to_openai_functions function."""

    def test_converts_multiple_tools(self):
        from iris.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(SampleTool())
        registry.register(NoArgsTool())

        result = ToolSchemaConverter.registry_to_openai_functions(registry)

        assert len(result) == 2
        # get_tool_names returns sorted list, so no_args_tool comes first
        assert result[0]["function"]["name"] == "no_args_tool"
        assert result[1]["function"]["name"] == "sample_tool"

    def test_empty_registry_returns_empty_list(self):
        from iris.tools.registry import ToolRegistry

        registry = ToolRegistry()
        result = ToolSchemaConverter.registry_to_openai_functions(registry)

        assert result == []

    def test_preserves_tool_order(self):
        from iris.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(NoArgsTool())
        registry.register(SampleTool())

        result = ToolSchemaConverter.registry_to_openai_functions(registry)

        assert result[0]["function"]["name"] == "no_args_tool"
        assert result[1]["function"]["name"] == "sample_tool"