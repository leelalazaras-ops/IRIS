"""
Action planner for IRIS Phase 7.
"""

from typing import Dict, Any, List, Optional
from iris.intent.models import Intent
from iris.planning.models import ActionPlan, ActionStep
from iris.safety.classifier import SafetyClassifier, SafetyLevel
from iris.tools.registry import ToolRegistry


class Planner:
    """
    Converts intents into executable action plans.
    """

    def __init__(self, registry: ToolRegistry, safety_classifier: SafetyClassifier):
        """
        Initialize the planner.

        Args:
            registry: The tool registry for tool discovery
            safety_classifier: The safety classifier for action safety assessment
        """
        self.registry = registry
        self.safety_classifier = safety_classifier

        # Mapping from intent actions to tool names and argument mappings
        # This is a simple rule-based mapper; can be enhanced with ML or config later
        self._intent_to_tool_map = {
            # File system operations
            "read_file": ("read_file", {"path": "path"}),
            "write_file": ("write_file", {"path": "path", "content": "content"}),
            "list_directory": ("list_directory", {"path": "path"}),
            "create_directory": ("create_directory", {"path": "path"}),
            # System operations
            "get_system_info": ("get_system_info", {}),
            "get_current_directory": ("get_current_directory", {}),
            "get_environment_info": ("get_environment_info", {}),
            # Utility operations
            "get_current_time": ("get_current_time", {}),
            "calculate": ("calculate", {"expression": "expression"}),
            # Add more mappings as needed
        }

    def plan(self, intent: Intent) -> ActionPlan:
        """
        Create an action plan from an intent.

        Args:
            intent: The intent to convert to a plan

        Returns:
            ActionPlan: A plan containing one or more action steps
        """
        # For now, we assume a one-to-one mapping from intent to action step
        # In the future, we might decompose complex intents into multiple steps
        tool_name, arg_mapping = self._intent_to_tool_map.get(intent.action, (None, {}))

        if tool_name is None:
            # If we don't know how to handle this intent, we create a plan with no steps
            # Alternatively, we could raise an error or create a failed step
            return ActionPlan(
                steps=[],
                intent=intent,
                metadata={"error": f"No tool mapping found for intent action: {intent.action}"}
            )

        # Map intent arguments to tool arguments
        tool_arguments: Dict[str, Any] = {}
        for intent_arg, tool_arg in arg_mapping.items():
            if intent_arg in intent.arguments:
                tool_arguments[tool_arg] = intent.arguments[intent_arg]

        # Classify the safety of the action
        safety_level = self.safety_classifier.classify_action(tool_name, tool_arguments)

        # Create a description for the action step
        description = self._generate_description(tool_name, tool_arguments)

        # Create the action step
        step = ActionStep(
            tool_name=tool_name,
            arguments=tool_arguments,
            safety_classification=safety_level,
            description=description,
            metadata={"intent_action": intent.action}
        )

        # Create and return the plan
        return ActionPlan(
            steps=[step],
            intent=intent,
            metadata={"planner_version": "1.0"}
        )

    def _generate_description(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Generate a human-readable description for an action step.

        Args:
            tool_name: Name of the tool
            arguments: Arguments for the tool

        Returns:
            str: A description of what the action does
        """
        # Simple description generation; can be enhanced
        if tool_name == "read_file":
            return f"Read file: {arguments.get('path', 'unknown')}"
        elif tool_name == "write_file":
            return f"Write file: {arguments.get('path', 'unknown')}"
        elif tool_name == "list_directory":
            return f"List directory: {arguments.get('path', 'unknown')}"
        elif tool_name == "create_directory":
            return f"Create directory: {arguments.get('path', 'unknown')}"
        elif tool_name == "get_system_info":
            return "Get system information"
        elif tool_name == "get_current_directory":
            return "Get current directory"
        elif tool_name == "get_environment_info":
            return "Get environment information"
        elif tool_name == "get_current_time":
            return "Get current time"
        elif tool_name == "calculate":
            expr = arguments.get('expression', 'unknown')
            return f"Calculate: {expr}"
        else:
            return f"Execute tool: {tool_name}"