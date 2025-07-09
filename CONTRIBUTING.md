# Contributing to emdx

Thank you for your interest in contributing to emdx! We welcome contributions from the community.

## Getting Started

1. **Fork the repository**
   ```bash
   # Fork via GitHub UI, then:
   git clone https://github.com/YOUR_USERNAME/emdx.git
   cd emdx
   ```

2. **Set up development environment**
   ```bash
   # Create a virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install in development mode with dev dependencies
   pip install -e ".[dev]"
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Code Style

We use several tools to maintain code quality:

- **Black**: Code formatting (line length: 100)
- **Ruff**: Linting (pycodestyle, pyflakes, isort, and more)
- **MyPy**: Static type checking

Run all checks:
```bash
# Format code
black emdx/

# Lint
ruff check emdx/

# Type checking
mypy emdx/
```

### Making Changes

1. **Write your code**
   - Follow existing code patterns and conventions
   - Add type hints to all functions
   - Keep functions focused and modular
   - Update docstrings for any modified functions

2. **Test your changes**
   - Currently, the project lacks automated tests (contributions welcome!)
   - Manually test all affected commands
   - Test edge cases and error conditions
   - Verify backward compatibility

3. **Update documentation**
   - Update README.md if adding new features
   - Add docstrings to new functions
   - Include examples in commit messages

### Commit Guidelines

We follow conventional commit messages:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code changes that neither fix bugs nor add features
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Examples:
```bash
git commit -m "feat: add support for markdown export"
git commit -m "fix: handle empty search results gracefully"
git commit -m "docs: update installation instructions"
```

## Submitting Changes

1. **Push your branch**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request**
   - Use a clear, descriptive title
   - Reference any related issues with `Fixes #123`
   - Describe what changes you made and why
   - Include examples of how to test the changes

3. **Code Review**
   - Be responsive to feedback
   - Make requested changes promptly
   - Ask questions if anything is unclear

## Development Priorities

Current areas where contributions are especially welcome:

### High Priority
- **Test Suite**: Set up pytest and write comprehensive tests
- **CI/CD**: Configure GitHub Actions for automated testing
- **Bug Fixes**: Check issues for reported bugs

### Features
- **Export Formats**: Add HTML, Markdown bundle exports
- **Search Operators**: Implement AND, OR, NOT operators
- **Tagging System**: Add support for document tags
- **Import Tools**: Import from other note-taking apps
- **Sync Features**: Cloud backup/sync capabilities

### Documentation
- **API Documentation**: Document all public functions
- **User Guide**: Create detailed usage guide
- **Video Tutorials**: Record demo videos

## Project Structure

```
emdx/
├── __init__.py          # Package initialization
├── cli.py               # CLI entry point (Typer app)
├── core.py              # Core commands (save, find, view, etc.)
├── browse.py            # Browse and stats commands
├── gist.py              # GitHub Gist integration
├── gui.py               # Interactive FZF browser
├── database.py          # Database abstraction
├── sqlite_database.py   # SQLite implementation
└── utils.py             # Shared utilities
```

## Questions?

Feel free to:
- Open an issue for discussion
- Ask questions in pull requests
- Reach out to maintainers

Thank you for contributing to emdx!