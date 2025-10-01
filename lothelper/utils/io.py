"""IO helpers for LotHelper CLI tooling."""

from __future__ import annotations

import csv
import warnings
from pathlib import Path
from typing import Dict, Iterable, List

FIELD_ISBN = "isbn"


def read_isbns_csv(path: str) -> List[str]:
    """Load ISBNs from ``path`` handling optional headers."""
    file_path = Path(path)
    isbns: List[str] = []
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        is_header = True
        for row in reader:
            if not row:
                continue
            value = row[0].strip()
            if not value:
                continue
            if is_header and value.lower() == FIELD_ISBN:
                is_header = False
                continue
            if is_header:
                is_header = False
            isbns.append(value)

    return isbns


def write_rows_csv(path: str, rows: List[Dict[str, object]], fieldnames: Iterable[str]) -> None:
    """Persist rows to ``path`` as CSV with the provided column order."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_rows_parquet(path: str, rows: List[Dict[str, object]]) -> None:
    """Persist rows to Parquet using ``pyarrow`` when available.

    Falls back to CSV output when ``pyarrow`` is not installed.
    """

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        warnings.warn(
            "pyarrow is not installed; falling back to CSV output.",
            RuntimeWarning,
            stacklevel=2,
        )
        fieldnames = list(rows[0].keys()) if rows else []
        write_rows_csv(path, rows, fieldnames)
        return

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if rows:
        table = pa.Table.from_pylist(rows)
    else:
        table = pa.table({})

    pq.write_table(table, file_path)
