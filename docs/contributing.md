# Contributing

Thank you for considering contributing - this document provides guidelines for contributing.

## Code of Conduct

Be respectful and constructive in all interactions. We want this to be a welcoming community for everyone.

## How to Contribute

There are many ways to contribute:

- **Report bugs**: Open an issue with details
- **Suggest features**: Describe your use case
- **Improve documentation**: Fix typos, add examples
- **Write code**: Fix bugs, add features

## Getting Started

### 1. Fork and Clone

```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/alastairtree/crump.git
cd AppName
```

### 2. Set Up Development Environment

```bash
# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install with development dependencies
uv sync --all-extras

./build.sh
```

See the [Development Guide](development.md) for detailed setup instructions.

### 3. Create a Branch

```bash
git checkout -b feature/my-feature
```

Use descriptive branch names:

- `feature/add-mysql-support`
- `fix/handle-empty-files`
- `docs/improve-api-reference`

## Development Workflow

### 1. Write Tests First

Follow Test-Driven Development (TDD):

```python
# tests/test_my_feature.py
def test_my_feature_works():
    """Test that my feature does X."""
    # Arrange
    input_data = ...

    # Act
    result = my_feature(input_data)

    # Assert
    assert result == expected_value
```

Run tests to see it fail:

```bash
uv run pytest tests/test_my_feature.py -v
```

### 2. Implement the Feature

```python
# src/crump/module.py
def my_feature(data):
    """Short description of what this does.

    Args:
        data: Description of parameter

    Returns:
        Description of return value

    Example:
        >>> my_feature("input")
        "output"
    """
    # Implementation
    return result
```

### 3. Run Tests

```bash
# Run all tests with coverage
uv run pytest --cov=src --cov-report=term-missing 
```

### 4. Check Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check --fix .

# Type check
uv run mypy src/crump
```

### 5. Update Documentation

- Add docstrings to all functions
- Update relevant documentation pages
- Add examples if appropriate

### 6. Commit Changes

Use clear, descriptive commit messages:

```bash
git add .
git commit -m "feat: add support for MySQL databases"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Maintenance tasks

### 7. Push and Open PR

```bash
git push origin feature/my-feature
```

Then open a Pull Request on GitHub.

## Pull Request Guidelines

### PR Title

Use a clear, descriptive title:

- ✅ "Add support for MySQL databases"
- ✅ "Fix handling of empty CSV files"
- ❌ "Updates"
- ❌ "Fixed bug"

### PR Description

Include:

1. **What**: What does this PR do?
2. **Why**: Why is this change needed?
3. **How**: How does it work?
4. **Testing**: How was it tested?

Example:

```markdown
## What

Adds support for MySQL databases in addition to PostgreSQL.

## Why

Many users have MySQL databases and want to use crump.

## How

- Added MySQL connection handling
- Adapted SQL queries for MySQL syntax
- Updated tests to cover MySQL

## Testing

- Added integration tests with MySQL testcontainer
- All existing tests still pass
- Tested manually with MySQL 8.0

## Breaking Changes

None
```

### PR Checklist

Before submitting, ensure:

- [ ] Tests added/updated and passing
- [ ] Code formatted with `ruff format`
- [ ] No linting errors (`ruff check`)
- [ ] Type hints added (`mypy` passes)
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] PR description is complete

## Reporting Bugs

### Before Reporting

1. Check existing issues
2. Try the latest version
3. Reproduce with minimal example

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce:
1. Create file with '...'
2. Run command '...'
3. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Environment**
- OS: [e.g., macOS 14, Ubuntu 22.04]
- Python version: [e.g., 3.11.5]
- crump version: [e.g., 0.1.0]
- Database: [e.g., PostgreSQL 16]

**CSV file (if relevant)**
```csv
id,name,value
1,test,123
```

**Config file (if relevant)**
```yaml
jobs:
  my_job:
    ...
```

**Error message**
```
Full error message and traceback
```
```

## Suggesting Features

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
A clear description of the problem. Ex. "I'm always frustrated when [...]"

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Alternative solutions or features you've considered.

**Use case**
Describe your specific use case and how this feature would help.

**Example**
Show an example of how this feature would work:

\`\`\`yaml
# Config example
jobs:
  my_job:
    new_feature:
      option: value
\`\`\`

**Additional context**
Any other context or screenshots.
```

## Code Style

### Python Style

Follow PEP 8 and project conventions:

```python
# Good
def sync_csv_to_db(
    file_path: Path,
    crump_job: CrumpJob,
    db_url: str
) -> int:
    """Sync a CSV file to PostgreSQL.

    Args:
        file_path: Path to the CSV file
        crump_job: Configuration for the sync job
        db_url: Database connection string

    Returns:
        Number of rows synced

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If configuration is invalid
    """
    # Implementation
    return rows_synced
```

### Type Hints

Always include type hints:

```python
# Good
def process_data(data: list[dict[str, str]]) -> dict[str, int]:
    return {"count": len(data)}

# Avoid
def process_data(data):
    return {"count": len(data)}
```

### Docstrings

Use Google-style docstrings:

```python
def analyze_csv(file_path: Path) -> dict[str, tuple[str, bool]]:
    """Analyze CSV file to detect column types.

    Args:
        file_path: Path to the CSV file to analyze

    Returns:
        Dictionary mapping column names to (type, nullable) tuples.
        Example: {"user_id": ("INTEGER", False), "name": ("TEXT", True)}

    Raises:
        FileNotFoundError: If the CSV file doesn't exist
        ValueError: If the CSV file is empty or malformed

    Example:
        >>> analyze_csv(Path("users.csv"))
        {"user_id": ("INTEGER", False), "name": ("TEXT", True)}
    """
    # Implementation
```

## Testing Guidelines

### Unit Tests

Test individual functions:

```python
def test_generate_job_name_removes_numbers():
    """Test that numbers are removed from job names."""
    assert generate_job_name_from_filename("data_2024.csv") == "data"
    assert generate_job_name_from_filename("file123.csv") == "file"
```

### Integration Tests

Test with real database:

```python
@pytest.mark.integration
def test_sync_creates_table(db_url):
    """Test that sync creates table if it doesn't exist."""
    # Sync CSV
    sync_csv_to_db(...)

    # Verify table exists
    with psycopg.connect(db_url) as conn:
        # Check table
```

### Test Organization

```python
class TestMyFeature:
    """Tests for my_feature functionality."""

    def test_basic_case(self):
        """Test basic functionality."""
        pass

    def test_edge_case(self):
        """Test edge case handling."""
        pass

    def test_error_handling(self):
        """Test that errors are raised correctly."""
        with pytest.raises(ValueError):
            my_feature(invalid_input)
```

## Documentation Guidelines

### Structure

- **Overview**: What is it?
- **Usage**: How to use it?
- **Examples**: Show concrete examples
- **Reference**: Detailed parameters

### Examples

Always include examples:

```markdown
## sync_csv_to_db

Sync a CSV file to PostgreSQL.

**Example:**

\`\`\`python
from pathlib import Path
from crump import sync_csv_to_db, CrumpConfig

config = CrumpConfig.from_yaml(Path("crump_config.yml"))
job = config.get_job("my_job")

rows = sync_csv_to_db(
    file_path=Path("data.csv"),
    crump_job=job,
    db_url="postgresql://localhost/mydb"
)
\`\`\`
```

## Review Process

### What Reviewers Look For

1. **Correctness**: Does it work?
2. **Tests**: Are there adequate tests?
3. **Code quality**: Is it readable and maintainable?
4. **Documentation**: Is it documented?
5. **Breaking changes**: Are they justified and documented?

### Addressing Feedback

- Respond to all comments
- Ask questions if unclear
- Make requested changes
- Mark conversations as resolved

## Community

### Getting Help

- **Documentation**: Check the [docs](https://alastairtree.github.io/crump)
- **Issues**: Search existing issues
- **Discussions**: Use GitHub Discussions for questions

### Acknowledgments

Contributors are recognized in:

- GitHub contributors page
- Release notes for their contributions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

If you have questions about contributing, please:

1. Check the [Development Guide](development.md)
2. Search existing issues
3. Open a new issue with the "question" label

Thank you for contributing to crump! 🎉
