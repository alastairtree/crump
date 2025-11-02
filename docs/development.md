# Development Guide

Guide for contributing to crump development.

## Setup Development Environment

### Prerequisites

- Python 3.11 or higher
- Docker (for integration tests)
- Git

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/alastairtree/crump.git
cd crump

# Install with uv (recommended)
uv sync --all-extras

# OR install with pip
pip install -e ".[dev]"
```

### VSCode Dev Container (Recommended)

For the best development experience:

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
3. Open the project folder in VSCode
4. Click "Reopen in Container" when prompted

The devcontainer includes:

- Python 3.11 with all dependencies pre-installed via uv
- Docker-in-Docker for running integration tests
- VSCode extensions for Python, Ruff, and Docker
- Proper test and linting configuration

## Project Structure

```
crump/
├── .github/
│   └── workflows/
│       └── ci.yml                    # GitHub Actions CI/CD
├── .devcontainer/
│   └── devcontainer.json             # VSCode dev container config
├── docs/                             # MkDocs documentation
│   ├── index.md
│   ├── installation.md
│   └── ...
├── src/
│   └── crump/
│       ├── __init__.py               # Package exports
│       ├── cli.py                    # Main CLI entry point
│       ├── cli_COMMANDNAME.py        # CLI commands 
│       └── database.py               # Database operations
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Pytest configuration
│   ├── helpers.py                    # Test helpers
│   ├── test_FILENAME.py              # test for a file FILENAME   
│   └── test_database_integration.py  # Integration tests (requires Docker)
├── pyproject.toml                    # Project configuration
├── mkdocs.yml                        # Documentation configuration
├── generate-docs.sh                  # Local docs generation script
├── build.sh                          # Build script
└── README.md                         # Concise readme with link to docs
```

## Running Tests

### All Tests

```bash
# With uv (recommended)
uv run pytest -v

# OR with direct pytest if that is on the path/in venv
pytest -v
```

### With Coverage

```bash
uv run pytest --cov=src --cov-report=html

# View coverage report by hosting it with a live server
uv run python -m http.server --directory htmlcov 8000
```

### Specific Test

```bash
# Run specific test file
uv run pytest tests/test_config.py -v

# Run specific test class
uv run pytest tests/test_config.py::TestCrumpConfig -v

# Run specific test
uv run pytest tests/test_config.py::TestCrumpConfig::test_load_from_yaml -v
```

## Code Quality

### Formatting

Format code with Ruff:

```bash
uv run ruff format .
```

### Linting

Check and fix linting issues:

```bash
# Check for issues
uv run ruff check .

# Fix automatically
uv run ruff check --fix .
```

### Type Checking

Run MyPy type checker:

```bash
uv run mypy .
```

### Pre-Commit Checks

Run all checks before committing:

```bash
# Format code
uv run ruff format .

# Fix linting issues
uv run ruff check --fix .

# Type check
uv run mypy .

# Run tests
uv run pytest
```

## Testing Philosophy

This project prioritizes:

### High Coverage

Aim for >90% code coverage:

### Meaningful Tests

Test behavior, not implementation:

```python
# Good: Tests behavior
def test_sync_updates_existing_rows(self):
    # First sync
    sync_csv_to_db(...)
    # Update CSV
    # Second sync
    # Verify rows are updated, not duplicated

# Avoid: Tests implementation details
def test_sync_calls_execute_with_correct_sql(self):
    # Too tied to implementation
```

### Fast Tests

Keep test suite fast for quick feedback:

- Unit tests: < 5 seconds
- Integration tests: < 30 seconds
- Full suite: < 1 minute

### Real Integration Tests

Use testcontainers for authentic database testing:

```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:16") as postgres:
        yield postgres
```

### Readable Tests

Tests serve as documentation:

```python
def test_filename_to_column_extracts_date_from_filename(self):
    """Test that dates are correctly extracted from filenames."""
    # Arrange: Create config with date pattern
    # Act: Extract values
    # Assert: Date matches expected value
```

## Adding New Features

1. Write Tests First (TDD)
2. Implement Feature
3. Update Documentation
4. Run Quality Checks
5. Create Pull Request

## Documentation

### Build Documentation Locally

```bash
# Generate and serve documentation
./generate-docs.sh

# Or manually
uv run mkdocs serve
```

Then open http://127.0.0.1:8000


### Writing Documentation

Use MkDocs Material features:

**Admonitions**:

```markdown
!!! note
    This is a note

!!! warning
    This is a warning

!!! tip
    This is a tip
```

**Code Tabs**:

```markdown
=== "Python"
    ```python
    print("Hello")
    ```

=== "Bash"
    ```bash
    echo "Hello"
    ```
```

**Tables**:

```markdown
| Column | Type | Description |
|--------|------|-------------|
| name   | str  | User name   |
```

## CI/CD Pipeline

GitHub Actions runs on main and pull requests.:

## Release Process

### Version Bumping

Update version in `pyproject.toml`, push code to main and then tag the release
