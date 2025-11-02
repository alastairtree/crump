"""Test documentation code examples by executing them."""

import subprocess
from pathlib import Path

import pytest


def get_doc_files() -> list[Path]:
    """Get all markdown documentation files."""
    docs_dir = Path(__file__).parent.parent / 'docs'
    return list(docs_dir.glob('*.md'))


class TestDocsCLIExamples:
    """Test CLI examples from documentation by actually executing them."""

    def test_prepare_command_works(self, tmp_path: Path) -> None:
        """Test that the prepare command works as documented."""
        # Create sample CSV file
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text("user_id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com\n")

        config_file = tmp_path / "config.yaml"

        # Run prepare command as documented (config file doesn't need to exist)
        result = subprocess.run(
            ["uv", "run", "crump", "prepare", str(csv_file), "--config", str(config_file)],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"prepare failed: {result.stderr}"
        assert config_file.exists(), "Config file should be created"

    def test_inspect_command_works(self, tmp_path: Path) -> None:
        """Test that the inspect command works as documented."""
        # Create sample CSV file
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text("user_id,name,email\n1,Alice,alice@example.com\n")

        # Run inspect command
        result = subprocess.run(
            ["uv", "run", "crump", "inspect", str(csv_file)],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"inspect failed: {result.stderr}"
        assert "user_id" in result.stdout or "user_id" in result.stderr

    def test_version_command_works(self) -> None:
        """Test that --version command works and returns correct version."""
        result = subprocess.run(
            ["uv", "run", "crump", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0
        assert "0.1.0" in result.stdout or "0.1.0" in result.stderr

    def test_help_command_works(self) -> None:
        """Test that --help command works."""
        result = subprocess.run(
            ["uv", "run", "crump", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "sync" in output.lower()
        assert "prepare" in output.lower()


class TestDocsCodeExamples:
    """Test that importable code examples from docs actually work."""

    def test_crump_imports_work(self) -> None:
        """Test that documented imports actually work."""
        # This tests the imports shown in docs/api-reference.md
        # We import them to verify they exist, even though we don't use them here
        # ruff: noqa: F401
        try:
            from crump import (  # noqa: F401
                ColumnMapping,
                CrumpConfig,
                CrumpJob,
                DryRunSummary,
                Index,
                IndexColumn,
                analyze_csv_types_and_nullable,
                suggest_id_column,
                sync_csv_to_db,
                sync_csv_to_db_dry_run,
            )
            # If we got here, imports work
            assert True
        except ImportError as e:
            pytest.fail(f"Documented imports don't work: {e}")

    def test_analyze_csv_works_as_documented(self, tmp_path: Path) -> None:
        """Test analyze_csv_types_and_nullable works as shown in docs."""
        from crump import analyze_csv_types_and_nullable

        # Create sample CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("user_id,name,age\n1,Alice,30\n2,Bob,25\n")

        # Run as documented
        column_info = analyze_csv_types_and_nullable(csv_file)

        # Verify it returns expected structure
        assert isinstance(column_info, dict)
        assert "user_id" in column_info
        assert "name" in column_info
        # Each value should be (type, nullable) tuple
        data_type, nullable = column_info["user_id"]
        assert isinstance(data_type, str)
        assert isinstance(nullable, bool)

    def test_suggest_id_column_works_as_documented(self) -> None:
        """Test suggest_id_column works as shown in docs."""
        from crump import suggest_id_column

        # Test with columns that have an ID
        columns = ["user_id", "name", "email"]
        id_col = suggest_id_column(columns)
        assert id_col == "user_id"

        # Test with no obvious ID
        columns = ["name", "email"]
        id_col = suggest_id_column(columns)
        assert id_col == "name"  # Should default to first column

    def test_config_loading_works_as_documented(self, tmp_path: Path) -> None:
        """Test CrumpConfig.from_yaml works as shown in docs."""
        from crump import CrumpConfig

        # Create minimal config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
""")

        # Load as documented
        config = CrumpConfig.from_yaml(config_file)

        # Verify it loaded
        assert config is not None
        job = config.get_job("test_job")
        assert job is not None
        assert job.target_table == "users"


class TestDocsConsistency:
    """Test that docs are internally consistent and don't have obvious errors."""

    def test_mkdocs_config_has_correct_urls(self) -> None:
        """Test that mkdocs.yml has correct URLs."""
        mkdocs_path = Path(__file__).parent.parent / 'mkdocs.yml'
        content = mkdocs_path.read_text(encoding='utf-8')

        assert 'alastairtree.github.io/crump' in content
        assert 'github.com/alastairtree/crump' in content
        assert 'yourusername' not in content.lower()

    def test_docs_dont_reference_old_function_names(self) -> None:
        """Test that docs don't reference deprecated function names."""
        deprecated_names = [
            'sync_csv_to_postgres',
        ]

        for doc_file in get_doc_files():
            # Skip changelog/migration docs which might reference old names
            if doc_file.name.lower() in ['changelog.md', 'migration.md']:
                continue

            content = doc_file.read_text(encoding='utf-8')

            for old_name in deprecated_names:
                assert old_name not in content, (
                    f"Deprecated function name '{old_name}' found in {doc_file.name}"
                )

    def test_docs_files_use_utf8_encoding(self) -> None:
        """Test that all docs files can be read with UTF-8 encoding."""
        for doc_file in get_doc_files():
            try:
                content = doc_file.read_text(encoding='utf-8')
                assert len(content) > 0
            except UnicodeDecodeError as e:
                pytest.fail(f"Failed to read {doc_file.name} with UTF-8: {e}")
