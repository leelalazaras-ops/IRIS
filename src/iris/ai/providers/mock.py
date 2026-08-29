"""
Mock AI provider for testing.

Returns deterministic responses without network calls.
"""

from iris.ai.provider import AIProvider, AIRequest, AIResponse


class MockProvider(AIProvider):
    """
    Mock provider that returns deterministic responses.

    Useful for testing without requiring API keys or network access.
    """

    def __init__(self, response_content: str = "This is a mock response."):
        """
        Initialize the mock provider.

        Args:
            response_content: The content to return in responses
        """
        self.response_content = response_content
        self.call_count = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate a mock response.

        Args:
            request: The AI request (used for tracking but doesn't affect output)

        Returns:
            AIResponse with deterministic mock content
        """
        self.call_count += 1

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
            }
        )

    async def close(self) -> None:
        """Close the mock provider (no-op)."""
        pass
