# Show available commands
default:
    @just --list

# Install dependencies
install:
    poetry install

# Run the development version (interactive help)
dev:
    @echo "EMDX Development Commands:"
    @echo "  just run list     - List all documents"
    @echo "  just run recent   - Show recent documents"
    @echo "  just run find 'query' - Search documents"
    @echo "  just run gui      - Run GUI (requires proper terminal)"
    @echo ""
    @echo "Or run: just run --help"

# Run emdx with arguments
run *args:
    poetry run emdx {{args}}

# Run tests
test:
    poetry run pytest

# Run tests with coverage
test-cov:
    poetry run pytest --cov=emdx --cov-report=html --cov-report=term

# Run linter
lint:
    poetry run ruff check .

# Format code
format:
    poetry run black .

# Run type checking
typecheck:
    poetry run mypy emdx

# Run all checks (lint, typecheck, test)
check: lint typecheck test
    @echo "All checks passed!"

# Fix all auto-fixable issues
fix:
    poetry run black .
    poetry run ruff check --fix .

# Clean up cache and build files
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .pytest_cache
    rm -rf .mypy_cache
    rm -rf .ruff_cache
    rm -rf htmlcov