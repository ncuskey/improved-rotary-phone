from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def detect_isbn_field(fieldnames: Sequence[str]) -> str:
    for name in fieldnames:
        if not name:
            continue
        if name.strip().lower() == "isbn":
            return name
    return fieldnames[0]


def read_isbn_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str], str]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file must have a header row.")
        header = reader.fieldnames
        isbn_field = detect_isbn_field(header)
        rows = [row for row in reader]
    return rows, header, isbn_field


def normalise_isbn(value: str) -> Optional[str]:
    if not value:
        return None
    cleaned = "".join(
        ch.upper() if ch.upper() == "X" else ch
        for ch in value
        if ch.isdigit() or ch.upper() == "X"
    )
    if not cleaned:
        return None
    return coerce_isbn13(cleaned)


def coerce_isbn13(cleaned: str) -> Optional[str]:
    cleaned = cleaned.upper()

    if len(cleaned) == 13 and cleaned.isdigit():
        if validate_isbn13(cleaned):
            return cleaned
        return cleaned[:12] + compute_isbn13_check_digit(cleaned[:12])

    if len(cleaned) == 12 and cleaned.isdigit():
        return cleaned + compute_isbn13_check_digit(cleaned)

    if len(cleaned) == 9 and cleaned[:-1].isdigit() and cleaned[-1] in "0123456789X":
        prefix = "0" + cleaned[:-1]
        try:
            check = compute_isbn10_check_digit(prefix)
        except ValueError:
            check = None
        if check and check == cleaned[-1]:
            isbn10 = prefix + check
            try:
                return isbn10_to_isbn13(isbn10)
            except ValueError:
                return None

    if len(cleaned) == 10:
        core = cleaned[:9]
        if not core.isdigit():
            return None
        check = compute_isbn10_check_digit(core)
        isbn10 = core + check
        try:
            return isbn10_to_isbn13(isbn10)
        except ValueError:
            return None

    if len(cleaned) == 9 and cleaned.isdigit():
        check = compute_isbn10_check_digit(cleaned)
        isbn10 = cleaned + check
        try:
            return isbn10_to_isbn13(isbn10)
        except ValueError:
            return None

    return None


def isbn10_to_isbn13(isbn10: str) -> str:
    core = isbn10[:9]
    if len(isbn10) != 10 or not core.isdigit():
        raise ValueError(f"Cannot convert malformed ISBN-10: {isbn10}")
    prefix = "978" + core
    check = compute_isbn13_check_digit(prefix)
    return prefix + check


def compute_isbn13_check_digit(prefix: str) -> str:
    if len(prefix) != 12 or not prefix.isdigit():
        raise ValueError(f"ISBN-13 prefix must be 12 digits, received '{prefix}'")
    total = 0
    for idx, digit in enumerate(prefix):
        factor = 3 if idx % 2 else 1
        total += factor * int(digit)
    return str((10 - (total % 10)) % 10)


def compute_isbn10_check_digit(prefix: str) -> str:
    if len(prefix) != 9 or not prefix.isdigit():
        raise ValueError(f"ISBN-10 prefix must be 9 digits, received '{prefix}'")
    total = 0
    for idx, digit in enumerate(prefix):
        weight = 10 - idx
        total += weight * int(digit)
    remainder = total % 11
    check = (11 - remainder) % 11
    return "X" if check == 10 else str(check)


def validate_isbn13(isbn: str) -> bool:
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    return isbn[-1] == compute_isbn13_check_digit(isbn[:12])


def validate_isbn10(isbn: str) -> bool:
    if len(isbn) != 10 or not isbn[:9].isdigit():
        return False
    return isbn[-1].upper() == compute_isbn10_check_digit(isbn[:9])
