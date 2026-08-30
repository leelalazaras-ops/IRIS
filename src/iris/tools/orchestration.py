"""
Tool orchestration for IRIS AI-driven tool execution.

This module provides the ToolOrchestrator, which enables AI providers to
request tool execution in a safe, controlled manner. All tool execution
goes through the existing Phase 3 ToolRegistry with full validation.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, TYPE_CHECKING
from iris.tools.registry import ToolRegistry
from iris.tools.base import ToolResult

if TYPE_CHECKING:
    from iris.ai.service import AIService


@dataclass
class ToolCall:
    """
    Internal provider-independent representation of a tool execution request.

    Providers map their native formats (OpenAI functions, etc.) to this
    internal representation at the provider boundary.

    Attributes:
        id: Unique identifier for this tool call
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments to pass to the tool
    """
    id: str
    tool_name: str
    arguments: dict[str, Any]

    def __post_init__(self):
        """Validate ToolCall structure."""
        if not self.id:
            raise ValueError("ToolCall id cannot be empty")
        if not self.tool_name:
            raise ValueError("ToolCall tool_name cannot be empty")
        if not isinstance(self.arguments, dict):
            raise ValueError("ToolCall arguments must be a dict")


@dataclass
class OrchestrationConfig:
    """
    Configuration for tool orchestration behavior.

    Attributes:
        max_tool_calls: Maximum number of tool calls allowed per user message
        enable_tools: Master switch to enable/disable tool orchestration
    """
    max_tool_calls: int = 5
    enable_tools: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1")


class ToolOrchestrator:
    """
    Orchestrates AI-driven tool execution.

    Responsibilities:
    - Accept tool calls from AI providers
    - Validate tool requests as untrusted input
    - Execute tools via the existing ToolRegistry
    - Format results for AI consumption
    - Enforce safety limits (max calls)
    - Handle errors safely

    All tool execution goes through the Phase 3 ToolRegistry, preserving
    all existing security guarantees (path validation, no subprocess, etc.)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        config: Optional[OrchestrationConfig] = None
    ):
        """
        Initialize the tool orchestrator.

        Args:
            registry: ToolRegistry containing available tools
            config: Orchestration configuration (uses defaults if not provided)
        """
        self.registry = registry
        self.config = config or OrchestrationConfig()
        self._tool_call_count = 0

    def reset_call_count(self) -> None:
        """Reset the tool call counter (call at start of each user turn)."""
        self._tool_call_count = 0

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCall]
    ) -> list[ToolResult]:
        """
        Execute multiple tool calls with validation and safety limits.

        Each tool call is treated as untrusted input and validated before
        execution through the ToolRegistry.

        Args:
            tool_calls: List of ToolCall objects to execute

        Returns:
            List of ToolResult objects (one per tool call)

        Note:
            Does not raise exceptions. Validation/execution errors are
            returned as ToolResult objects with success=False.
        """
        results: list[ToolResult] = []

        for tool_call in tool_calls:
            # Check safety limit
            if self._tool_call_count >= self.config.max_tool_calls:
                results.append(ToolResult(
                    success=False,
                    content=None,
                    error=f"Maximum tool calls exceeded (limit: {self.config.max_tool_calls})",
                    metadata={"tool_call_id": tool_call.id}
                ))
                continue

            # Validate ToolCall structure (treat as untrusted)
            try:
                # Basic structure validation
                if not isinstance(tool_call.tool_name, str):
                    results.append(ToolResult(
                        success=False,
                        content=None,
                        error="Invalid tool_name: must be a string",
                        metadata={"tool_call_id": tool_call.id}
                    ))
                    continue

                if not isinstance(tool_call.arguments, dict):
                    results.append(ToolResult(
                        success=False,
                        content=None,
                        error="Invalid arguments: must be a dictionary",
                        metadata={"tool_call_id": tool_call.id}
                    ))
                    continue

                # Execute through ToolRegistry (validates and executes safely)
                # This goes through Phase 3 security (path validation, etc.)
                result = await self.registry.execute(
                    tool_call.tool_name,
                    **tool_call.arguments
                )

                # Add tool call ID to result metadata
                result.metadata["tool_call_id"] = tool_call.id
                results.append(result)

                # Increment counter only for executed calls
                self._tool_call_count += 1

            except Exception as e:
                # Safety net: catch any unexpected errors
                results.append(ToolResult(
                    success=False,
                    content=None,
                    error=f"Tool execution error: {str(e)}",
                    metadata={
                        "tool_call_id": tool_call.id,
                        "exception_type": type(e).__name__
                    }
                ))

        return results

    @staticmethod
    def format_tool_results_for_messages(
        tool_calls: list[ToolCall],
        results: list[ToolResult]
    ) -> list[dict[str, str]]:
        """
        Format tool execution results as conversation messages.

        Converts ToolResult objects into message dictionaries that can be
        added to the conversation history and sent back to the AI.

        Args:
            tool_calls: Original tool calls
            results: Execution results (must match tool_calls length)

        Returns:
            List of message dictionaries with role="tool"
        """
        if len(tool_calls) != len(results):
            raise ValueError("tool_calls and results must have the same length")

        messages = []
        for tool_call, result in zip(tool_calls, results):
            if result.success:
                # Format successful result
                content = str(result.content)
            else:
                # Format error result
                content = f"Error: {result.error}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.tool_name,
                "content": content
            })

        return messages

    async def process_conversation_turn(
        self,
        ai_service: AIService,
        messages: list[dict[str, str]],
        available_tools: Optional[list[str]] = None
    ) -> tuple[str, list[ToolCall]]:
        """
        Process one conversation turn with tool support.

        This is a high-level method that:
        1. Calls AI with tool definitions
        2. If AI requests tools, executes them
        3. Sends results back to AI
        4. Returns final response

        Args:
            ai_service: AIService instance
            messages: Conversation history
            available_tools: Optional whitelist of tool names to expose

        Returns:
            Tuple of (final_response_text, executed_tool_calls)

        Note:
            This method will be used by the CLI. For now, it's a placeholder
            that will be fully implemented once provider support is complete.
        """
        # Reset call counter for new turn
        self.reset_call_count()

        # For now, return a placeholder
        # This will be implemented after provider integration
        executed_calls: list[ToolCall] = []

        # Just pass through to AI without tools for now
        response = await ai_service.generate(messages=messages)

        return response, executed_calls
