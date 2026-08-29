# IRIS AI Core Architecture

## Overview

IRIS has a clean, provider-independent AI architecture that allows the runtime AI provider to be changed through configuration without modifying application code.

**Important**: Claude Code + OmniRoute is the development environment. IRIS's AI runtime is completely independent and configurable.

## Architecture

```
IRIS Application
       |
       v
   AI Service (service.py)
       |
       v
 Provider Interface (provider.py)
       |
       +---> OpenAI-Compatible Provider (providers/openai_compatible.py)
       |
       +---> Mock Provider (providers/mock.py)
```

### Components

#### 1. Configuration (`config.py`)

Loads AI settings from environment variables:

- `IRIS_AI_PROVIDER` - Provider type (e.g., "openai-compatible", "mock")
- `IRIS_AI_BASE_URL` - API endpoint URL
- `IRIS_AI_API_KEY` - Authentication key
- `IRIS_AI_MODEL` - Model identifier
- `IRIS_AI_TIMEOUT` - Request timeout in seconds

Configuration validation happens at load time, preventing runtime errors from missing settings.

#### 2. Provider Interface (`provider.py`)

Abstract base class defining the contract all providers must implement:

- `AIRequest` - Request data model (messages, temperature, max_tokens, metadata)
- `AIResponse` - Response data model (content, model, usage, metadata)
- `AIProvider` - Abstract provider interface with `generate()` and `close()` methods

#### 3. Providers

##### OpenAI-Compatible Provider (`providers/openai_compatible.py`)

HTTP provider that communicates with any OpenAI-compatible chat completion API.

Features:
- Async HTTP client using `httpx`
- Configurable endpoint/key/model/timeout
- Comprehensive error handling
- Secret sanitization in errors
- Compatible with: OpenAI API, OmniRoute, and other OpenAI-compatible services

##### Mock Provider (`providers/mock.py`)

Deterministic provider for testing without network calls or API keys.

Features:
- Returns configurable mock responses
- Tracks call count
- Calculates mock usage metrics
- No network dependencies

#### 4. AI Service (`service.py`)

High-level facade that IRIS application code uses for AI operations.

The service:
- Abstracts provider implementation details
- Lazy-loads providers on first use
- Provides simple `generate()` method for text generation
- Provides `generate_with_metadata()` for full response details
- Handles resource cleanup

#### 5. Exceptions (`exceptions.py`)

Specific exception hierarchy for clear error handling:

```
AIError (base)
├── ConfigurationError (invalid/missing config)
└── ProviderError (base for provider errors)
    ├── AuthenticationError (401, invalid API key)
    ├── TimeoutError (request timeout)
    └── ResponseError (invalid response format)
```

All exceptions sanitize sensitive data to prevent API keys from appearing in logs.

## Usage

### Basic Usage

```python
from iris.ai import AIService

# Create service (loads config from environment)
service = AIService()

# Generate a response
response = await service.generate(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ],
    temperature=0.7,
    max_tokens=150
)

print(response)  # "I'm doing well, thank you for asking! How can I help you today?"

# Clean up
await service.close()
```

### Advanced Usage with Metadata

```python
from iris.ai import AIService

service = AIService()

# Get full response with usage information
response = await service.generate_with_metadata(
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    temperature=0.5,
    max_tokens=200
)

print(f"Content: {response.content}")
print(f"Model: {response.model}")
print(f"Tokens used: {response.usage['total_tokens']}")
print(f"Finish reason: {response.metadata.get('finish_reason')}")

await service.close()
```

### Using Mock Provider for Tests

```python
import os
from iris.ai import AIService

# Configure mock provider
os.environ["IRIS_AI_PROVIDER"] = "mock"

service = AIService()

# No network call, returns deterministic mock response
response = await service.generate(
    messages=[{"role": "user", "content": "Test"}]
)

assert isinstance(response, str)

await service.close()
```

## Connecting to OmniRoute

To connect IRIS to OmniRoute (or any other OpenAI-compatible service):

1. Set environment variables in `.env`:

```bash
IRIS_AI_PROVIDER=openai-compatible
IRIS_AI_BASE_URL=https://your-omniroute-endpoint.com/v1
IRIS_AI_API_KEY=your_omniroute_api_key
IRIS_AI_MODEL=gpt-4
IRIS_AI_TIMEOUT=60.0
```

2. That's it! No code changes needed.

The OpenAI-compatible provider will automatically use the configured endpoint.

### OmniRoute Integration Details

OmniRoute implements the OpenAI chat completion API format, so IRIS's OpenAI-compatible provider works seamlessly:

- **Request format**: Standard OpenAI `/chat/completions` payload
- **Response format**: Standard OpenAI response structure
- **Authentication**: Bearer token in Authorization header
- **Error handling**: Standard HTTP status codes (401, 429, 500, etc.)

## Testing

### Running Tests

All tests run offline without requiring API keys:

```bash
# Run all AI tests
pytest tests/iris/ai/

# Run with coverage
pytest tests/iris/ai/ --cov=iris.ai --cov-report=html

# Run specific test file
pytest tests/iris/ai/test_service.py
```

### Test Coverage

The test suite covers:
- ✅ Configuration loading and validation
- ✅ Provider interface contract
- ✅ Mock provider behavior
- ✅ OpenAI-compatible provider (with mocked HTTP)
- ✅ AI service facade
- ✅ Exception handling and sanitization
- ✅ Successful API responses
- ✅ Authentication errors
- ✅ Timeout handling
- ✅ Malformed response handling
- ✅ Rate limiting
- ✅ Secret sanitization

All HTTP calls are mocked, so tests never contact real APIs.

## Security

### Secret Protection

1. **Configuration**: API keys never have default values in code
2. **Logging**: `__repr__` methods mask secrets with `***`
3. **Exceptions**: Authentication errors strip key/token fields from details
4. **Environment**: `.env.example` contains only placeholders
5. **Git**: `.env` is in `.gitignore` (never commit real keys)

### Safe Practices

- Load configuration from environment variables only
- Never log full exception details that might contain secrets
- Use the mock provider for tests (no real credentials needed)
- Validate configuration at startup to fail fast

## Extending the Architecture

### Adding a New Provider

1. Create a new provider class in `src/iris/ai/providers/`:

```python
from iris.ai.provider import AIProvider, AIRequest, AIResponse

class MyCustomProvider(AIProvider):
    async def generate(self, request: AIRequest) -> AIResponse:
        # Your implementation
        pass
    
    async def close(self) -> None:
        # Cleanup
        pass
```

2. Register it in `service.py`:

```python
elif self.config.provider == "my-custom":
    self._provider = MyCustomProvider(...)
```

3. Add configuration validation in `config.py` if needed.

### Provider Design Guidelines

- Accept configuration through constructor, not hardcoded
- Use async/await for I/O operations
- Raise specific exceptions from `exceptions.py`
- Sanitize secrets in error messages
- Implement proper resource cleanup in `close()`
- Return standard `AIResponse` objects

## Current Status

### Phase 1: AI Core ✅
- Provider abstraction
- OpenAI-compatible provider
- Mock provider for testing
- Configuration management
- Exception handling with secret sanitization

### Phase 2: Interactive CLI ✅
- Terminal conversation interface
- Session-based conversation history
- Graceful error handling
- Multiple exit methods
- Integration with AI service

See [CLI Usage Guide](CLI_USAGE.md) for interactive usage instructions.

## Future Phases

This AI core is designed to support IRIS's future capabilities:

- **Phase 3+**: Response streaming
- **Phase 4+**: Tool execution, function calling
- **Phase 5+**: Multi-modal inputs (vision, audio)
- **Phase 6+**: Persistent memory
- **Phase 7+**: Agent orchestration

The provider abstraction keeps these future features isolated from the core architecture.
