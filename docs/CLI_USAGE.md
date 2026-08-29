# IRIS CLI Usage Guide

## Overview

IRIS provides an interactive command-line interface for conversational AI interactions. The CLI maintains conversation history during your session, enabling context-aware multi-turn conversations.

## Starting IRIS

### From Installed Package

If you've installed IRIS with `pip install -e .`:

```bash
iris
```

### From Source

```bash
python -m iris.core.cli
```

### From Virtual Environment

```bash
# Activate virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Then run IRIS
iris
```

## Using IRIS

### Basic Conversation

When you start IRIS, you'll see:

```
IRIS - Intelligent Responsive Interactive System
Version: 0.2.0
Type 'exit' or 'quit' to close IRIS.

IRIS>
```

Simply type your message and press Enter:

```
IRIS> Hello, how are you?

IRIS: Hello! I'm doing well, thank you for asking. How can I help you today?

IRIS> What is Python?

IRIS: Python is a high-level, interpreted programming language known for its simplicity and readability...

IRIS>
```

### Commands

- **Regular input**: Type any message and press Enter to chat
- **exit**: Type `exit` to close IRIS gracefully
- **quit**: Type `quit` to close IRIS gracefully
- **Ctrl+C**: Press Ctrl+C to interrupt and exit
- **Ctrl+D**: Press Ctrl+D (or Ctrl+Z on Windows) for EOF exit
- **Empty input**: Pressing Enter without typing anything is ignored

All exit methods are case-insensitive (`EXIT`, `Quit`, etc. all work).

## Conversation History

IRIS maintains conversation history **during the current session only**:

- Each message you send is added to the conversation context
- AI responses reference previous messages in the session
- History is cleared when you exit IRIS
- No persistent memory between sessions (planned for future phases)

Example of context-aware conversation:

```
IRIS> My name is Alex

IRIS: Nice to meet you, Alex! How can I help you today?

IRIS> What's my name?

IRIS: Your name is Alex, as you just told me.

IRIS> exit
Goodbye! 👋
```

After restarting IRIS, the previous conversation is forgotten.

## Configuration

IRIS behavior is controlled via environment variables. See `.env.example` for all options.

### Required Configuration

Set these in your `.env` file before starting IRIS:

```bash
# AI Provider Configuration
IRIS_AI_PROVIDER=openai-compatible
IRIS_AI_BASE_URL=https://api.openai.com/v1
IRIS_AI_API_KEY=your_api_key_here
IRIS_AI_MODEL=gpt-3.5-turbo
```

### Configuration Errors

If IRIS cannot start due to missing or invalid configuration, you'll see:

```
❌ Configuration error: IRIS_AI_BASE_URL is required for openai-compatible provider

Please check your environment variables:
  - IRIS_AI_PROVIDER (default: openai-compatible)
  - IRIS_AI_BASE_URL (required for openai-compatible)
  - IRIS_AI_API_KEY (required for openai-compatible)
  - IRIS_AI_MODEL (default: gpt-3.5-turbo)

See .env.example for configuration examples.
```

Fix the configuration and restart IRIS.

## Error Handling

### AI Errors

If the AI service encounters an error during generation:

```
IRIS> Hello

❌ AI Error: Authentication failed
Please try again or check your configuration.

IRIS>
```

The conversation continues, but the failed message is not added to history.

### Network Errors

If the provider cannot be reached:

```
IRIS> What's the weather?

❌ Error: Connection timeout
Please try again.

IRIS>
```

### Sensitive Data Protection

IRIS automatically sanitizes error messages to prevent API keys, tokens, passwords, or secrets from being displayed:

```
# Instead of showing:
❌ Error: Invalid API key sk-1234567890abcdef

# IRIS shows:
❌ Error: An error occurred. Please check your configuration.
```

## Examples

### Simple Q&A

```
IRIS> What is the capital of France?

IRIS: The capital of France is Paris.

IRIS> How many people live there?

IRIS: Paris has a population of approximately 2.2 million people within the city proper...

IRIS>
```

### Multi-turn Conversation

```
IRIS> I'm learning Python

IRIS: That's great! Python is an excellent language to learn. What would you like to know about it?

IRIS> What should I learn first?

IRIS: For beginners, I recommend starting with:
1. Basic syntax and variables
2. Data types (strings, numbers, lists)
3. Control flow (if statements, loops)
...

IRIS> Can you explain loops?

IRIS: Of course! In Python, loops allow you to repeat code multiple times...

IRIS>
```

### Using Mock Provider for Testing

To test IRIS without an API key, use the mock provider:

```bash
# In .env
IRIS_AI_PROVIDER=mock
```

The mock provider returns deterministic responses without making network calls:

```
IRIS> Hello

IRIS: This is a mock response.

IRIS> How are you?

IRIS: This is a mock response.

IRIS>
```

## Tips

1. **Keep conversations focused**: While IRIS maintains session history, very long conversations may exceed model context limits

2. **Use clear language**: The AI responds best to clear, specific questions

3. **Check configuration first**: Most errors are due to missing or incorrect environment variables

4. **Test with mock provider**: Use `IRIS_AI_PROVIDER=mock` to verify IRIS works before configuring a real API

5. **Review .env.example**: It contains all available configuration options with examples

## Troubleshooting

### IRIS won't start

1. Check that you've activated your virtual environment
2. Verify installation: `pip show iris`
3. Check configuration: ensure `.env` exists and has required variables
4. Try mock provider: `IRIS_AI_PROVIDER=mock` in `.env`

### Responses are slow

1. Check your network connection
2. Increase timeout: `IRIS_AI_TIMEOUT=60.0` in `.env`
3. Try a faster model if available

### "Configuration error" on startup

1. Copy `.env.example` to `.env` if you haven't already
2. Fill in all required fields for your provider
3. Ensure no extra spaces around `=` in `.env`
4. Check that variable names match exactly (case-sensitive)

### API authentication errors

1. Verify your API key is correct (no extra spaces)
2. Check that the base URL is correct for your provider
3. Ensure your API key has the required permissions
4. Test the API key using curl or another tool first

## Limitations (Current Phase)

Phase 2 has the following intentional limitations:

- ❌ **No persistent memory**: History is cleared when you exit
- ❌ **No streaming**: Responses appear after generation completes
- ❌ **No tool execution**: Cannot execute code, search web, etc.
- ❌ **No multimodal input**: Text only (no images, voice, etc.)
- ❌ **No GUI**: Terminal only

These features are planned for future phases.

## Next Steps

- See [AI Architecture](AI_ARCHITECTURE.md) for technical details
- See [README.md](../README.md) for installation instructions
- Check `.env.example` for all configuration options
