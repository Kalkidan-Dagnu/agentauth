# Contributing to AgentAuth

Thank you for your interest in contributing! AgentAuth is built for African AI developers and welcomes contributions from anywhere in the world.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/agentauth`
3. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
4. Install dev dependencies: `pip install -e ".[dev]"`
5. Copy `.env.example` to `.env` and add your `GEMINI_API_KEY`
6. Run tests: `pytest tests/ -v`

## Development Workflow

- Create a branch: `git checkout -b feature/your-feature-name`
- Make your changes
- Run tests: `pytest tests/ -v`
- Run linter: `ruff check .`
- Commit and push, then open a PR

## What We Welcome

- Bug fixes
- New SDK clients (Java, TypeScript, Go)
- Persistent storage backends (PostgreSQL, Redis)
- Policy templates for African regulatory contexts
- Performance improvements
- Documentation improvements
- Test coverage improvements

## Code Style

- Follow existing patterns
- Type hints on all functions
- Docstrings on all public methods
- Tests for new functionality

## Questions?

Open an issue or reach out at kalajanegassykoki@gmail.com
