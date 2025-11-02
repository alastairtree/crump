# Installation

## Prerequisites

- Python 3.11 or higher
- PostgreSQL database (for database operations)
- Docker (only for running integration tests during development)

## Install from PyPI (Recommended)

Install the package using pip or uv:

=== "Using pip"

    ```bash
    pip install crump
    ```

=== "Using uv"

    ```bash
    uv pip install crump
    ```

This installs the `crump` CLI tool and makes the package available for programmatic use.

## Install from Source

For development or to get the latest unreleased features:

```bash
# Clone the repository
git clone https://github.com/alastairtree/crump.git
cd crump

# Install with uv (recommended)
uv sync --all-extras

# OR install with pip
pip install -e ".[dev]"
```

## VSCode Dev Container (Recommended for Development)

For the best development experience, open the project in VSCode with the Dev Containers extension:

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
3. Open the project folder in VSCode
4. Click "Reopen in Container" when prompted (or use Command Palette: "Dev Containers: Reopen in Container")

The devcontainer includes:

- Python 3.11 with all dependencies pre-installed via uv
- Docker-in-Docker for running integration tests
- VSCode extensions for Python, Ruff, and Docker
- Proper test and linting configuration

## Verify Installation

After installation, verify that crump is installed correctly:

```bash
# Check version
crump --version

# Show help
crump --help
```

You should see output showing the version number and available commands.

## Database Setup

### PostgreSQL

You'll need a PostgreSQL database to sync data to. You can:

**Option 1: Use an existing PostgreSQL instance**

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/mydb"
```

**Option 2: Run PostgreSQL with Docker**

```bash
docker run -d \
  --name postgres-crump \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mydb \
  -p 5432:5432 \
  postgres:16

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/mydb"
```

**Option 3: Use a cloud provider**

- [AWS RDS](https://aws.amazon.com/rds/postgresql/)
- [Google Cloud SQL](https://cloud.google.com/sql/docs/postgres)
- [Azure Database for PostgreSQL](https://azure.microsoft.com/en-us/products/postgresql)
- [Supabase](https://supabase.com/)
- [Neon](https://neon.tech/)

### SQLite (Alternative)

For testing or lightweight use cases, you can also use SQLite:

```bash
export DATABASE_URL="sqlite:///mydb.db"
```

!!! note
    Some features like advanced indexing work differently in SQLite vs PostgreSQL.

## Next Steps

- [Quick Start Guide](quick-start.md) - Get started with your first sync
- [Configuration](configuration.md) - Learn about YAML configuration
- [CLI Reference](cli-reference.md) - Command-line interface documentation
