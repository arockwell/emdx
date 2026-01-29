# Show available commands
default:
    @just --list

# Install dependencies and sync lock file
install:
    poetry lock
    poetry install
    poetry env list --full-path | head -1 | cut -d' ' -f1 > .venv-path

# Check if dependencies are installed and install if needed
_ensure-installed:
    @if ! poetry run python -c "import textual" 2>/dev/null; then \
        echo "📦 Installing dependencies..."; \
        if ! poetry env info | grep -q "Python 3.13"; then \
            echo "🔄 Updating to Python 3.13..."; \
            poetry env use python3.13; \
            poetry lock; \
        fi; \
        poetry install; \
        echo "✅ Dependencies installed!"; \
    fi

# Run the development version (interactive help)
dev:
    @echo "EMDX Development Commands:"
    @echo "  just run list     - List all documents"
    @echo "  just run recent   - Show recent documents"
    @echo "  just run find 'query' - Search documents"
    @echo "  just run gui      - Run GUI (requires proper terminal)"
    @echo ""
    @echo "Or run: just run --help"

# Run emdx with arguments (fast - bypasses poetry run overhead)
# Uses venv directly for ~4x speedup. Auto-installs on first run if needed.
run *args:
    @if [ ! -f .venv-path ] || [ ! -x "$(cat .venv-path)/bin/emdx" ]; then \
        echo "📦 Setting up emdx..." && \
        poetry install -q && \
        poetry env list --full-path | head -1 | cut -d' ' -f1 > .venv-path; \
    fi && \
    "$(cat .venv-path)/bin/emdx" {{args}}

# Run emdx with dependency check (slower but ensures deps installed)
run-safe *args: _ensure-installed
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

# Show changelog preview (what would go in next release)
changelog:
    python3 scripts/release.py changelog

# Bump version (e.g., just bump 0.8.0)
bump version:
    python3 scripts/release.py bump {{version}}

# Prepare a release (bump version + update changelog)
release version:
    python3 scripts/release.py release {{version}}