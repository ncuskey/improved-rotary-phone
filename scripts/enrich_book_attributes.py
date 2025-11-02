"""
Enrich book attributes by parsing titles and metadata.

Extracts:
- Cover type (Hardcover, Paperback, Mass Market)
- First edition status
- Signed status

Zero API calls - purely text parsing.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Tuple


class BookAttributeParser:
    """Parse book attributes from titles and metadata."""

    # Cover type patterns
    HARDCOVER_PATTERNS = [
        r'\bhardcover\b',
        r'\bhardback\b',
        r'\bhc\b',
        r'\bbound\b',
        r'\bcloth\b',
    ]

    PAPERBACK_PATTERNS = [
        r'\bpaperback\b',
        r'\bsoftcover\b',
        r'\bsoft cover\b',
        r'\bpb\b',
    ]

    MASS_MARKET_PATTERNS = [
        r'\bmass market\b',
        r'\bmmpb\b',
        r'\bmm paperback\b',
    ]

    # First edition patterns
    FIRST_EDITION_PATTERNS = [
        r'\b1st edition\b',
        r'\bfirst edition\b',
        r'\b1st ed\.',
        r'\bfirst printing\b',
        r'\b1st printing\b',
        r'\bfirst issue\b',
    ]

    # Signed patterns
    SIGNED_PATTERNS = [
        r'\bsigned\b',
        r'\bautographed\b',
        r'\bautograph\b',
        r'\binscribed\b',
    ]

    def __init__(self):
        self.stats = {
            'cover_type': 0,
            'first_edition': 0,
            'signed': 0,
        }

    def parse_cover_type(self, title: str, metadata_json: Optional[str]) -> Optional[str]:
        """
        Parse cover type from title or metadata.

        Returns: "Hardcover", "Paperback", "Mass Market", or None
        """
        text = title.lower()

        # Add metadata if available
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
                # Check if metadata has binding info
                if 'binding' in metadata:
                    binding = metadata['binding'].lower()
                    if 'hardcover' in binding or 'hardback' in binding:
                        return "Hardcover"
                    elif 'mass' in binding:
                        return "Mass Market"
                    elif 'paperback' in binding:
                        return "Paperback"
            except (json.JSONDecodeError, KeyError):
                pass

        # Check mass market first (most specific)
        for pattern in self.MASS_MARKET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "Mass Market"

        # Check hardcover
        for pattern in self.HARDCOVER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "Hardcover"

        # Check paperback
        for pattern in self.PAPERBACK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "Paperback"

        return None

    def parse_first_edition(self, title: str) -> Optional[str]:
        """
        Parse first edition info from title.

        Returns: "1st" if first edition, None otherwise
        """
        text = title.lower()

        for pattern in self.FIRST_EDITION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "1st"

        return None

    def parse_signed(self, title: str) -> bool:
        """
        Parse signed status from title.

        Returns: True if signed, False otherwise
        """
        text = title.lower()

        for pattern in self.SIGNED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def parse_book(self, title: str, metadata_json: Optional[str]) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Parse all attributes from a book.

        Returns: (cover_type, first_edition, signed)
        """
        cover_type = self.parse_cover_type(title, metadata_json)
        first_edition = self.parse_first_edition(title)
        signed = self.parse_signed(title)

        if cover_type:
            self.stats['cover_type'] += 1
        if first_edition:
            self.stats['first_edition'] += 1
        if signed:
            self.stats['signed'] += 1

        return cover_type, first_edition, signed


def enrich_catalog(db_path: Path, dry_run: bool = False):
    """
    Enrich catalog.db with parsed book attributes.

    Args:
        db_path: Path to catalog.db
        dry_run: If True, don't write changes
    """
    parser = BookAttributeParser()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 70)
    print("BOOK ATTRIBUTE ENRICHMENT")
    print("=" * 70)
    print()

    # Get books that need enrichment
    query = """
        SELECT isbn, title, metadata_json, cover_type, printing, signed
        FROM books
        WHERE cover_type IS NULL OR printing IS NULL OR signed IS NULL OR signed = 0
    """

    cursor.execute(query)
    books = cursor.fetchall()

    print(f"Found {len(books)} books needing enrichment")
    print()

    updates = []

    for isbn, title, metadata_json, existing_cover, existing_printing, existing_signed in books:
        # Parse attributes
        cover_type, first_edition, signed = parser.parse_book(title, metadata_json)

        # Use existing values if parser didn't find anything
        final_cover = cover_type or existing_cover
        final_printing = first_edition or existing_printing
        final_signed = signed or existing_signed

        # Only update if we found new info
        if cover_type or first_edition or signed:
            updates.append((final_cover, final_printing, final_signed, isbn))

    print("Parsing Results:")
    print("-" * 70)
    print(f"  Cover types found: {parser.stats['cover_type']}")
    print(f"  First editions found: {parser.stats['first_edition']}")
    print(f"  Signed books found: {parser.stats['signed']}")
    print()

    if dry_run:
        print("DRY RUN - No changes made")
        print()
        print("Sample enrichments:")
        for i, (cover, printing, signed, isbn) in enumerate(updates[:10]):
            cursor.execute("SELECT title FROM books WHERE isbn = ?", (isbn,))
            title = cursor.fetchone()[0]
            print(f"  {isbn}")
            print(f"    Title: {title[:60]}...")
            print(f"    Cover: {cover}, First Ed: {printing}, Signed: {signed}")
            print()
    else:
        # Apply updates
        print(f"Applying {len(updates)} updates...")

        cursor.executemany("""
            UPDATE books
            SET cover_type = ?, printing = ?, signed = ?
            WHERE isbn = ?
        """, updates)

        conn.commit()
        print(f"✓ Updated {len(updates)} books")

    # Show before/after stats
    print()
    print("Database Stats:")
    print("-" * 70)

    cursor.execute("SELECT COUNT(*) FROM books WHERE cover_type IS NOT NULL")
    with_cover = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM books")
    total = cursor.fetchone()[0]
    print(f"  Books with cover type: {with_cover}/{total} ({with_cover/total*100:.1f}%)")

    cursor.execute("SELECT COUNT(*) FROM books WHERE printing IS NOT NULL")
    with_printing = cursor.fetchone()[0]
    print(f"  Books with printing info: {with_printing}/{total} ({with_printing/total*100:.1f}%)")

    cursor.execute("SELECT COUNT(*) FROM books WHERE signed = 1")
    with_signed = cursor.fetchone()[0]
    print(f"  Signed books: {with_signed}/{total} ({with_signed/total*100:.1f}%)")

    conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Enrich book attributes from titles")
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write changes, just show what would be done"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    enrich_catalog(db_path, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
