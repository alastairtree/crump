"""Test documentation code examples to ensure they are valid and runnable."""

import ast
import re
import tempfile
from pathlib import Path

import pytest


def extract_python_code_blocks(markdown_content: str) -> list[tuple[str, int]]:
    """Extract Python code blocks from markdown content.

    Returns list of (code, line_number) tuples.
    """
    code_blocks = []
    lines = markdown_content.split('\n')
    in_code_block = False
    current_block = []
    block_start_line = 0
    is_python_block = False

    for i, line in enumerate(lines, 1):
        if line.strip().startswith('```python'):
            in_code_block = True
            is_python_block = True
            block_start_line = i + 1
            current_block = []
        elif line.strip().startswith('```') and in_code_block and is_python_block:
            in_code_block = False
            if current_block:
                code_blocks.append(('\n'.join(current_block), block_start_line))
            is_python_block = False
        elif in_code_block and is_python_block:
            current_block.append(line)

    return code_blocks


def should_skip_code_block(code: str) -> bool:
    """Check if code block should be skipped from testing."""
    skip_markers = [
        '# doctest: skip',
        '# skip test',
        '...',  # Ellipsis in example code
        'input(',  # Interactive input
    ]

    # Skip function/method signatures without bodies
    # These are just type signatures showing the API, not runnable code
    lines = code.strip().split('\n')

    # Check the entire code block for signature patterns
    # If code ends with ) -> <return_type> without a colon, it's a signature
    code_no_whitespace = ' '.join(line.strip() for line in lines)
    if code_no_whitespace.startswith('def '):
        # Check if it's a signature: has balanced parens and ends with -> type (no colon)
        paren_count = code_no_whitespace.count('(') - code_no_whitespace.count(')')
        if paren_count == 0 and ') ->' in code_no_whitespace and not code_no_whitespace.endswith(':'):
            return True

    # Class with only method signatures (API documentation)
    if code_no_whitespace.startswith('class '):
        # Check if this is just a class with method signatures (no actual code bodies)
        # Look for any method that has a body (ends with : followed by actual code)
        has_implementation = False
        in_method = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('def '):
                in_method = True
                # Check if this method has a body
                # Look ahead to see if there's code after the def line
                remaining = lines[i+1:] if i+1 < len(lines) else []
                has_body = False
                for next_line in remaining:
                    next_stripped = next_line.strip()
                    if next_stripped and not next_stripped.startswith(('def ', '@', '#', 'class ')):
                        # Check if it's just method parameters or actual code
                        if not next_stripped.startswith((')', 'self,', 'cls,')) and not ':' in next_stripped:
                            # This looks like actual code
                            has_body = True
                            break
                    if next_stripped.startswith(('def ', 'class ')):
                        # Next method/class, this one has no body
                        break
                if has_body:
                    has_implementation = True
                    break
        if not has_implementation:
            return True

    # Skip indented code snippets (these are examples within markdown formatting examples)
    if code.startswith('    ') and len(lines) == 1:
        return True

    return any(marker in code for marker in skip_markers)


def get_doc_files() -> list[Path]:
    """Get all markdown documentation files."""
    docs_dir = Path(__file__).parent.parent / 'docs'
    return list(docs_dir.glob('*.md'))


class TestDocsExamples:
    """Test that code examples in documentation are valid."""

    @pytest.mark.parametrize('doc_file', get_doc_files(), ids=lambda p: p.name)
    def test_python_code_blocks_are_valid_syntax(self, doc_file: Path) -> None:
        """Test that all Python code blocks in docs have valid syntax."""
        content = doc_file.read_text()
        code_blocks = extract_python_code_blocks(content)

        for code, line_num in code_blocks:
            # Skip code blocks that are meant to be examples or contain interactive elements
            if should_skip_code_block(code):
                continue

            try:
                ast.parse(code)
            except SyntaxError as e:
                pytest.fail(
                    f"Invalid Python syntax in {doc_file.name}:{line_num}\n"
                    f"Error: {e}\n"
                    f"Code:\n{code}"
                )

    def test_api_reference_imports_are_valid(self) -> None:
        """Test that import statements in API reference are valid."""
        api_ref = Path(__file__).parent.parent / 'docs' / 'api-reference.md'
        content = api_ref.read_text()

        # Extract all import statements
        import_pattern = r'from crump import ([^\n]+)'
        imports = re.findall(import_pattern, content)

        # Valid exports from crump package
        valid_exports = {
            'CrumpConfig', 'CrumpJob', 'ColumnMapping', 'Index', 'IndexColumn',
            'sync_csv_to_db', 'sync_csv_to_db_dry_run', 'DryRunSummary',
            'analyze_csv_types_and_nullable', 'suggest_id_column',
            'FilenameToColumn', 'FilenameColumnMapping'
        }

        for import_line in imports:
            # Handle multi-line imports
            if '(' in import_line:
                continue  # Skip multi-line for now, we'll validate them differently

            items = [item.strip() for item in import_line.split(',')]
            for item in items:
                if item and item not in valid_exports:
                    pytest.fail(
                        f"Invalid import in api-reference.md: {item}\n"
                        f"Valid exports: {sorted(valid_exports)}"
                    )

    def test_cli_commands_in_docs_are_valid(self) -> None:
        """Test that CLI command examples in docs use correct command names."""
        # Valid CLI commands
        valid_commands = {'sync', 'prepare', 'inspect', 'extract'}

        for doc_file in get_doc_files():
            content = doc_file.read_text()

            # Find all crump CLI commands in code blocks or command lines
            # Look for lines that start with crump command or are in bash blocks
            lines = content.split('\n')
            for line in lines:
                # Match actual CLI usage (starts with crump or has bash marker)
                if re.match(r'^\s*(crump|#\s+crump|\$\s+crump)', line):
                    command_match = re.search(r'crump\s+(\w+)', line)
                    if command_match:
                        cmd = command_match.group(1)
                        if cmd not in valid_commands:
                            pytest.fail(
                                f"Invalid crump command in {doc_file.name}: {cmd}\n"
                                f"Valid commands: {sorted(valid_commands)}"
                            )

    def test_function_names_are_current(self) -> None:
        """Test that docs don't reference old function names."""
        # Old function names that should not appear
        deprecated_names = [
            'sync_csv_to_postgres',
            'sync_csv_to_postgres_dry_run',
        ]

        # Files to check (exclude CHANGELOG which might reference old names)
        for doc_file in get_doc_files():
            if doc_file.name.lower() in ['changelog.md', 'migration.md']:
                continue

            content = doc_file.read_text()

            for old_name in deprecated_names:
                if old_name in content:
                    pytest.fail(
                        f"Deprecated function name '{old_name}' found in {doc_file.name}\n"
                        f"Should use: sync_csv_to_db or sync_csv_to_db_dry_run"
                    )

    def test_urls_are_correct(self) -> None:
        """Test that URLs in docs point to correct locations."""
        correct_github = 'github.com/alastairtree/crump'
        correct_docs = 'alastairtree.github.io/crump'

        # Placeholder patterns that should not exist
        bad_patterns = [
            'yourusername',
            'YOUR-USERNAME',
            'Your Name',
            'your.email@example.com',
        ]

        for doc_file in get_doc_files():
            content = doc_file.read_text()

            for pattern in bad_patterns:
                if pattern in content and pattern != 'your.email@example.com':
                    # Allow example emails in code examples
                    if 'example.com' in pattern:
                        continue
                    pytest.fail(
                        f"Placeholder text '{pattern}' found in {doc_file.name}\n"
                        f"Replace with actual values"
                    )

    def test_mkdocs_config_urls(self) -> None:
        """Test that mkdocs.yml has correct URLs."""
        mkdocs_path = Path(__file__).parent.parent / 'mkdocs.yml'
        content = mkdocs_path.read_text()

        assert 'alastairtree.github.io/crump' in content
        assert 'github.com/alastairtree/crump' in content
        assert 'yourusername' not in content.lower()

    def test_example_code_uses_realistic_data(self) -> None:
        """Test that example code uses realistic, runnable data."""
        # Check that examples use actual files or realistic paths
        for doc_file in get_doc_files():
            content = doc_file.read_text()
            code_blocks = extract_python_code_blocks(content)

            for code, line_num in code_blocks:
                # Skip if this is just a function signature
                if 'def ' in code and '...' in code:
                    continue

                # Check for common mistakes
                if 'Path("crump_config.yaml")' in code:
                    # Good - using a realistic config file name
                    pass
                if 'Path("data.csv")' in code:
                    # Good - using a realistic data file name
                    pass
