"""
IRIS AI Core

Provider-independent AI service layer for IRIS.
"""

from iris.ai.service import AIService
from iris.ai.exceptions import (
    AIError,
    ConfigurationError,
    ProviderError,
    AuthenticationError,
    TimeoutError,
    ResponseError,
)

__all__ = [
    "AIService",
    "AIError",
    "ConfigurationError",
    "ProviderError",
    "AuthenticationError",
    "TimeoutError",
    "ResponseError",
]
