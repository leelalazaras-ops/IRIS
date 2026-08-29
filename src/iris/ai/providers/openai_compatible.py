"""
OpenAI-compatible HTTP provider for IRIS.

Communicates with any OpenAI-compatible chat completion API.
"""

import httpx
from iris.ai.provider import AIProvider, AIRequest, AIResponse
from iris.ai.exceptions import (
    AuthenticationError,
    TimeoutError,
    ResponseError,
    ProviderError,
)


class OpenAICompatibleProvider(AIProvider):
    """
    Provider for OpenAI-compatible chat completion APIs.

    This provider can connect to:
    - OpenAI API
    - OmniRoute
    - Any other service implementing the OpenAI chat/completions format
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ):
        """
        Initialize the OpenAI-compatible provider.

        Args:
            base_url: Base URL for the API (e.g., "https://api.openai.com/v1")
            api_key: API authentication key
            model: Model identifier to use
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate a response using the OpenAI-compatible API.

        Args:
            request: The AI request to process

        Returns:
            AIResponse containing the generated content

        Raises:
            AuthenticationError: If API authentication fails (401)
            TimeoutError: If the request times out
            ResponseError: If the response format is invalid
            ProviderError: For other API errors
        """
        endpoint = f"{self.base_url}/chat/completions"

        # Build request payload
        payload = {
            "model": self.model,
            "messages": request.messages,
            "temperature": request.temperature,
        }

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # Add any provider-specific metadata
        payload.update(request.metadata)

        try:
            response = await self._client.post(endpoint, json=payload)

            # Handle HTTP errors
            if response.status_code == 401:
                raise AuthenticationError(
                    "API authentication failed",
                    {"status_code": response.status_code}
                )
            elif response.status_code == 429:
                raise ProviderError(
                    "Rate limit exceeded",
                    {"status_code": response.status_code}
                )
            elif response.status_code >= 400:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get("error", {}).get("message", error_detail)
                except Exception:
                    error_detail = response.text[:200]

                raise ProviderError(
                    f"API request failed: {error_detail}",
                    {"status_code": response.status_code}
                )

            # Parse response
            try:
                data = response.json()
            except Exception as e:
                raise ResponseError(
                    f"Failed to parse API response as JSON: {e}",
                    {"response_text": response.text[:200]}
                )

            # Extract content from response
            try:
                choices = data.get("choices", [])
                if not choices:
                    raise ResponseError(
                        "API response contained no choices",
                        {"response": data}
                    )

                message = choices[0].get("message", {})
                content = message.get("content", "")

                usage = data.get("usage", {})
                model_used = data.get("model", self.model)

                return AIResponse(
                    content=content,
                    model=model_used,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    metadata={
                        "finish_reason": choices[0].get("finish_reason"),
                    }
                )
            except (KeyError, IndexError, TypeError) as e:
                raise ResponseError(
                    f"Invalid response structure: {e}",
                    {"response": str(data)[:200]}
                )

        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"Request timed out after {self.timeout}s",
                {"timeout": self.timeout}
            )
        except (AuthenticationError, TimeoutError, ResponseError, ProviderError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise ProviderError(
                f"Unexpected error during API request: {type(e).__name__}",
                {"error": str(e)}
            )

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        await self._client.aclose()
