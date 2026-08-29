"""
Base abstractions for the IRIS tool system.

Defines the core Tool interface and result structures that all tools must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """
    Result from tool execution.

    Attributes:
        success: Whether the tool executed successfully
        content: The result content (varies by tool)
        error: Error message if execution failed
        metadata: Additional metadata about the execution
    """
    success: bool
    content: Any
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        """String representation that doesn't expose sensitive content."""
        if self.success:
            return f"ToolResult(success=True, content_type={type(self.content).__name__})"
        return f"ToolResult(success=False, error={self.error!r})"


@dataclass
class ToolArgument:
    """
    Specification for a tool argument.

    Attributes:
        name: Argument name
        type: Expected Python type
        description: Human-readable description
        required: Whether the argument is required
        default: Default value if not required
    """
    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None

    def __post_init__(self):
        """Validate argument specification."""
        if not self.required and self.default is None:
            raise ValueError(f"Optional argument '{self.name}' must have a default value")


class Tool(ABC):
    """
    Abstract base class for all IRIS tools.

    Tools provide specific capabilities (filesystem operations, system info, etc.)
    with a consistent interface for registration, validation, and execution.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique tool identifier.

        Returns:
            Tool name (lowercase, underscore-separated)
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of what the tool does.

        Returns:
            Tool description
        """
        pass

    @property
    @abstractmethod
    def arguments(self) -> list[ToolArgument]:
        """
        Tool argument specifications.

        Returns:
            List of ToolArgument objects defining the tool's parameters
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given arguments.

        Args:
            **kwargs: Tool arguments (validated before execution)

        Returns:
            ToolResult with execution outcome

        Raises:
            Should not raise exceptions - errors should be returned in ToolResult
        """
        pass

    def validate_arguments(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate arguments before execution.

        Args:
            **kwargs: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for required arguments
        required_args = {arg.name for arg in self.arguments if arg.required}
        provided_args = set(kwargs.keys())

        missing_args = required_args - provided_args
        if missing_args:
            return False, f"Missing required arguments: {', '.join(sorted(missing_args))}"

        # Check for unexpected arguments
        valid_args = {arg.name for arg in self.arguments}
        unexpected_args = provided_args - valid_args
        if unexpected_args:
            return False, f"Unexpected arguments: {', '.join(sorted(unexpected_args))}"

        # Check argument types
        arg_types = {arg.name: arg.type for arg in self.arguments}
        for arg_name, arg_value in kwargs.items():
            expected_type = arg_types[arg_name]
            if not isinstance(arg_value, expected_type):
                return False, (
                    f"Argument '{arg_name}' must be {expected_type.__name__}, "
                    f"got {type(arg_value).__name__}"
                )

        return True, None

    def get_metadata(self) -> dict[str, Any]:
        """
        Get tool metadata for registration and discovery.

        Returns:
            Dictionary with tool name, description, and argument specs
        """
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [
                {
                    "name": arg.name,
                    "type": arg.type.__name__,
                    "description": arg.description,
                    "required": arg.required,
                    "default": arg.default,
                }
                for arg in self.arguments
            ],
        }
