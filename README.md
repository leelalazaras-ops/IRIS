# IRIS

**I**ntelligent **R**esponsive **I**nteractive **S**ystem

IRIS is a modular AI assistant framework designed for extensibility and clean architecture.

## Project Status

🚧 **In Development** - Foundation phase

## Architecture

IRIS follows a modular architecture with clear separation of concerns:

```
src/iris/
├── core/       # Core system components and utilities
├── ai/         # AI model integrations and processing
├── voice/      # Voice input/output handling
├── tools/      # Tool definitions and execution
├── memory/     # Context and memory management
├── vision/     # Vision and image processing
├── web/        # Web interface and API
├── ui/         # User interface components
└── security/   # Security and authentication
```

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

4. Copy the environment template:
```bash
cp .env.example .env
```

## Development

### Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=iris --cov-report=html
```

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
