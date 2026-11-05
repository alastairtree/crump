"""Command-line interface for crump."""

import logging

import click

from crump import __version__
from crump.cli_extract import extract
from crump.cli_inspect import inspect
from crump.cli_prepare import prepare
from crump.cli_sync import sync


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Sync CSV and CDF science files into database.

    This application provides tools for syncing scientific data files
    into a database (PostgreSQL or SQLite) for analysis and storage.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ctx.ensure_object(dict)


# Register commands
main.add_command(sync)
main.add_command(prepare)
main.add_command(inspect)
main.add_command(extract)
