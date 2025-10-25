#!/usr/bin/env python3
"""
Normalize Series Names in Database

Fixes inconsistent series names so books group properly into lots.
Handles common patterns like:
- "Series Name (Book #1)" → "Series Name"
- "Book Title" → "Series Name" (when part of known series)
- Author-specific series normalization
"""

import sqlite3
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

# ANSI colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

DB_PATH = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

# Known series name mappings (add more as needed)
SERIES_MAPPINGS = {
    # Jack Reacher series
    "killing floor": "Jack Reacher",
    "die trying": "Jack Reacher",
    "tripwire": "Jack Reacher",
    "running blind": "Jack Reacher",
    "echo burning": "Jack Reacher",
    "without fail": "Jack Reacher",
    "persuader": "Jack Reacher",
    "the enemy": "Jack Reacher",
    "one shot": "Jack Reacher",
    "the hard way": "Jack Reacher",
    "bad luck and trouble": "Jack Reacher",
    "nothing to lose": "Jack Reacher",
    "gone tomorrow": "Jack Reacher",
    "61 hours": "Jack Reacher",
    "worth dying for": "Jack Reacher",
    "the affair": "Jack Reacher",
    "a wanted man": "Jack Reacher",
    "never go back": "Jack Reacher",
    "personal": "Jack Reacher",
    "make me": "Jack Reacher",
    "night school": "Jack Reacher",
    "no middle name": "Jack Reacher",
    "the midnight line": "Jack Reacher",
    "past tense": "Jack Reacher",
    "blue moon": "Jack Reacher",
    "the sentinel": "Jack Reacher",
    "better off dead": "Jack Reacher",
    "no plan b": "Jack Reacher",
    "in too deep": "Jack Reacher",
    "the secret": "Jack Reacher",

    # Add more series as you discover them
    # "book title": "Series Name",
}


def normalize_series_name(current_name: str, title: str = "", author: str = "") -> str:
    """
    Normalize a series name to a canonical form.

    Handles:
    - "Series Name (Book #1)" → "Series Name"
    - "Series Name (#1)" → "Series Name"
    - Book titles that are actually series names
    """
    if not current_name:
        return current_name

    # First check if it's a known book title that should map to a series
    title_lower = title.lower().strip()
    if title_lower in SERIES_MAPPINGS:
        return SERIES_MAPPINGS[title_lower]

    # Check if the series name itself is in mappings
    name_lower = current_name.lower().strip()
    if name_lower in SERIES_MAPPINGS:
        return SERIES_MAPPINGS[name_lower]

    # Remove trailing (#X) or (Book #X) patterns
    patterns = [
        r'\s*\(#?\d+\)\s*$',           # (1) or (#1)
        r'\s*\(Book #?\d+\)\s*$',      # (Book 1) or (Book #1)
        r'\s*#\d+\s*$',                # #1
        r'\s*Book \d+\s*$',            # Book 1
    ]

    normalized = current_name
    for pattern in patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Clean up any extra whitespace
    normalized = normalized.strip()

    # If we stripped something, return the cleaned name
    if normalized != current_name and normalized:
        return normalized

    return current_name


def analyze_series_issues(conn: sqlite3.Connection) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Analyze the database for series name inconsistencies.

    Returns dict of:
    {
        "author_name": [(isbn, current_series, title), ...]
    }
    """
    cursor = conn.execute("""
        SELECT isbn, title, authors,
               json_extract(metadata_json, '$.series_name') as series_name
        FROM books
        WHERE series_name IS NOT NULL AND series_name != ''
        ORDER BY authors, series_name
    """)

    series_by_author: Dict[str, List[Tuple[str, str, str]]] = {}

    for row in cursor.fetchall():
        isbn, title, authors, series_name = row

        if not authors:
            continue

        # Use first author as key
        author = authors.split(',')[0] if ',' in authors else authors

        if author not in series_by_author:
            series_by_author[author] = []

        series_by_author[author].append((isbn, series_name, title))

    return series_by_author


def fix_series_names(conn: sqlite3.Connection, dry_run: bool = True) -> int:
    """
    Fix series names in the database.

    Returns number of books updated.
    """
    cursor = conn.execute("""
        SELECT isbn, title, authors, metadata_json
        FROM books
        WHERE metadata_json IS NOT NULL
    """)

    updated_count = 0
    updates = []

    for row in cursor.fetchall():
        isbn, title, authors, metadata_json_str = row

        if not metadata_json_str:
            continue

        try:
            metadata = json.loads(metadata_json_str)
        except json.JSONDecodeError:
            print(f"{YELLOW}⚠️  Skipping {isbn} - invalid JSON{RESET}")
            continue

        current_series = metadata.get('series_name')
        if not current_series:
            continue

        # Normalize the series name
        normalized_series = normalize_series_name(
            current_series,
            title=title or "",
            author=authors or ""
        )

        # Check if we need to update
        if normalized_series != current_series:
            updates.append({
                'isbn': isbn,
                'title': title,
                'old_series': current_series,
                'new_series': normalized_series,
                'metadata': metadata
            })

    # Display what we'll change
    if updates:
        print(f"\n{BOLD}{BLUE}Found {len(updates)} books with series names to normalize:{RESET}\n")

        # Group by series change for easier review
        changes_by_series: Dict[str, List[Dict]] = {}
        for update in updates:
            key = f"{update['old_series']} → {update['new_series']}"
            if key not in changes_by_series:
                changes_by_series[key] = []
            changes_by_series[key].append(update)

        for change_desc, books in sorted(changes_by_series.items()):
            print(f"{BOLD}{change_desc}{RESET} ({len(books)} books)")
            for book in books[:3]:  # Show first 3 examples
                print(f"  • {book['title']} ({book['isbn']})")
            if len(books) > 3:
                print(f"  ... and {len(books) - 3} more")
            print()

    if not updates:
        print(f"{GREEN}✓ No series names need normalization!{RESET}")
        return 0

    if dry_run:
        print(f"{YELLOW}DRY RUN - No changes made. Run with --apply to update.{RESET}")
        return 0

    # Apply updates
    print(f"\n{BOLD}Applying updates...{RESET}")
    for update in updates:
        # Update metadata JSON
        update['metadata']['series_name'] = update['new_series']
        new_metadata_json = json.dumps(update['metadata'])

        conn.execute(
            "UPDATE books SET metadata_json = ? WHERE isbn = ?",
            (new_metadata_json, update['isbn'])
        )
        updated_count += 1

        if updated_count % 10 == 0:
            print(f"  Updated {updated_count}/{len(updates)}...")

    conn.commit()
    print(f"{GREEN}✓ Updated {updated_count} books{RESET}")

    return updated_count


def main():
    """Main entry point"""
    import sys

    dry_run = "--apply" not in sys.argv

    print(f"{BOLD}{BLUE}Series Name Normalization Tool{RESET}")
    print(f"Database: {DB_PATH}\n")

    if not DB_PATH.exists():
        print(f"{YELLOW}⚠️  Database not found at {DB_PATH}{RESET}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # First, analyze current state
        print(f"{BOLD}Analyzing current series names...{RESET}\n")
        series_by_author = analyze_series_issues(conn)

        # Show some stats
        total_series = sum(len(books) for books in series_by_author.values())
        print(f"Found {total_series} books with series metadata across {len(series_by_author)} authors\n")

        # Fix series names
        updated = fix_series_names(conn, dry_run=dry_run)

        if updated > 0 and not dry_run:
            print(f"\n{BOLD}Regenerating lots...{RESET}")
            print(f"{YELLOW}Run: curl -X POST http://localhost:8000/api/lots/regenerate.json{RESET}")
            print(f"{YELLOW}Or restart your backend to see changes.{RESET}")

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    sys.exit(main())
