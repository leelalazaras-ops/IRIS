"""
Mock AI provider for testing.

Returns deterministic responses without network calls.
"""

from iris.ai.provider import AIProvider, AIRequest, AIResponse
from iris.tools.orchestration import ToolCall


class MockProvider(AIProvider):
    """
    Mock provider that returns deterministic responses.

    Useful for testing without requiring API keys or network access.
    Supports configurable tool call responses for testing orchestration.
    """

    def __init__(
        self,
        response_content: str = "This is a mock response.",
        tool_calls: list[ToolCall] | None = None
    ):
        """
        Initialize the mock provider.

        Args:
            response_content: The content to return in responses (when no tool calls)
            tool_calls: Optional list of ToolCall objects to return on first call
        """
        self.response_content = response_content
        self.tool_calls = tool_calls
        self.call_count = 0
        self._tool_calls_returned = False

    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate a mock response.

        Args:
            request: The AI request (used for tracking but doesn't affect output)

        Returns:
            AIResponse with deterministic mock content
        """
        self.call_count += 1

        # Return tool calls on first call if configured
        if self.tool_calls is not None and not self._tool_calls_returned:
            self._tool_calls_returned = True
            return AIResponse(
                content="",  # No content when making tool calls
                model="mock-model-v1",
                usage={
                    "prompt_tokens": len(str(request.messages)),
                    "completion_tokens": 0,
                    "total_tokens": len(str(request.messages)),
                },
                metadata={
                    "mock": True,
                    "call_count": self.call_count,
                },
                tool_calls=self.tool_calls
            )

        return AIResponse(
            content=self.response_content,
            model="mock-model-v1",
            usage={
                "prompt_tokens": len(str(request.messages)),
                "completion_tokens": len(self.response_content),
                "total_tokens": len(str(request.messages)) + len(self.response_content),
            },
            metadata={
                "mock": True,
                "call_count": self.call_count,
            },
            tool_calls=[]
        )

    async def close(self) -> None:
        """Close the mock provider (no-op)."""
        pass
