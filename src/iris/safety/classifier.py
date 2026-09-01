"""
Safety classification for IRIS Phase 7.
"""

from enum import Enum
from typing import Dict, Any
from iris.tools.registry import ToolRegistry


class SafetyLevel(Enum):
    """
    Safety levels for actions.
    """
    SAFE = "safe"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    BLOCKED = "blocked"


class SafetyClassifier:
    """
    Classifies actions as SAFE, REQUIRES_CONFIRMATION, or BLOCKED.
    """

    def __init__(self, registry: ToolRegistry):
        """
        Initialize the safety classifier.

        Args:
            registry: The tool registry to get tool information from
        """
        self.registry = registry

        # Define safety rules based on tool names
        # These are initial hardcoded rules; can be made configurable later
        self._safe_tools = {
            "list_directory",
            "read_file",
            "get_system_info",
            "get_current_directory",
            "get_environment_info",
            "get_current_time",
            "calculate",
        }

        self._requires_confirmation_tools = {
            "write_file",
            "create_directory",
            # Add other tools that modify state but are not extremely dangerous
        }

        self._blocked_tools = {
            # Add tools that are too dangerous to ever execute automatically
            # For example, if we had a tool to delete files or format drives
        }

    def classify_action(self, tool_name: str, arguments: Dict[str, Any]) -> SafetyLevel:
        """
        Classify an action based on tool name and arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            SafetyLevel: The safety classification for this action
        """
        # First, check if the tool exists in the registry
        if not self.registry.has_tool(tool_name):
            # Unknown tool - treat as blocked for safety
            return SafetyLevel.BLOCKED

        # Check against our predefined categories
        if tool_name in self._blocked_tools:
            return SafetyLevel.BLOCKED

        if tool_name in self._requires_confirmation_tools:
            return SafetyLevel.REQUIRES_CONFIRMATION

        if tool_name in self._safe_tools:
            return SafetyLevel.SAFE

        # For tools not explicitly classified, default to requiring confirmation
        # This is a safe default for unknown tools
        return SafetyLevel.REQUIRES_CONFIRMATION

    def is_safe(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Check if an action is safe (no confirmation needed).

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            bool: True if action is safe, False otherwise
        """
        return self.classify_action(tool_name, arguments) == SafetyLevel.SAFE

    def requires_confirmation(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Check if an action requires user confirmation.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            bool: True if action requires confirmation, False otherwise
        """
        return self.classify_action(tool_name, arguments) == SafetyLevel.REQUIRES_CONFIRMATION

    def is_blocked(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Check if an action is blocked (should not be executed).

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            bool: True if action is blocked, False otherwise
        """
        return self.classify_action(tool_name, arguments) == SafetyLevel.BLOCKED