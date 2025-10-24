#!/usr/bin/env python3
"""
Clean and standardize book metadata in the database.

Standards:
- Titles: Title Case (except articles, prepositions, conjunctions)
- Authors: Title Case for names
- Years: Plain integers (no commas)
- Remove unnecessary quotes
- Normalize whitespace
- Consistent punctuation
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Title case exceptions (lowercase unless at start)
TITLE_CASE_EXCEPTIONS = {
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into',
    'of', 'on', 'or', 'the', 'to', 'with', 'vs', 'via', 'per'
}


def clean_title(title: Optional[str]) -> Optional[str]:
    """
    Clean and standardize book title.

    Rules:
    - Remove quotes around entire title
    - Title Case with proper exception handling
    - Normalize whitespace
    - Preserve intentional punctuation
    """
    if not title:
        return title

    # Remove quotes around entire title
    title = title.strip()
    if title.startswith('"') and title.endswith('"'):
        title = title[1:-1].strip()

    # Normalize whitespace (multiple spaces to single)
    title = re.sub(r'\s+', ' ', title)

    # Title case with exceptions
    words = title.split()
    result = []

    for i, word in enumerate(words):
        # Always capitalize first and last word
        if i == 0 or i == len(words) - 1:
            result.append(word.capitalize())
        # Check if previous word ends with punctuation (: or !)
        # If so, capitalize this word (subtitle or new clause)
        elif i > 0 and result[i-1][-1] in ':!?':
            result.append(word.capitalize())
        # Check for exception words
        elif word.lower() in TITLE_CASE_EXCEPTIONS:
            result.append(word.lower())
        # Handle hyphenated words
        elif '-' in word:
            parts = word.split('-')
            result.append('-'.join(p.capitalize() for p in parts))
        # Handle words with apostrophes
        elif "'" in word:
            result.append(word.capitalize())
        # Default: capitalize
        else:
            result.append(word.capitalize())

    return ' '.join(result)


def clean_author(author: Optional[str]) -> Optional[str]:
    """
    Clean and standardize author name.

    Rules:
    - Title Case for names
    - Normalize whitespace
    - Preserve semicolons for multiple authors
    - Handle suffixes (Jr., Sr., III, etc.)
    """
    if not author:
        return author

    # Normalize whitespace
    author = re.sub(r'\s+', ' ', author.strip())

    # Split multiple authors by semicolon
    if ';' in author:
        authors = [clean_single_author(a.strip()) for a in author.split(';')]
        return '; '.join(authors)

    return clean_single_author(author)


def clean_single_author(name: str) -> str:
    """Clean a single author name."""
    # Preserve all-caps suffixes (Jr., Sr., II, III, etc.)
    parts = name.split()
    result = []

    for part in parts:
        # Keep suffixes uppercase
        if part.upper() in ('JR.', 'SR.', 'II', 'III', 'IV', 'V', 'JR', 'SR'):
            result.append(part.upper())
        # Keep initials as-is but ensure proper format
        elif re.match(r'^[A-Z]\.?$', part.upper()):
            result.append(part.upper().rstrip('.') + '.')
        # Title case for regular name parts
        else:
            result.append(part.capitalize())

    return ' '.join(result)


def clean_year(year: Optional[str]) -> Optional[str]:
    """
    Clean and standardize publication year.

    Rules:
    - Remove commas (2,025 -> 2025)
    - Ensure it's a valid 4-digit year
    - Remove any non-digit characters
    """
    if not year:
        return year

    # Remove all non-digit characters
    year_str = re.sub(r'[^\d]', '', str(year))

    # Must be 4 digits
    if len(year_str) == 4:
        return year_str

    # If not 4 digits, return original
    return year


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    """Normalize whitespace in any text field."""
    if not text:
        return text

    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)

    # Strip leading/trailing whitespace
    return text.strip()


def clean_book_record(isbn: str, title: str, authors: str, year: str, metadata_json_str: str, conn: sqlite3.Connection) -> dict:
    """
    Clean a single book record.

    Returns dict of cleaned fields.
    """
    cleaned = {
        'isbn': isbn,
        'title': clean_title(title),
        'authors': clean_author(authors),
        'publication_year': clean_year(year),
        'metadata_json': metadata_json_str  # Will be updated below
    }

    # Also clean the metadata_json field if it exists
    if metadata_json_str:
        try:
            metadata = json.loads(metadata_json_str)

            # Clean title in metadata_json
            if 'title' in metadata:
                metadata['title'] = clean_title(metadata['title'])

            # Clean subtitle in metadata_json
            if 'subtitle' in metadata:
                metadata['subtitle'] = clean_title(metadata['subtitle'])

            # Clean authors array in metadata_json
            if 'authors' in metadata and isinstance(metadata['authors'], list):
                metadata['authors'] = [clean_author(a) for a in metadata['authors']]

            # Clean credited_authors in metadata_json
            if 'credited_authors' in metadata and isinstance(metadata['credited_authors'], list):
                metadata['credited_authors'] = [clean_author(a) for a in metadata['credited_authors']]

            # Clean published_year in metadata_json
            if 'published_year' in metadata and metadata['published_year']:
                cleaned_year = clean_year(str(metadata['published_year']))
                metadata['published_year'] = int(cleaned_year) if cleaned_year and cleaned_year.isdigit() else metadata['published_year']

            # Clean series_name in metadata_json
            if 'series_name' in metadata and metadata['series_name']:
                metadata['series_name'] = clean_title(metadata['series_name'])

            cleaned['metadata_json'] = json.dumps(metadata)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  Warning: Could not parse metadata_json for {isbn}: {e}")
            # Keep original if parsing fails
            cleaned['metadata_json'] = metadata_json_str

    return cleaned


def clean_database(db_path: Path, dry_run: bool = False) -> None:
    """
    Clean all book records in the database.

    Args:
        db_path: Path to catalog.db
        dry_run: If True, only show what would be changed
    """
    print(f"{'DRY RUN - ' if dry_run else ''}Cleaning database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all books
    cursor.execute("SELECT isbn, title, authors, publication_year, metadata_json FROM books")
    books = cursor.fetchall()

    total = len(books)
    changed = 0

    changes = []

    for book in books:
        isbn = book['isbn']
        old_title = book['title']
        old_authors = book['authors']
        old_year = book['publication_year']
        old_metadata_json = book['metadata_json']

        # Clean the record
        cleaned = clean_book_record(isbn, old_title, old_authors, old_year, old_metadata_json, conn)

        # Check if anything changed
        title_changed = cleaned['title'] != old_title
        authors_changed = cleaned['authors'] != old_authors
        year_changed = cleaned['publication_year'] != old_year
        metadata_changed = cleaned['metadata_json'] != old_metadata_json

        if title_changed or authors_changed or year_changed or metadata_changed:
            changed += 1

            change_details = []
            if title_changed:
                change_details.append(f"  Title: '{old_title}' -> '{cleaned['title']}'")
            if authors_changed:
                change_details.append(f"  Authors: '{old_authors}' -> '{cleaned['authors']}'")
            if year_changed:
                change_details.append(f"  Year: '{old_year}' -> '{cleaned['publication_year']}'")
            if metadata_changed:
                change_details.append(f"  metadata_json: Updated")

            changes.append((isbn, change_details))

            # Update database
            if not dry_run:
                cursor.execute("""
                    UPDATE books
                    SET title = ?, authors = ?, publication_year = ?, metadata_json = ?
                    WHERE isbn = ?
                """, (cleaned['title'], cleaned['authors'], cleaned['publication_year'], cleaned['metadata_json'], isbn))

    if not dry_run:
        conn.commit()

    conn.close()

    # Print summary
    print("\n" + "="*60)
    print(f"{'DRY RUN - ' if dry_run else ''}Cleaning Complete!")
    print("="*60)
    print(f"Books processed: {total:,}")
    print(f"Books changed:   {changed:,} ({changed/total*100:.1f}%)")

    if changes and (dry_run or changed <= 20):
        print(f"\nChanges {'(preview)' if dry_run else 'made'}:")
        for isbn, details in changes[:20]:
            print(f"\n{isbn}:")
            for detail in details:
                print(detail)
    elif changes:
        print(f"\nShowing first 20 of {changed} changes:")
        for isbn, details in changes[:20]:
            print(f"\n{isbn}:")
            for detail in details:
                print(detail)

    print("\n" + "="*60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clean and standardize book metadata'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=Path.home() / '.isbn_lot_optimizer' / 'catalog.db',
        help='Path to catalog database'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying database'
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database not found: {args.db}")
        sys.exit(1)

    clean_database(args.db, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
