# IRIS

**I**ntelligent **R**esponsive **I**nteractive **S**ystem

IRIS is a modular AI assistant framework designed for extensibility and clean architecture.

## Project Status

✅ **Phase 1 Complete** - AI Core with provider abstraction
✅ **Phase 2 Complete** - Interactive CLI conversation loop
✅ **Phase 3 Complete** - Tool execution framework
🚧 **In Development** - Additional capabilities planned

## Architecture

IRIS follows a modular architecture with clear separation of concerns:

```
src/iris/
├── core/       # Core system components and utilities
├── ai/         # AI model integrations and processing (✅ Phase 1 complete)
├── voice/      # Voice input/output handling (planned)
├── tools/      # Tool definitions and execution (planned)
├── memory/     # Context and memory management (planned)
├── vision/     # Vision and image processing (planned)
├── web/        # Web interface and API (planned)
├── ui/         # User interface components (planned)
└── security/   # Security and authentication (planned)
```

### Phase 1: AI Core ✅

Provider-independent AI architecture that allows switching between AI providers through configuration:

- **Provider abstraction**: Clean interface for any OpenAI-compatible API
- **Configurable runtime**: Connect to OpenAI, OmniRoute, or other services via environment variables
- **Comprehensive testing**: Full test coverage with offline tests (no API keys needed)
- **Security-first**: Secret sanitization in logs and error messages

### Phase 2: Interactive CLI ✅

Terminal-based conversation interface with IRIS:

- **Interactive conversation loop**: Natural back-and-forth chat interface
- **Session history**: Context-aware responses within the current session
- **Graceful error handling**: Clear error messages without exposing sensitive data
- **Multiple exit methods**: exit, quit, Ctrl+C, Ctrl+D
- **Provider integration**: Works with any configured OpenAI-compatible provider

### Phase 3: Tool System ✅

Secure tool execution framework:

- **9 Built-in tools**: Filesystem, system info, and utility operations
- **Safe execution**: Path validation, no arbitrary code execution
- **Security-first**: Sensitive data filtering, no shell access
- **Type-safe**: Full argument validation with type checking
- **CLI integration**: `/tools` and `/help` commands

See [AI Architecture Documentation](docs/AI_ARCHITECTURE.md) for detailed information.

## Setup

### Prerequisites

- Python 3.10 or higher
- pip (Python package installer)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd IRIS
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e ".[dev]"
```

4. Copy the environment template and configure your AI provider:
```bash
cp .env.example .env
```

5. Edit `.env` with your AI provider settings:
```bash
# For OpenAI
IRIS_AI_PROVIDER=openai-compatible
IRIS_AI_BASE_URL=https://api.openai.com/v1
IRIS_AI_API_KEY=your_openai_api_key_here
IRIS_AI_MODEL=gpt-3.5-turbo

# For OmniRoute or other OpenAI-compatible services
IRIS_AI_PROVIDER=openai-compatible
IRIS_AI_BASE_URL=https://your-service-endpoint.com/v1
IRIS_AI_API_KEY=your_api_key_here
IRIS_AI_MODEL=gpt-4

# For testing without API keys
IRIS_AI_PROVIDER=mock
```

## Usage

### Running IRIS

Start the interactive conversation interface:

```bash
iris
```

Or with the virtual environment activated:
```bash
python -m iris.core.cli
```

This will start an interactive session:

```
IRIS - Intelligent Responsive Interactive System
Version: 0.3.0
Type 'exit' or 'quit' to close IRIS.
Type '/help' for available commands.

IRIS> Hello!

IRIS: Hello! How can I help you today?

IRIS> 
```

**Commands:**
- Type your message and press Enter to chat with IRIS
- Type `/tools` to list available tools
- Type `/help` to see all commands
- Type `exit` or `quit` to close IRIS
- Press `Ctrl+C` or `Ctrl+D` to exit

**Note**: IRIS maintains conversation history during the current session for context-aware responses.

## Development

### Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=iris --cov-report=html
```

All tests pass without requiring API keys (using the mock provider).

### Project Structure

- `src/iris/` - Main package source code
- `tests/` - Test suite
- `docs/` - Documentation
- `scripts/` - Development and utility scripts
- `config/` - Configuration files

## Design Principles

- **Modular**: Each component is independently maintainable
- **Extensible**: Easy to add new capabilities
- **Clean**: Following Python best practices and PEP standards
- **Testable**: Comprehensive test coverage from the start

## License

MIT License - See LICENSE file for details

## Contributing

This is currently in early development. Contribution guidelines will be established as the project matures.
