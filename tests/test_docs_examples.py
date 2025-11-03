"""Executable documentation tests - Execute code directly from markdown docs."""

import subprocess
from pathlib import Path
from typing import Any

import pytest


def get_doc_files() -> list[Path]:
    """Get all markdown documentation files."""
    docs_dir = Path(__file__).parent.parent / "docs"
    return sorted(docs_dir.glob("*.md"))


def extract_code_blocks(markdown_content: str) -> list[dict[str, Any]]:
    """Extract code blocks from markdown with language and content.

    Returns list of dicts with 'language', 'content', and 'line_number'.
    """
    blocks = []
    lines = markdown_content.split("\n")
    in_code_block = False
    current_block = []
    block_language = ""
    block_start_line = 0

    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            if not in_code_block:
                # Starting a code block
                in_code_block = True
                block_language = line.strip()[3:].lower()  # Get language after ```
                block_start_line = i + 1
                current_block = []
            else:
                # Ending a code block
                in_code_block = False
                if current_block:
                    blocks.append(
                        {
                            "language": block_language,
                            "content": "\n".join(current_block),
                            "line_number": block_start_line,
                        }
                    )
        elif in_code_block:
            current_block.append(line)

    return blocks


def is_executable_python(code: str) -> bool:
    """Check if Python code block should be executed."""
    # Skip if it's just a signature without body (ends with ) -> type without colon)
    lines = [line for line in code.split("\n") if line.strip()]
    if lines:
        # Check if code ends with a return type annotation without a colon (just a signature)
        last_line = lines[-1].strip()
        if ") ->" in " ".join(lines) and not last_line.endswith(":"):
            return False

    # Skip if it's just a signature without body
    if code.strip().startswith("def ") and "..." in code:
        return False

    # Skip class definitions that are just API documentation
    if code.strip().startswith("class "):
        # Check if there's any actual implementation (not just method signatures)
        has_body = False
        for line in code.split("\n"):
            stripped = line.strip()
            # Look for actual code that's not just signatures, decorators, or comments
            if (
                stripped
                and not stripped.startswith(("class ", "def ", "@", "#", ")"))
                and ":" in stripped
                and not stripped.endswith(":")
            ):
                has_body = True
                break
        if not has_body:
            return False

    # Skip if it has ellipsis (incomplete example)
    if "..." in code:
        return False

    # Skip if it requires user input
    if "input(" in code:
        return False

    # Skip if it has "Good" or "Bad" comment markers (code style examples)
    if code.strip().startswith("# Good") or code.strip().startswith("# Bad"):
        return False

    # Skip SQL queries
    return not code.strip().upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE"))


def is_executable_bash(code: str) -> bool:
    """Check if bash code block should be executed."""
    # Skip if it's just showing output or has placeholders
    if any(x in code for x in ["...", "<", ">", "yourusername", "your.email"]):
        return False

    # Skip if it's showing example output (starts with something that's not a command)
    first_line = code.strip().split("\n")[0]
    return first_line.startswith(("#", "$", "crump", "export", "uv", "pip", "python", "git"))


def prepare_test_environment(tmp_path: Path) -> dict[str, Path]:
    """Create sample files for testing documentation examples."""
    # Create sample CSV files
    users_csv = tmp_path / "users.csv"
    users_csv.write_text(
        "user_id,name,email,notes\n1,Alice,alice@example.com,Admin user\n2,Bob,bob@example.com,Regular user\n3,Charlie,charlie@example.com,Guest user\n"
    )

    sample_csv = tmp_path / "sample.csv"
    sample_csv.write_text("user_id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com\n")

    data_csv = tmp_path / "data.csv"
    data_csv.write_text(
        "user_id,name,email\n1,Test User,test@example.com\n2,Demo User,demo@example.com\n"
    )

    # Create activity_log.csv for docs examples
    activity_log_csv = tmp_path / "activity_log.csv"
    activity_log_csv.write_text(
        "user_id,action,timestamp\n1,login,2024-01-01\n2,logout,2024-01-02\n"
    )

    # Create users_v2.csv for docs examples
    users_v2_csv = tmp_path / "users_v2.csv"
    users_v2_csv.write_text("user_id,name,email,notes\n1,Alice Updated,alice@example.com,Admin\n")

    # Create sample config with only my_job (docs will create other jobs)
    config_yaml = tmp_path / "crump_config.yml"
    config_yaml.write_text("""
jobs:
  my_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
      email: email_address
""")

    return {
        "users.csv": users_csv,
        "sample.csv": sample_csv,
        "data.csv": data_csv,
        "activity_log.csv": activity_log_csv,
        "users_v2.csv": users_v2_csv,
        "crump_config.yml": config_yaml,
        "tmp_path": tmp_path,
    }


class TestExecutableDocsPython:
    """Execute Python code blocks from documentation."""

    @pytest.mark.parametrize("doc_file", get_doc_files(), ids=lambda p: p.name)
    def test_python_code_blocks_execute(self, doc_file: Path, tmp_path: Path) -> None:
        """Execute Python code blocks from documentation to verify they work."""
        content = doc_file.read_text(encoding="utf-8")
        blocks = extract_code_blocks(content)

        # Set up test environment
        test_env = prepare_test_environment(tmp_path)

        # Filter to Python blocks
        python_blocks = [b for b in blocks if b["language"] == "python"]

        executed_count = 0
        for block in python_blocks:
            code = block["content"]

            if not is_executable_python(code):
                continue

            # Try to execute the code
            try:
                # Create namespace with common imports and test files
                namespace: dict[str, Any] = {
                    "Path": Path,
                    "__name__": "__main__",
                }

                # Add test file paths to namespace
                for name, path in test_env.items():
                    if name.endswith(".csv") or name.endswith(".yml"):
                        namespace[name.replace(".", "_")] = path

                exec(code, namespace)
                executed_count += 1

            except ImportError:
                # Skip if it requires imports we don't have in test environment
                continue
            except FileNotFoundError:
                # Skip if it references files we haven't created
                continue
            except Exception as e:
                pytest.fail(
                    f"Python code in {doc_file.name}:{block['line_number']} failed:\n"
                    f"{code}\n\nError: {e}"
                )

        # We should have executed at least some Python code in API reference
        if doc_file.name in ["api-reference.md"]:
            assert executed_count > 0, f"No executable Python found in {doc_file.name}"


class TestExecutableDocsCLI:
    """Execute CLI commands from documentation."""

    @pytest.mark.parametrize("doc_file", get_doc_files(), ids=lambda p: p.name)
    def test_cli_commands_execute(self, doc_file: Path, tmp_path: Path) -> None:
        """Execute CLI commands from documentation to verify they work."""
        content = doc_file.read_text(encoding="utf-8")
        blocks = extract_code_blocks(content)

        # Set up test environment
        test_env = prepare_test_environment(tmp_path)

        # Filter to bash/shell blocks
        bash_blocks = [b for b in blocks if b["language"] in ["bash", "sh", "shell", ""]]

        executed_count = 0
        for block in bash_blocks:
            code = block["content"]

            if not is_executable_bash(code):
                continue

            # Extract crump commands
            lines = code.split("\n")
            for line in lines:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Remove $ or # prefix if present
                if line.startswith("$ "):
                    line = line[2:]
                elif line.startswith("$"):
                    line = line[1:].strip()

                # Only execute crump commands
                if not line.startswith("crump"):
                    continue

                # Skip extract and inspect commands for CDF files (need binary CDF files)
                if ("crump extract" in line or "crump inspect" in line) and ".cdf" in line:
                    continue

                # Replace file references with our test files
                cmd = line
                for name, path in test_env.items():
                    if name in cmd:
                        cmd = cmd.replace(name, str(path))

                # Handle export DATABASE_URL commands (skip them)
                if line.startswith("export DATABASE_URL="):
                    continue

                # Skip commands with postgresql db-url (need real database)
                if "postgresql://" in cmd:
                    continue

                # Skip sync commands without --db-url or DATABASE_URL (need database)
                if "crump sync" in cmd:
                    # Add --db-url if not present and it's dry-run
                    if "--dry-run" in cmd and "--db-url" not in cmd:
                        cmd = cmd.replace("--dry-run", "--db-url sqlite:///test.db --dry-run")
                    elif "--dry-run" not in cmd:
                        # Non dry-run sync needs real database, skip
                        continue

                # Execute the command
                try:
                    result = subprocess.run(
                        cmd.split(), capture_output=True, text=True, timeout=30, cwd=tmp_path
                    )

                    # Some commands are expected to fail (examples showing errors)
                    # Only fail if: returncode != 0 AND not in Troubleshooting AND not help/version
                    if (
                        result.returncode != 0
                        and "Troubleshooting" not in content
                        and "--help" not in cmd
                        and "--version" not in cmd
                    ):
                        pytest.fail(
                            f"CLI command in {doc_file.name}:{block['line_number']} failed:\n"
                            f"{cmd}\n\nStderr: {result.stderr}\nStdout: {result.stdout}"
                        )

                    executed_count += 1

                except subprocess.TimeoutExpired:
                    pytest.fail(f"CLI command timed out: {cmd}")
                except Exception as e:
                    pytest.fail(f"CLI command failed: {cmd}\nError: {e}")

        # CLI reference and quick-start should have executable commands
        if doc_file.name in ["cli-reference.md", "quick-start.md"]:
            assert executed_count > 0, f"No executable CLI commands found in {doc_file.name}"


class TestDocsConsistency:
    """Test documentation consistency without executing code."""

    def test_all_docs_readable_utf8(self) -> None:
        """All documentation files should be readable with UTF-8 encoding."""
        for doc_file in get_doc_files():
            content = doc_file.read_text(encoding="utf-8")
            assert len(content) > 0, f"{doc_file.name} is empty"

    def test_no_deprecated_function_names(self) -> None:
        """Documentation should not reference deprecated function names."""
        deprecated = ["sync_csv_to_postgres"]

        for doc_file in get_doc_files():
            content = doc_file.read_text(encoding="utf-8")

            for old_name in deprecated:
                assert old_name not in content, f"Deprecated '{old_name}' found in {doc_file.name}"

    def test_mkdocs_config_correct(self) -> None:
        """Verify mkdocs.yml has correct configuration."""
        mkdocs = Path(__file__).parent.parent / "mkdocs.yml"
        content = mkdocs.read_text(encoding="utf-8")

        assert "alastairtree.github.io/crump" in content
        assert "github.com/alastairtree/crump" in content
        assert "yourusername" not in content.lower()
