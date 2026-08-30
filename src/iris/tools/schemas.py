"""
Schema conversion for IRIS tools.

Converts IRIS Tool definitions to provider-specific formats (e.g., OpenAI functions).
Keeps provider-specific logic isolated from the core Tool abstraction.
"""

from typing import Any
from iris.tools.base import Tool, ToolArgument
from iris.tools.registry import ToolRegistry


class ToolSchemaConverter:
    """
    Converts IRIS tools to provider-specific schema formats.

    Currently supports OpenAI function calling format.
    Can be extended for other providers (Anthropic, etc.)
    """

    @staticmethod
    def python_type_to_json_schema_type(py_type: type) -> str:
        """
        Map Python type to JSON Schema type string.

        Args:
            py_type: Python type object

        Returns:
            JSON Schema type string

        Raises:
            ValueError: If type is not supported
        """
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        if py_type in type_mapping:
            return type_mapping[py_type]

        # Handle None/Optional
        if py_type is type(None):
            return "null"

        raise ValueError(f"Unsupported Python type for JSON Schema: {py_type}")

    @staticmethod
    def tool_argument_to_json_schema_property(
        arg: ToolArgument
    ) -> dict[str, Any]:
        """
        Convert a ToolArgument to a JSON Schema property definition.

        Args:
            arg: ToolArgument specification

        Returns:
            JSON Schema property dictionary
        """
        try:
            json_type = ToolSchemaConverter.python_type_to_json_schema_type(arg.type)
        except ValueError:
            # Fallback to string for unknown types
            json_type = "string"

        property_def = {
            "type": json_type,
            "description": arg.description
        }

        return property_def

    @staticmethod
    def tool_to_openai_function(tool: Tool) -> dict[str, Any]:
        """
        Convert an IRIS Tool to OpenAI function definition format.

        OpenAI function format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg_name": {"type": "string", "description": "..."}
                },
                "required": ["required_arg1", "required_arg2"]
            }
        }

        Args:
            tool: IRIS Tool instance

        Returns:
            OpenAI function definition dictionary
        """
        properties = {}
        required = []

        for arg in tool.arguments:
            properties[arg.name] = ToolSchemaConverter.tool_argument_to_json_schema_property(arg)

            if arg.required:
                required.append(arg.name)

        parameters = {
            "type": "object",
            "properties": properties
        }

        # Only include "required" if there are required arguments
        if required:
            parameters["required"] = required

        function_def = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters
            }
        }

        return function_def

    @staticmethod
    def registry_to_openai_functions(
        registry: ToolRegistry,
        tool_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Convert tools in a registry to OpenAI function definitions.

        Args:
            registry: ToolRegistry containing tools
            tool_names: Optional list of specific tool names to include.
                       If None, includes all tools in registry.

        Returns:
            List of OpenAI function definition dictionaries
        """
        functions = []

        if tool_names is None:
            # Get all tools
            tool_names = registry.get_tool_names()

        for tool_name in tool_names:
            tool = registry.get(tool_name)
            if tool is not None:
                function_def = ToolSchemaConverter.tool_to_openai_function(tool)
                functions.append(function_def)

        return functions
