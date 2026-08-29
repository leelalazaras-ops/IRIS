"""
Provider abstraction for IRIS AI core.

Defines the interface that all AI providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIRequest:
    """
    Request to an AI provider.

    Attributes:
        messages: List of conversation messages
        temperature: Sampling temperature (0.0 to 2.0)
        max_tokens: Maximum tokens to generate
        metadata: Additional provider-specific options
    """
    messages: list[dict[str, str]]
    temperature: float = 0.7
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate request parameters."""
        if not self.messages:
            raise ValueError("messages cannot be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")


@dataclass
class AIResponse:
    """
    Response from an AI provider.

    Attributes:
        content: Generated text content
        model: Model identifier used
        usage: Token usage information
        metadata: Additional provider-specific data
    """
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    All providers must implement the generate method to handle AI requests.
    """

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate a response for the given request.

        Args:
            request: The AI request to process

        Returns:
            AIResponse containing the generated content

        Raises:
            ProviderError: If the provider encounters an error
            AuthenticationError: If authentication fails
            TimeoutError: If the request times out
            ResponseError: If the response is invalid
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Clean up provider resources.

        Should be called when the provider is no longer needed.
        """
        pass
