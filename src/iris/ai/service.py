"""
AI service facade for IRIS.

Provides a high-level interface for AI operations without exposing provider details.
"""

from typing import Optional
from iris.ai.config import AIConfig
from iris.ai.provider import AIProvider, AIRequest, AIResponse
from iris.ai.providers.mock import MockProvider
from iris.ai.providers.openai_compatible import OpenAICompatibleProvider
from iris.ai.exceptions import ConfigurationError


class AIService:
    """
    High-level AI service for IRIS.

    This service abstracts provider details and provides a clean interface
    for the rest of the IRIS system to interact with AI capabilities.
    """

    def __init__(self, config: Optional[AIConfig] = None):
        """
        Initialize the AI service.

        Args:
            config: AI configuration (loads from environment if not provided)

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config or AIConfig.from_env()
        self._provider: Optional[AIProvider] = None

    def _get_provider(self) -> AIProvider:
        """
        Get or create the AI provider instance.

        Returns:
            Configured AIProvider instance

        Raises:
            ConfigurationError: If provider type is unknown
        """
        if self._provider is None:
            if self.config.provider == "openai-compatible":
                self._provider = OpenAICompatibleProvider(
                    base_url=self.config.base_url,
                    api_key=self.config.api_key,
                    model=self.config.model,
                    timeout=self.config.timeout,
                )
            elif self.config.provider == "mock":
                self._provider = MockProvider()
            else:
                raise ConfigurationError(
                    f"Unknown provider: {self.config.provider}",
                    {"provider": self.config.provider}
                )

        return self._provider

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a response from the AI.

        Args:
            messages: List of conversation messages with 'role' and 'content' keys
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (optional)

        Returns:
            Generated text content

        Raises:
            AIError: If generation fails
        """
        request = AIRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        provider = self._get_provider()
        response = await provider.generate(request)

        return response.content

    async def generate_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """
        Generate a response with full metadata.

        Args:
            messages: List of conversation messages with 'role' and 'content' keys
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (optional)

        Returns:
            Complete AIResponse with usage and metadata

        Raises:
            AIError: If generation fails
        """
        request = AIRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        provider = self._get_provider()
        return await provider.generate(request)

    async def close(self) -> None:
        """
        Close the service and clean up resources.

        Should be called when the service is no longer needed.
        """
        if self._provider is not None:
            await self._provider.close()
            self._provider = None
