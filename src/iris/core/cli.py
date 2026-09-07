"""
Command-line interface for IRIS.
"""

import asyncio
import json
import sys
import signal
import re
from typing import Optional, List, Dict

from iris.ai.service import AIService
from iris.ai.exceptions import AIError, ConfigurationError
from iris.tools.registry import ToolRegistry
from iris.tools.orchestration import ToolOrchestrator, OrchestrationConfig, ToolCall
from iris.tools.schemas import ToolSchemaConverter
from iris.tools.filesystem import (
    ListDirectoryTool,
    CreateDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)
from iris.tools.system import (
    GetSystemInfoTool,
    GetCurrentDirectoryTool,
    GetEnvironmentInfoTool,
)
from iris.tools.utility import (
    GetCurrentTimeTool,
    CalculateTool,
)
from iris.memory.manager import MemoryManager

# Phase 7: Intent & Action Engine imports
from iris.intent.models import Intent
from iris.planning.planner import Planner
from iris.planning.models import ActionPlan, ActionStep
from iris.safety.classifier import SafetyClassifier, SafetyLevel
from iris.results.models import ActionResult
from iris.results.handler import ResultHandler


class IRISConversation:
    """Manages an interactive conversation session with IRIS."""

    def __init__(self):
        """Initialize the conversation manager."""
        self.ai_service: Optional[AIService] = None
        self.memory_manager = MemoryManager()
        self.running = False
        self.tool_registry = self._initialize_tool_registry()
        self.orchestrator = ToolOrchestrator(
            self.tool_registry,
            OrchestrationConfig(max_tool_calls=5, enable_tools=True)
        )
        self.tools_enabled = True  # Can be toggled by user

        # Phase 7: Intent & Action Engine components
        self.safety_classifier = SafetyClassifier(self.tool_registry)
        self.planner = Planner(self.tool_registry, self.safety_classifier)
        self.result_handler = ResultHandler(self.memory_manager)

        # Conversation state for Phase 7
        self.dry_run_mode = False
        self.pending_remaining_steps: Optional[List[ActionStep]] = None
        self.pending_plan: Optional[ActionPlan] = None

    @property
    def conversation_history(self):
        """Get conversation history for backward compatibility with tests."""
        return self.memory_manager.context.turns

    @conversation_history.setter
    def conversation_history(self, value):
        """Set conversation history for backward compatibility with tests."""
        self.memory_manager.context.turns = value

    def _initialize_tool_registry(self) -> ToolRegistry:
        """
        Initialize and populate the tool registry.

        Returns:
            ToolRegistry with all available tools registered
        """
        registry = ToolRegistry()

        # Register filesystem tools
        registry.register(ListDirectoryTool())
        registry.register(CreateDirectoryTool())
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())

        # Register system tools
        registry.register(GetSystemInfoTool())
        registry.register(GetCurrentDirectoryTool())
        registry.register(GetEnvironmentInfoTool())

        # Register utility tools
        registry.register(GetCurrentTimeTool())
        registry.register(CalculateTool())

        return registry

    async def initialize(self) -> bool:
        """
        Initialize the AI service.

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            self.ai_service = AIService()
            return True
        except ConfigurationError as e:
            print(f"\nERROR: Configuration error: {e.message}")
            print("\nPlease check your environment variables:")
            print("  - IRIS_AI_PROVIDER (default: openai-compatible)")
            print("  - IRIS_AI_BASE_URL (required for openai-compatible)")
            print("  - IRIS_AI_API_KEY (required for openai-compatible)")
            print("  - IRIS_AI_MODEL (default: gpt-3.5-turbo)")
            print("\nSee .env.example for configuration examples.")
            return False
        except Exception as e:
            print(f"\nERROR: Unexpected error during initialization: {str(e)}")
            return False

    async def handle_user_input(self, user_input: str) -> bool:
        """
        Process user input and generate a response.

        Args:
            user_input: The user's message

        Returns:
            True to continue, False to exit
        """
        # Handle empty input
        if not user_input.strip():
            return True

        # Handle exit commands
        if user_input.strip().lower() in ('exit', 'quit'):
            return False

        # Handle tool commands
        stripped_input = user_input.strip()
        if stripped_input.startswith('/'):
            return await self.handle_tool_command(stripped_input)

        # Add user message to memory
        self.memory_manager.add_user_message(user_input.strip())

        try:
            # Phase 7: Process with intent & action engine
            if self.tools_enabled:
                response = await self._process_with_intent_and_action(user_input.strip())
            else:
                # Standard conversation without tools
                response = await self.ai_service.generate(
                    messages=self.memory_manager.get_messages_for_ai(),
                    temperature=0.7,
                )

            # Add assistant response to memory
            self.memory_manager.add_assistant_message(response)

            # Display response
            print(f"\nIRIS: {response}\n")

        except AIError as e:
            # Remove the user message from memory since we couldn't process it
            self.memory_manager.remove_last_turn()
            print(f"\nERROR: AI Error: {e.message}")
            print("Please try again or check your configuration.\n")
        except Exception as e:
            # Remove the user message from memory
            self.memory_manager.remove_last_turn()
            # Sanitize error message to avoid leaking sensitive data
            error_msg = str(e)
            # Don't expose API keys or tokens in error messages
            for sensitive_word in ['key', 'token', 'password', 'secret']:
                if sensitive_word in error_msg.lower():
                    error_msg = "An error occurred. Please check your configuration."
                    break
            print(f"\nError: {error_msg}")
            print("Please try again.\n")

        return True

    async def handle_tool_command(self, command: str) -> bool:
        """
        Handle tool-related commands.

        Args:
            command: Command string starting with '/'

        Returns:
            True to continue, False to exit
        """
        parts = command[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "tools":
            # List all available tools
            print("\n[Tools] Available Tools:\n")
            tools = self.tool_registry.list_tools()
            for tool in tools:
                print(f"  • {tool['name']}")
                print(f"    {tool['description']}")
                if tool['arguments']:
                    print(f"    Arguments:")
                    for arg in tool['arguments']:
                        req = "required" if arg['required'] else "optional"
                        print(f"      - {arg['name']} ({arg['type']}, {req}): {arg['description']}")
                print()
            print(f"Total: {len(tools)} tools\n")
            return True

        elif cmd == "help":
            # Show help information
            print("\n📖 IRIS Commands:\n")
            print("  /tools                 - List all available tools")
            print("  /enable-tools          - Enable AI tool orchestration")
            print("  /disable-tools         - Disable AI tool orchestration")
            print("  /tool-status           - Show tool orchestration status")
            print("  /help                  - Show this help message")
            print("  /dry-run               - Toggle dry-run mode (show plans without executing)")
            print("  /confirm               - Confirm pending action")
            print("  /cancel                - Cancel pending action")
            print("  exit, quit             - Exit IRIS")
            print()
            return True

        elif cmd == "enable-tools":
            self.tools_enabled = True
            self.orchestrator.config.enable_tools = True
            print("\n✅ Tool orchestration enabled\n")
            return True

        elif cmd == "disable-tools":
            self.tools_enabled = False
            self.orchestrator.config.enable_tools = False
            print("\n🚫 Tool orchestration disabled\n")
            return True

        elif cmd == "tool-status":
            print(f"\n⚙️ Tool Orchestration Status:\n")
            print(f"  Enabled: {'Yes' if self.tools_enabled else 'No'}")
            print(f"  Max tool calls per turn: {self.orchestrator.config.max_tool_calls}")
            print(f"  Available tools: {len(self.tool_registry.get_tool_names())}")
            print()
            return True

        elif cmd == "dry-run":
            self.dry_run_mode = not self.dry_run_mode
            status = "enabled" if self.dry_run_mode else "disabled"
            print(f"\n🔍 Dry-run mode {status}\n")
            return True

        elif cmd == "confirm":
            if self.pending_remaining_steps is not None:
                # Execute all remaining steps in order
                step_descriptions = [s.description for s in self.pending_remaining_steps]
                print(f"\n✅ Confirming {len(self.pending_remaining_steps)} action(s): {', '.join(step_descriptions)}")
                for step in self.pending_remaining_steps:
                    await self._execute_action_step(step)
                self.pending_remaining_steps = None
                self.pending_plan = None
            else:
                print("\n❌ No pending action to confirm\n")
            return True

        elif cmd == "cancel":
            if self.pending_remaining_steps is not None:
                step_descriptions = [s.description for s in self.pending_remaining_steps]
                print(f"\n❌ Cancelling action(s): {', '.join(step_descriptions)}")
                self.pending_remaining_steps = None
                self.pending_plan = None
            else:
                print("\n❌ No pending action to cancel\n")
            return True

        else:
            print(f"\n❌ Unknown command: /{cmd}")
            print("Type '/help' for available commands.\n")
            return True

    async def _process_with_intent_and_action(self, user_input: str) -> str:
        """
        Process user input through the Phase 7 intent and action engine.
        This follows the same pattern as _process_with_tools but adds intent understanding.

        Args:
            user_input: The user's input string

        Returns:
            The AI's response string
        """
        if not self.ai_service:
            raise RuntimeError("AI service not initialized")

        # Try to interpret as intent for action execution
        intent = self._create_intent_from_user_input(user_input.strip())

        # Only proceed with action execution if confidence is high enough
        # For now, we'll use a threshold of 0.7
        if intent.confidence <= 0.7:
            # Fall back to normal tool processing for low-confidence intents
            response_content, _ = await self._process_with_tools()
            return response_content

        # Create action plan from intent
        plan = self.planner.plan(intent)

        # Check if we have any steps to execute
        if not plan.steps:
            # If no plan steps, fall back to normal processing
            response_content, _ = await self._process_with_tools()
            return response_content

        # We have a plan to execute - we'll execute it directly
        # But we still want to follow the tool execution pattern for consistency

        # Reset tool call counter for this user turn
        self.orchestrator.reset_call_count()

        # Convert our action steps to tool calls
        tool_calls: list[ToolCall] = []
        for i, step in enumerate(plan.steps):
            # Check safety classification
            if self.safety_classifier.is_blocked(step.tool_name, step.arguments):
                # Create a failed tool result for blocked actions
                from iris.tools.base import ToolResult
                tool_result = ToolResult(
                    success=False,
                    content=None,
                    error=f"Action blocked: {step.description}",
                    metadata={"blocked_by_safety": True}
                )

                # Format as tool message and add to memory
                tool_message = {
                    "role": "tool",
                    "tool_call_id": f"blocked_{i}",
                    "name": step.tool_name,
                    "content": f"Error: {tool_result.error}"
                }
                self.memory_manager.context.turns.append(tool_message)
                continue

            if self.safety_classifier.requires_confirmation(step.tool_name, step.arguments):
                # For confirmation-required actions, we need to handle specially
                if self.dry_run_mode:
                    # In dry run, simulate execution
                    from iris.tools.base import ToolResult
                    tool_result = await self._execute_action_step_dry_run(step)
                else:
                    # Store ALL steps that have not been executed yet.
                    # This includes the SAFE steps that appeared earlier in
                    # the plan (already collected as tool_calls but never
                    # executed because we return early) AND the confirmation
                    # step AND all subsequent steps. We must not lose any step.
                    # Convert any collected tool_calls back to ActionStep
                    # representation and combine with remaining plan steps.
                    pending: List[ActionStep] = []
                    for tc in tool_calls:
                        pending.append(ActionStep(
                            tool_name=tc.tool_name,
                            arguments=tc.arguments,
                            description=f"Execute tool: {tc.tool_name}"
                        ))
                    pending.extend(plan.steps[i:])
                    self.pending_remaining_steps = pending
                    self.pending_plan = plan
                    return f"⚠️  Action requires confirmation: {step.description}\nType '/confirm' to proceed or '/cancel' to abort."

                # Format successful result
                tool_message = {
                    "role": "tool",
                    "tool_call_id": f"dry_run_{i}",
                    "name": step.tool_name,
                    "content": str(tool_result.content) if tool_result.success else f"Error: {tool_result.error}"
                }
                self.memory_manager.context.turns.append(tool_message)
                continue

            # Safe action - create tool call
            tool_call = ToolCall(
                id=f"action_{i}",
                tool_name=step.tool_name,
                arguments=step.arguments
            )
            tool_calls.append(tool_call)

        # If we have tool calls to execute (safe actions), execute them
        if tool_calls:
            # Execute tool calls through orchestrator
            results = await self.orchestrator.execute_tool_calls(tool_calls)

            # Format results for conversation
            tool_messages = ToolOrchestrator.format_tool_results_for_messages(
                tool_calls,
                results
            )

            # Add tool results to memory
            for message in tool_messages:
                if message["role"] == "user":
                    self.memory_manager.add_user_message(message["content"])
                elif message["role"] == "assistant":
                    self.memory_manager.add_assistant_message(message["content"])
                elif message["role"] == "tool":
                    # For tool messages, we need to add them directly to turns
                    # since they don't fit the standard user/assistant pattern
                    self.memory_manager.context.turns.append(message)

            # Now generate final response based on the tool results
            response_content = await self.ai_service.generate(
                messages=self.memory_manager.get_messages_for_ai(),
                temperature=0.7,
            )

            # Add assistant response to memory
            self.memory_manager.add_assistant_message(response_content)

            return response_content
        else:
            # No tool calls to execute (all were blocked or handled specially)
            # Generate response based on what happened
            if self.pending_remaining_steps is not None:
                # This shouldn't happen because we returned early above, but just in case
                first_step = self.pending_remaining_steps[0]
                return f"⚠️  Action requires confirmation: {first_step.description}\nType '/confirm' to proceed or '/cancel' to abort."
            else:
                # All actions were blocked or we had dry run results
                # Generate a summary response
                return await self.ai_service.generate(
                    messages=self.memory_manager.get_messages_for_ai(),
                    temperature=0.7,
                )

    async def _process_with_tools(self) -> tuple[str, list[ToolCall]]:
        """
        Process a conversation turn with tool support.
        Executes a loop: AI -> tool execution -> AI -> ... until AI returns no tool calls.

        Returns:
            Tuple of (final_response, all_tool_calls_requested)
        """
        if not self.ai_service:
            raise RuntimeError("AI service not initialized")

        # Reset tool call counter for this user turn
        self.orchestrator.reset_call_count()

        # Build tool definitions in OpenAI format
        tool_defs = ToolSchemaConverter.registry_to_openai_functions(
            self.tool_registry
        )

        # Accumulate all tool calls requested across rounds
        all_tool_calls: list[ToolCall] = []
        # Track every tool signature (tool_name + serialized arguments) requested
        # so far in this user turn. This persists across ALL iterations of the
        # AI -> tool -> AI loop, so a tool requested again in a later iteration
        # is never executed twice.
        executed_tool_signatures: set[str] = set()
        # Prevent infinite tool call loops
        max_tool_iterations = 20  # Safety limit to prevent infinite loops

        for iteration in range(max_tool_iterations):
            # Use AIService to generate with tools
            response_content, tool_calls = await self.ai_service.generate_with_tools(
                messages=self.memory_manager.get_messages_for_ai(),
                tools=tool_defs if tool_defs else [],
                temperature=0.7,
            )

            # If AI requested no tool calls, we are done
            if not tool_calls:
                # This is the final response
                return response_content, all_tool_calls

            # Check for repeated tool calls (same tool name and arguments) against
            # every signature already requested in this user turn. A tool requested
            # again in a later iteration is NOT executed again.
            repeated_tool_calls = []
            new_tool_calls = []
            import json
            for tool_call in tool_calls:
                # Create a signature for tracking: tool_name + serialized arguments
                try:
                    args_str = json.dumps(tool_call.arguments, sort_keys=True)
                except (TypeError, ValueError):
                    # Fallback for non-serializable arguments
                    args_str = str(tool_call.arguments)
                tool_key = f"{tool_call.tool_name}:{args_str}"

                if tool_key in executed_tool_signatures:
                    repeated_tool_calls.append(tool_call)
                else:
                    executed_tool_signatures.add(tool_key)
                    new_tool_calls.append(tool_call)

            # If all requested tool calls were already executed earlier in this
            # turn, stop the tool loop and generate the final response directly.
            if not new_tool_calls:
                # Build a valid history (never starts with role="tool") and
                # generate the final answer WITHOUT tools.
                valid_messages = self._get_valid_message_history_for_fallback()
                final_response = await self.ai_service.generate(
                    messages=valid_messages,
                    temperature=0.7,
                )
                # Still accumulate the repeated calls in all_tool_calls for tracking
                all_tool_calls.extend(repeated_tool_calls)
                return final_response, all_tool_calls

            # Execute new tool calls through orchestrator (respects max_tool_calls limit)
            results = await self.orchestrator.execute_tool_calls(new_tool_calls)

            # Add the assistant message containing these tool calls to memory
            # FIRST, so tool results pair with it: assistant(tool_calls) -> tool
            self.memory_manager.add_assistant_message(
                response_content, tool_calls=new_tool_calls
            )

            # Format results for conversation
            tool_messages = ToolOrchestrator.format_tool_results_for_messages(
                new_tool_calls,
                results
            )

            # Add tool results to memory after their assistant tool_calls message
            for message in tool_messages:
                if message["role"] == "tool":
                    self.memory_manager.context.turns.append(message)

            # Accumulate tool calls requested (including those that may have been limited)
            all_tool_calls.extend(new_tool_calls)
            # Also track repeated calls that we didn't execute
            all_tool_calls.extend(repeated_tool_calls)

            # If we've reached the max iterations, break to prevent infinite loop
            if iteration == max_tool_iterations - 1:
                break

        # If we exited the loop due to max iterations, generate final response without tools
        # First, ensure we have a valid message history that doesn't start with tool messages
        valid_messages = self._get_valid_message_history_for_fallback()
        final_response = await self.ai_service.generate(
            messages=valid_messages,
            temperature=0.7,
        )
        return final_response, all_tool_calls

    def _get_valid_message_history_for_fallback(self) -> list[dict]:
        """
        Get a valid message history for fallback generation that doesn't start with orphaned tool messages.

        Returns:
            List of message dictionaries suitable for AI service consumption
        """
        messages = self.memory_manager.get_messages_for_ai()

        # If messages start with tool messages, we need to trim them until we get to a non-tool message
        # or until we have at least a user message
        if messages:
            # Find the first non-tool message index
            first_non_tool_index = 0
            for i, msg in enumerate(messages):
                if msg.get("role") != "tool":
                    first_non_tool_index = i
                    break
            else:
                # All messages are tool messages - this shouldn't happen in normal operation
                # but if it does, return just the last user message if we can find it
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        return [messages[i]]
                # If no user message found, return empty list (will cause AI to use system prompt only)
                return []

            # If we found tool messages at the start, trim them
            if first_non_tool_index > 0:
                # Check if what we're trimming are orphaned tool messages (not paired with assistant tool_calls)
                # For safety, we'll trim leading tool messages but ensure we keep at least a user message
                trimmed_messages = messages[first_non_tool_index:]

                # Ensure we have at least a user message in our history
                has_user_message = any(msg.get("role") == "user" for msg in trimmed_messages)
                if not has_user_message:
                    # Look for user message in original messages
                    for i in range(len(messages) - 1, -1, -1):
                        if messages[i].get("role") == "user":
                            # Return from that user message onward
                            return messages[i:]
                    # If no user message found, return what we have
                    return trimmed_messages

                return trimmed_messages

        return messages

    def _create_intent_from_user_input(self, user_input: str) -> Intent:
        """
        Create an intent from user input.
        This is a simplified implementation - in a full system, this would use AI to interpret intent.

        Args:
            user_input: The user's input string

        Returns:
            Intent: The interpreted intent
        """
        # Simple keyword-based intent detection for demonstration
        user_lower = user_input.lower().strip()

        # Map common phrases to intent actions
        if any(word in user_lower for word in ["read", "show", "display", "cat", "open", "view"]):
            if "." in user_lower or "/" in user_lower or "\\" in user_lower:
                # Likely a file path mentioned
                return Intent(
                    action="read_file",
                    arguments={"path": self._extract_file_path(user_input)},
                    confidence=0.8,
                    original_request=user_input
                )
            else:
                return Intent(
                    action="read_file",
                    arguments={"path": "."},  # Default to current directory
                    confidence=0.5,
                    original_request=user_input
                )

        elif any(word in user_lower for word in ["create", "make", "mkdir"]):
            extracted_path = self._extract_file_path(user_input)
            path = extracted_path if extracted_path else "new_folder"
            return Intent(
                action="create_directory",
                arguments={"path": path},
                confidence=0.8,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["list", "dir", "ls", "browse"]):
            extracted_path = self._extract_file_path(user_input)
            path = extracted_path if extracted_path else "."
            # Check if this is likely a genuine ls command or just coincidental match
            word_match = next((word for word in ["list", "dir", "ls", "browse"] if word in user_lower), None)
            confidence = 0.8
            if word_match == "ls" and not (
                user_lower.startswith("ls ") or
                user_lower.endswith(" ls") or
                " ls " in user_lower or
                user_lower == "ls"
            ):
                # If we matched "ls" but it's not standing alone, reduce confidence
                confidence = 0.3
            return Intent(
                action="list_directory",
                arguments={"path": path},
                confidence=confidence,
                original_request=user_input
            )

        elif any(word in user_lower.split() for word in ["write", "save", "put"]) or \
             any(phrase in user_lower for phrase in ["create a file", "make a file"]):
            # Try to extract path and content from the user input
            path, content = self._extract_write_file_args(user_input)
            if path is not None and content is not None:
                arguments = {"path": path, "content": content}
                confidence = 0.8
            else:
                # Fallback to hardcoded values
                arguments = {"path": "new_file.txt", "content": "File content"}
                confidence = 0.6
            return Intent(
                action="write_file",
                arguments=arguments,
                confidence=confidence,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["time", "clock"]):
            return Intent(
                action="get_current_time",
                arguments={},
                confidence=0.6,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["calculate", "compute", "math", "solve", "what is"]):
            # Extract expression using simple deterministic pattern matching: look for trigger at start
            trigger_phrases = ["what is", "calculate", "compute", "math", "solve"]
            expression = None
            for phrase in trigger_phrases:
                if user_lower.startswith(phrase):
                    expression = user_input[len(phrase):].strip()
                    break
            # If we didn't find a trigger at the start or the expression is empty or doesn't look like an expression (no digits), use fallback
            if not expression or not any(c.isdigit() for c in expression):
                expression = "2+2"
            return Intent(
                action="calculate",
                arguments={"expression": expression},
                confidence=0.7,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["system", "info", "spec", "status"]):
            return Intent(
                action="get_system_info",
                arguments={},
                confidence=0.8,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["directory", "folder", "pwd", "where"]):
            return Intent(
                action="get_current_directory",
                arguments={},
                confidence=0.8,
                original_request=user_input
            )

        elif any(word in user_lower for word in ["environment", "env", "variable", "vars"]):
            return Intent(
                action="get_environment_info",
                arguments={},
                confidence=0.8,
                original_request=user_input
            )

        else:
            # Default to a safe action - get current time
            return Intent(
                action="get_current_time",
                arguments={},
                confidence=0.3,
                original_request=user_input
            )

    def _extract_file_path(self, user_input: str) -> str:
        """
        Extract a file path from user input.
        Improved implementation that looks for common path patterns and natural language constructs.

        Args:
            user_input: The user's input string

        Returns:
            str: Extracted path or empty string if not found (caller should use fallback)
        """
        # Define patterns for natural language path extraction
        patterns = [
            r'read the file (\S+)',
            r'open (\S+)',
            r'show (\S+)',
            r'display (\S+)',
            r'cat (\S+)',
            r'view (\S+)',
            r'list the files in (\S+)',
            r'list directory (\S+)',
            r'list (\S+)',
            r'dir (\S+)',
            r'ls (\S+)',
            r'browse the (\S+) directory',
            r'browse (\S+)',
            r'create a directory called (\S+)',
            r'make a directory called (\S+)',
            r'create a folder named (\S+)',
            r'make a folder named (\S+)',
            r'create directory (\S+)',
            r'make directory (\S+)',
            r'create folder (\S+)',
            r'make folder (\S+)',
        ]

        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                path = match.group(1)
                if path:  # Ensure we got a non-empty match
                    return path

        # Fallback to word-based path detection
        words = user_input.split()
        for word in words:
            # Check for path-like patterns: contains dot and slash/backslash
            if "." in word and ("/" in word or "\\" in word):
                return word
            # Check for backslash alone
            if "\\" in word:
                return word
            # Check for path starters: ./, .\, /, or drive letter (e.g., C:)
            if word.startswith("./") or word.startswith(".\\") or word.startswith("/") or (len(word) > 1 and word[1] == ":"):
                return word
            # Check for words with dot (file extension) but not just "." or ".."
            if "." in word and word not in [".", ".."]:
                return word

        # If no path found, return empty string (caller will use fallback)
        return ""

    def _extract_write_file_args(self, user_input: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract path and content for a write_file intent from user input.
        Uses simple deterministic pattern matching for common patterns.

        Args:
            user_input: The user's input string

        Returns:
            Tuple of (path, content). Returns (None, None) if extraction fails.
        """
        import re

        # Normalize quotes: replace smart quotes with straight quotes for simplicity
        normalized = user_input.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

        # Define patterns to try, in order.
        # Each pattern is a tuple (regex, function_to_extract_path_and_content_from_match)
        # The function should return (path, content) from the match groups.
        patterns = [
            # Pattern: write <content> to <path>
            (r'write\s+(.+?)\s+to\s+(\S+)', lambda m: (m.group(2).strip(), m.group(1).strip())),
            # Pattern: save '<content>' in <path>
            (r'save\s+["\'](.+?)["\']\s+in\s+(\S+)', lambda m: (m.group(2).strip(), m.group(1).strip())),
            # Pattern: create a file called <path> containing <content>
            (r'create a file called\s+(\S+)\s+containing\s+(.+)', lambda m: (m.group(1).strip(), m.group(2).strip())),
            # Pattern: save <content> to <path> (without quotes)
            (r'save\s+(.+?)\s+to\s+(\S+)', lambda m: (m.group(2).strip(), m.group(1).strip())),
        ]

        for pattern, extract_func in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                path, content = extract_func(match)
                # Basic validation: path should not be empty and content should not be empty
                if path and content:
                    return path, content

        # If none of the patterns matched, return (None, None) to trigger fallback.
        return None, None

    async def _execute_action_step(self, step: ActionStep) -> ActionResult:
        """
        Execute a single action step and return the result.

        Args:
            step: The ActionStep to execute

        Returns:
            ActionResult: The result of executing the step
        """
        try:
            # Execute the tool through the registry
            tool_result = await self.tool_registry.execute(
                step.tool_name,
                **step.arguments
            )

            # Convert ToolResult to ActionResult
            action_result = ActionResult(
                step=step,
                success=tool_result.success,
                content=tool_result.content,
                error=tool_result.error,
                safety_classification=step.safety_classification,
                metadata=tool_result.metadata
            )

            # Handle the result (store in memory, etc.)
            self.result_handler.handle_result(action_result)

            return action_result

        except Exception as e:
            # Create a failed result
            action_result = ActionResult(
                step=step,
                success=False,
                error=str(e),
                safety_classification=step.safety_classification
            )
            self.result_handler.handle_result(action_result)
            return action_result

    async def _execute_action_step_dry_run(self, step: ActionStep) -> ToolResult:
        """
        Simulate executing an action step for dry-run mode.

        Args:
            step: The ActionStep to simulate

        Returns:
            ToolResult: Simulated result of executing the step
        """
        # For dry run, we just return a simulated success result
        # In a more sophisticated implementation, we might validate arguments
        # or check preconditions without actually executing
        return ToolResult(
            success=True,
            content=f"[DRY RUN] Would execute: {step.description}",
            metadata={"dry_run": True}
        )

    async def run(self):
        """Run the interactive conversation loop."""
        self.running = True

        # Display welcome banner
        print("IRIS - Intelligent Responsive Interactive System")
        print("Version: 0.3.0")
        print("Type 'exit' or 'quit' to close IRIS.")
        print("Type '/help' for available commands.\n")

        # Initialize AI service
        if not await self.initialize():
            return

        # Main conversation loop
        try:
            while self.running:
                try:
                    # Get user input
                    user_input = input("IRIS> ")

                    # Process input
                    should_continue = await self.handle_user_input(user_input)

                    if not should_continue:
                        break

                except EOFError:
                    # Handle Ctrl+D / EOF
                    print("\n")
                    break
                except KeyboardInterrupt:
                    # Handle Ctrl+C
                    print("\n")
                    break

        finally:
            # Clean up
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        print("Goodbye!")
        if self.ai_service:
            await self.ai_service.close()


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print("\n")
    sys.exit(0)


def main():
    """Main entry point for the IRIS CLI."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Create and run conversation
    conversation = IRISConversation()

    try:
        asyncio.run(conversation.run())
    except KeyboardInterrupt:
        print("\n")
    except Exception as e:
        # Final safety net - sanitize any unexpected errors
        error_msg = str(e)
        if any(word in error_msg.lower() for word in ['key', 'token', 'password', 'secret']):
            print("\n❌ An unexpected error occurred. Please check your configuration.")
        else:
            print(f"\n❌ An unexpected error occurred: {error_msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()