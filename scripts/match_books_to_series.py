#!/usr/bin/env python3
"""
Match existing scanned books to series from the imported data.
"""

import json
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.series_matcher import SeriesMatcher, normalize_author_name


def match_existing_books(db_path: Path, limit: int = None, verbose: bool = False) -> None:
    """
    Match all books in the database to series.

    Args:
        db_path: Path to books.db
        limit: Optional limit for testing
        verbose: Print detailed matching info
    """
    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch all books
    query = "SELECT isbn, title, authors, metadata_json FROM books"
    if limit:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query)
    books = cursor.fetchall()
    total = len(books)

    print(f"Found {total:,} books to match")

    # Initialize matcher
    matcher = SeriesMatcher(db_path)

    matched_count = 0
    high_confidence_count = 0

    print("Matching books to series...")

    for i, book_row in enumerate(books, 1):
        isbn = book_row['isbn']
        title = book_row['title']
        authors_str = book_row['authors']

        # Parse authors
        authors = []
        if authors_str:
            import re
            authors = [a.strip() for a in re.split(r'[;,]', authors_str) if a.strip()]

        # Also check metadata_json for additional author info
        try:
            metadata_json = book_row['metadata_json']
            if metadata_json:
                metadata = json.loads(metadata_json)
                meta_authors = metadata.get('authors', [])
                if meta_authors and isinstance(meta_authors, list):
                    for author in meta_authors:
                        normalized = normalize_author_name(author)
                        if normalized and normalized not in authors:
                            authors.append(normalized)
        except Exception:
            pass

        if not title or not authors:
            continue

        # Match the book
        matches = matcher.match_book(
            isbn=isbn,
            book_title=title,
            book_authors=authors,
            auto_save=True  # Automatically save high-confidence matches
        )

        if matches:
            matched_count += 1
            best_match = matches[0]

            if best_match['confidence'] >= 0.9:
                high_confidence_count += 1

            if verbose or (i <= 10 and matches):  # Show first 10 matches
                print(f"\n[{i}/{total}] {title[:50]}")
                print(f"  Authors: {', '.join(authors[:2])}")
                print(f"  Matched: {best_match['series_title']}")
                print(f"  Confidence: {best_match['confidence']:.2%}")

        # Progress indicator
        if i % 100 == 0:
            print(f"  [{i}/{total}] Matched: {matched_count} ({high_confidence_count} high confidence)")

    # Final stats
    stats = matcher.get_series_stats()

    print("\n" + "="*60)
    print("Matching Complete!")
    print("="*60)
    print(f"Books processed:         {total:,}")
    if total > 0:
        print(f"Books matched:           {matched_count:,} ({matched_count/total*100:.1f}%)")
    else:
        print(f"Books matched:           {matched_count:,}")
    print(f"High confidence matches: {high_confidence_count:,}")
    print(f"")
    print(f"Database stats:")
    print(f"  Authors:  {stats['author_count']:,}")
    print(f"  Series:   {stats['series_count']:,}")
    print(f"  Matches:  {stats['matches_count']:,}")
    print("="*60)

    conn.close()
    matcher.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Match scanned books to series'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=Path('books.db'),
        help='Path to books database (default: books.db)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of books to process (for testing)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed matching information'
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database not found: {args.db}")
        sys.exit(1)

    match_existing_books(args.db, limit=args.limit, verbose=args.verbose)


if __name__ == '__main__':
    main()
