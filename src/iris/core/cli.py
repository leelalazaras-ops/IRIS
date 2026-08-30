"""
Command-line interface for IRIS.
"""

import asyncio
import sys
import signal
from typing import Optional

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


class IRISConversation:
    """Manages an interactive conversation session with IRIS."""

    def __init__(self):
        """Initialize the conversation manager."""
        self.ai_service: Optional[AIService] = None
        self.conversation_history: list[dict[str, str]] = []
        self.running = False
        self.tool_registry = self._initialize_tool_registry()
        self.orchestrator = ToolOrchestrator(
            self.tool_registry,
            OrchestrationConfig(max_tool_calls=5, enable_tools=True)
        )
        self.tools_enabled = True  # Can be toggled by user

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
            print(f"\n❌ Configuration error: {e.message}")
            print("\nPlease check your environment variables:")
            print("  - IRIS_AI_PROVIDER (default: openai-compatible)")
            print("  - IRIS_AI_BASE_URL (required for openai-compatible)")
            print("  - IRIS_AI_API_KEY (required for openai-compatible)")
            print("  - IRIS_AI_MODEL (default: gpt-3.5-turbo)")
            print("\nSee .env.example for configuration examples.")
            return False
        except Exception as e:
            print(f"\n❌ Unexpected error during initialization: {str(e)}")
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

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_input.strip()
        })

        try:
            if self.tools_enabled:
                # Use orchestrator for tool-enabled conversation
                response, tool_calls = await self._process_with_tools()
            else:
                # Standard conversation without tools
                response = await self.ai_service.generate(
                    messages=self.conversation_history,
                    temperature=0.7,
                )
                tool_calls = []

            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response
            })

            # Display response
            print(f"\nIRIS: {response}\n")

            # Display tool execution info if any
            if tool_calls:
                for tc in tool_calls:
                    print(f"  🔧 Tool executed: {tc.tool_name}")

        except AIError as e:
            # Remove the user message from history since we couldn't process it
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            print(f"\n❌ AI Error: {e.message}")
            print("Please try again or check your configuration.\n")
        except Exception as e:
            # Remove the user message from history
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            # Sanitize error message to avoid leaking sensitive data
            error_msg = str(e)
            # Don't expose API keys or tokens in error messages
            for sensitive_word in ['key', 'token', 'password', 'secret']:
                if sensitive_word in error_msg.lower():
                    error_msg = "An error occurred. Please check your configuration."
                    break
            print(f"\n❌ Error: {error_msg}")
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

        if cmd == "tools":
            # List all available tools
            print("\n📦 Available Tools:\n")
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

        else:
            print(f"\n❌ Unknown command: /{cmd}")
            print("Type '/help' for available commands.\n")
            return True

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

        while True:
            # Use AIService to generate with tools
            response_content, tool_calls = await self.ai_service.generate_with_tools(
                messages=self.conversation_history,
                tools=tool_defs if tool_defs else [],
                temperature=0.7,
            )

            # If AI requested no tool calls, we are done
            if not tool_calls:
                # This is the final response
                return response_content, all_tool_calls

            # Execute tool calls through orchestrator (respects max_tool_calls limit)
            results = await self.orchestrator.execute_tool_calls(tool_calls)

            # Format results for conversation
            tool_messages = ToolOrchestrator.format_tool_results_for_messages(
                tool_calls,
                results
            )

            # Add tool results to conversation history
            self.conversation_history.extend(tool_messages)

            # Accumulate tool calls requested (including those that may have been limited)
            all_tool_calls.extend(tool_calls)

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
        print("Goodbye! 👋")
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
