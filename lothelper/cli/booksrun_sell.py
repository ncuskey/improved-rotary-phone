"""Bulk BooksRun SELL quote fetcher."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Iterable, List, Sequence

import requests

from lothelper.utils.io import read_isbns_csv, write_rows_csv, write_rows_parquet
from lothelper.vendors import booksrun_client

FIELDNAMES: Sequence[str] = (
    "isbn",
    "status",
    "http_status",
    "average",
    "good",
    "new",
    "currency",
    "raw_json",
)
PROGRESS_INTERVAL = 25
DEFAULT_SLEEP_SECONDS = 0.2


def _load_dotenv_if_available() -> None:
    try:  # pragma: no cover - exercised indirectly
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--in",
        dest="input_path",
        default="isbns.csv",
        help="Path to the input CSV containing ISBNs.",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        default="booksrun_sell_quotes.csv",
        help="Destination path for the quote output.",
    )
    parser.add_argument(
        "--sleep",
        dest="sleep_seconds",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Seconds to pause between API calls (default: 0.2).",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("csv", "parquet"),
        default="csv",
        help="Output file format.",
    )
    return parser


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lothelper booksrun-sell",
        description="Fetch BooksRun SELL quotes for a list of ISBNs.",
    )
    add_arguments(parser)
    return parser


def run(namespace: argparse.Namespace) -> int:
    _load_dotenv_if_available()

    try:
        booksrun_client.get_booksrun_key()
    except booksrun_client.BooksRunConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    isbns = read_isbns_csv(namespace.input_path)
    unique_isbns = _dedupe_preserve_order(isbns)

    if not unique_isbns:
        print("No ISBNs found in input.", file=sys.stderr)
        _write_output(namespace, [])
        return 1

    rows = []
    success_count = 0
    total = len(unique_isbns)

    with requests.Session() as session:
        for index, isbn in enumerate(unique_isbns, start=1):
            try:
                quote = booksrun_client.get_sell_quote(isbn, session=session)
            except Exception as exc:  # pragma: no cover - defensive guard
                quote = {
                    "isbn": isbn,
                    "status": "error",
                    "http_status": 0,
                    "average": None,
                    "good": None,
                    "new": None,
                    "currency": booksrun_client.DEFAULT_CURRENCY,
                    "raw_json": str(exc)[:500],
                }

            rows.append(quote)
            if quote.get("status") == "success":
                success_count += 1

            if index % PROGRESS_INTERVAL == 0:
                print(f"Processed {index}/{total} ISBNs", flush=True)

            if index < total and namespace.sleep_seconds > 0:
                time.sleep(namespace.sleep_seconds)

    if total % PROGRESS_INTERVAL:
        print(f"Processed {total}/{total} ISBNs", flush=True)

    _write_output(namespace, rows)

    return 0 if success_count > 0 else 1


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _write_output(namespace: argparse.Namespace, rows: List[dict]) -> None:
    output_format = namespace.output_format
    output_path = namespace.output_path

    if output_format == "csv":
        write_rows_csv(output_path, rows, FIELDNAMES)
    else:
        write_rows_parquet(output_path, rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
