#!/bin/bash
set -e

# if uv is not installed, install it
if ! command -v uv &> /dev/null
then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Assumes you are in the root of the project with the pyproject.toml file
uv sync --all-extras

# if arg1 is "fast" run tests without postgres
if [ "$1" = "fast" ]; then
    uv run pytest -v tests -k "not postgres"
else
    uv run pytest -v tests
fi

uv run ruff format --check .
# fix with uv run ruff format .

uv run ruff check .
# uv run ruff check --fix .

uv run mypy src

uv build

./generate-docs.sh build