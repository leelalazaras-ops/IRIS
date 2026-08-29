"""
Tool registry for IRIS.

Manages registration, discovery, and execution of tools.
"""

from typing import Optional, Any
from iris.tools.base import Tool, ToolResult


class ToolRegistryError(Exception):
    """Exception raised for tool registry errors."""
    pass


class ToolRegistry:
    """
    Central registry for IRIS tools.

    Manages tool registration, discovery, and execution with validation
    and error handling.
    """

    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ToolRegistryError: If a tool with the same name is already registered
            ValueError: If tool is not a valid Tool instance
        """
        if not isinstance(tool, Tool):
            raise ValueError(f"Expected Tool instance, got {type(tool).__name__}")

        tool_name = tool.name
        if tool_name in self._tools:
            raise ToolRegistryError(
                f"Tool '{tool_name}' is already registered"
            )

        self._tools[tool_name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool exists in the registry.

        Args:
            name: Tool name

        Returns:
            True if tool exists, False otherwise
        """
        return name in self._tools

    def list_tools(self) -> list[dict[str, Any]]:
        """
        List all registered tools with their metadata.

        Returns:
            List of tool metadata dictionaries
        """
        return [tool.get_metadata() for tool in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        """
        Get names of all registered tools.

        Returns:
            Sorted list of tool names
        """
        return sorted(self._tools.keys())

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name with validation.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            ToolResult from tool execution

        Note:
            Does not raise exceptions - all errors are returned in ToolResult
        """
        # Check if tool exists
        if name not in self._tools:
            return ToolResult(
                success=False,
                content=None,
                error=f"Tool '{name}' not found in registry",
                metadata={"available_tools": self.get_tool_names()}
            )

        tool = self._tools[name]

        # Validate arguments
        is_valid, error_message = tool.validate_arguments(**kwargs)
        if not is_valid:
            return ToolResult(
                success=False,
                content=None,
                error=f"Argument validation failed: {error_message}",
                metadata={"tool": name}
            )

        # Execute tool
        try:
            result = await tool.execute(**kwargs)
            return result
        except Exception as e:
            # Tools should not raise exceptions, but handle it if they do
            return ToolResult(
                success=False,
                content=None,
                error=f"Tool execution failed: {str(e)}",
                metadata={"tool": name, "exception_type": type(e).__name__}
            )

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool from the registry.

        Args:
            name: Tool name

        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def clear(self) -> None:
        """Remove all tools from the registry."""
        self._tools.clear()

    def __len__(self) -> int:
        """
        Get number of registered tools.

        Returns:
            Tool count
        """
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """
        Check if tool exists using 'in' operator.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return name in self._tools
