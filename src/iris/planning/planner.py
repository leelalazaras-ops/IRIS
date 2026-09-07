"""
Action planner for IRIS Phase 7.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
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
        # Check for deterministic multi-step combinations
        multi_step = self._detect_multistep(intent)
        if multi_step is not None:
            return ActionPlan(
                steps=multi_step,
                intent=intent,
                metadata={"planner_version": "1.0", "multistep": True}
            )

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

    def _detect_multistep(self, intent: Intent) -> Optional[List[ActionStep]]:
        """
        Detect if the intent represents a known multi-step combination.
        Returns a list of ActionSteps if a multi-step pattern is matched, None otherwise.

        Supported combinations:
        - create_directory + write_file: "create directory <dir> and write file <file> with content <content>"
        - read_file + calculate: "read file <file> and calculate <expression>" or "calculate <expression> from file <file>"

        Args:
            intent: The intent to check for multi-step patterns

        Returns:
            Optional[List[ActionStep]]: List of steps if multi-step pattern matched, None otherwise
        """
        # Pattern 1: create_directory + write_file
        # Look for patterns like "create directory X and write file Y"
        if intent.action == "write_file":
            # Check if this might be part of a create_directory + write_file pattern
            content = intent.arguments.get("content", "")
            path = intent.arguments.get("path", "")

            # Look for directory creation hints in content or path
            # Simple heuristic: if content mentions directory creation or path suggests new directory
            user_lower = intent.original_request.lower()
            if ("create directory" in user_lower or "make directory" in user_lower or
                "mkdir" in user_lower) and ("write" in user_lower or "save" in user_lower or "create file" in user_lower):
                # Extract directory and file information
                dir_path, file_path, file_content = self._extract_create_dir_write_file_args(intent.original_request)
                if dir_path and file_path and file_content is not None:
                    # Create directory step
                    dir_step = ActionStep(
                        tool_name="create_directory",
                        arguments={"path": dir_path},
                        safety_classification=self.safety_classifier.classify_action("create_directory", {"path": dir_path}),
                        description=f"Create directory {dir_path}",
                        metadata={"intent_action": "create_directory"}
                    )
                    # Create write file step
                    write_step = ActionStep(
                        tool_name="write_file",
                        arguments={"path": file_path, "content": file_content},
                        safety_classification=self.safety_classifier.classify_action("write_file", {"path": file_path, "content": file_content}),
                        description=f"Write file {file_path}",
                        metadata={"intent_action": "write_file"}
                    )
                    return [dir_step, write_step]

        # Pattern 2: read_file + calculate
        # Look for patterns like "read file X and calculate Y" or "calculate Y from file X"
        if intent.action == "calculate":
            expression = intent.arguments.get("expression", "")
            user_lower = intent.original_request.lower()
            # Check for multi-step indicators: "read" OR "file" AND "calculate" OR "compute"
            has_read = "read" in user_lower or "get" in user_lower
            has_file = "file" in user_lower
            has_calc = "calculate" in user_lower or "compute" in user_lower
            if (has_read or has_file) and has_calc:
                file_path, calc_expression = self._extract_read_file_calculate_args(intent.original_request)
                if file_path and calc_expression:
                    # Create read file step
                    read_step = ActionStep(
                        tool_name="read_file",
                        arguments={"path": file_path},
                        safety_classification=self.safety_classifier.classify_action("read_file", {"path": file_path}),
                        description=f"Read file {file_path}",
                        metadata={"intent_action": "read_file"}
                    )
                    # Create calculate step
                    calc_step = ActionStep(
                        tool_name="calculate",
                        arguments={"expression": calc_expression},
                        safety_classification=self.safety_classifier.classify_action("calculate", {"expression": calc_expression}),
                        description=f"Calculate {calc_expression}",
                        metadata={"intent_action": "calculate"}
                    )
                    return [read_step, calc_step]

        # Pattern 1 alternative: check if intent is create_directory but part of write_file pattern
        if intent.action == "create_directory":
            user_lower = intent.original_request.lower()
            if ("create directory" in user_lower or "make directory" in user_lower) and \
               ("write" in user_lower or "save" in user_lower or "create file" in user_lower):
                # This might be the first part of create_directory + write_file
                dir_path, file_path, file_content = self._extract_create_dir_write_file_args(intent.original_request)
                if dir_path and file_path and file_content is not None:
                    # Create directory step
                    dir_step = ActionStep(
                        tool_name="create_directory",
                        arguments={"path": dir_path},
                        safety_classification=self.safety_classifier.classify_action("create_directory", {"path": dir_path}),
                        description=f"Create directory {dir_path}",
                        metadata={"intent_action": "create_directory"}
                    )
                    # Create write file step
                    write_step = ActionStep(
                        tool_name="write_file",
                        arguments={"path": file_path, "content": file_content},
                        safety_classification=self.safety_classifier.classify_action("write_file", {"path": file_path, "content": file_content}),
                        description=f"Write file {file_path}",
                        metadata={"intent_action": "write_file"}
                    )
                    return [dir_step, write_step]

        # Pattern 2 alternative: check if intent is read_file but part of calculate pattern
        if intent.action == "read_file":
            user_lower = intent.original_request.lower()
            has_read = "read" in user_lower or "get" in user_lower
            has_file = "file" in user_lower
            has_calc = "calculate" in user_lower or "compute" in user_lower
            if (has_read or has_file) and has_calc:
                file_path, calc_expression = self._extract_read_file_calculate_args(intent.original_request)
                if file_path and calc_expression:
                    # Create read file step
                    read_step = ActionStep(
                        tool_name="read_file",
                        arguments={"path": file_path},
                        safety_classification=self.safety_classifier.classify_action("read_file", {"path": file_path}),
                        description=f"Read file {file_path}",
                        metadata={"intent_action": "read_file"}
                    )
                    # Create calculate step
                    calc_step = ActionStep(
                        tool_name="calculate",
                        arguments={"expression": calc_expression},
                        safety_classification=self.safety_classifier.classify_action("calculate", {"expression": calc_expression}),
                        description=f"Calculate {calc_expression}",
                        metadata={"intent_action": "calculate"}
                    )
                    return [read_step, calc_step]

        return None

    def _extract_create_dir_write_file_args(self, user_input: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract directory path, file path, and content for create_directory + write_file from user input.
        Uses simple deterministic pattern matching.

        Args:
            user_input: The user's input string

        Returns:
            Tuple of (directory_path, file_path, content). Returns (None, None, None) if extraction fails.
        """
        import re

        # Normalize quotes
        normalized = user_input.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

        # Patterns to try:
        patterns = [
            # Pattern: create directory <dir> and write file <file> containing <content>
            (r'create\s+directory\s+(\S+)\s+and\s+write\s+a\s+file\s+(\S+)\s+containing\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())),
            # Pattern: create directory <dir> and write file <file> with content <content>
            (r'create\s+directory\s+(\S+)\s+and\s+write\s+a\s+file\s+(\S+)\s+with\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())),
            # Pattern: make directory <dir> and save <content> to <file>
            (r'make\s+directory\s+(\S+)\s+and\s+save\s+(.+?)\s+to\s+(\S+)',
             lambda m: (m.group(1).strip(), m.group(3).strip(), m.group(2).strip())),
            # Pattern: create directory <dir> then write file <file> with <content>
            (r'create\s+directory\s+(\S+)\s+then\s+write\s+a\s+file\s+(\S+)\s+with\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())),
            # Pattern: create directory <dir> and save <content> to <file>
            (r'create\s+directory\s+(\S+)\s+and\s+save\s+(.+?)\s+to\s+(\S+)',
             lambda m: (m.group(1).strip(), m.group(3).strip(), m.group(2).strip())),
        ]

        for pattern, extract_func in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                dir_path, file_path, content = extract_func(match)
                # Basic validation
                if dir_path and file_path and content is not None:
                    return (dir_path.strip(), file_path.strip(), content.strip())

        return (None, None, None)

    def _extract_read_file_calculate_args(self, user_input: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract file path and expression for read_file + calculate from user input.
        Uses simple deterministic pattern matching.

        Args:
            user_input: The user's input string

        Returns:
            Tuple of (file_path, expression). Returns (None, None) if extraction fails.
        """
        import re

        # Normalize quotes
        normalized = user_input.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

        # Patterns to try:
        patterns = [
            # Pattern: read file <file> and calculate <expression>
            (r'read\s+file\s+(\S+)\s+and\s+calculate\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip())),
            # Pattern: calculate <expression> from file <file>
            (r'calculate\s+(.+?)\s+from\s+file\s+(\S+)',
             lambda m: (m.group(2).strip(), m.group(1).strip())),
            # Pattern: get <file> and compute <expression>
            (r'get\s+(\S+)\s+and\s+compute\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip())),
            # Pattern: read <file> then calculate <expression>
            (r'read\s+(\S+)\s+then\s+calculate\s+(.+)',
             lambda m: (m.group(1).strip(), m.group(2).strip())),
        ]

        for pattern, extract_func in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                file_path, expression = extract_func(match)
                # Basic validation
                if file_path and expression:
                    return (file_path.strip(), expression.strip())

        return (None, None)