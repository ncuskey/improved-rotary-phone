"""Entrypoint for ``python -m lothelper`` commands."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from lothelper.cli import booksrun_sell


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lothelper")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    booksrun_parser = subparsers.add_parser(
        "booksrun-sell",
        help="Fetch BooksRun SELL quotes in bulk.",
    )
    booksrun_sell.add_arguments(booksrun_parser)
    booksrun_parser.set_defaults(handler=booksrun_sell.run)

    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
