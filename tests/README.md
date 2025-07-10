# EMDX Test Suite

## Overview

This test suite provides coverage for the EMDX knowledge base system. We've set up tests for the core functionality while working around some architecture constraints.

## Running Tests

```bash
# Run all working tests
poetry run pytest tests/test_config.py tests/test_utils.py tests/test_simple.py tests/test_database_simple.py -v

# Run with coverage
poetry run pytest tests/test_config.py tests/test_utils.py tests/test_simple.py tests/test_database_simple.py --cov=emdx

# Run a specific test file
poetry run pytest tests/test_database_simple.py -v
```

## Test Organization

### Working Tests (16 tests)
- `test_config.py` - Tests for configuration utilities (2 tests)
- `test_utils.py` - Tests for utility functions like git project detection (6 tests)
- `test_simple.py` - Basic database connection tests (3 tests)
- `test_database_simple.py` - Core database operations using simplified test database (5 tests)

### Tests Needing Fixes
- `test_database.py` - Original database tests (needs fixture fixes)
- `test_tags.py` - Tag management tests (needs fixture fixes)

## Architecture Notes

The main challenge with testing this codebase is that the `SQLiteDatabase` class expects file paths (as `Path` objects) but SQLite's in-memory database needs the special string `:memory:`. When we pass `Path(":memory:")`, it creates an actual file path instead of using an in-memory database.

To work around this, we created `TestDatabase` in `test_fixtures_simple.py` which:
- Handles in-memory databases correctly
- Provides the same interface as the real database
- Keeps the in-memory connection open for the test duration

## Next Steps

To expand test coverage:

1. **Fix the original fixtures** - Modify `SQLiteDatabase` to handle `:memory:` as a special case
2. **Add CLI tests** - Use Typer's test runner to test CLI commands
3. **Add integration tests** - Test full workflows like saving and searching documents
4. **Mock external dependencies** - GitHub API, FZF, subprocess calls

## Test Philosophy

We're following a pragmatic approach:
- Start with the easiest, most isolated functions
- Use simple test databases rather than complex mocking
- Focus on core functionality first
- Add tests incrementally as the codebase evolves