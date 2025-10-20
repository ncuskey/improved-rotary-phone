#!/usr/bin/env python3
"""
Import book series data from bookseries.org scrape into the ISBN database.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.series_database import SeriesDatabaseManager


def import_series_data(json_file: Path, db_path: Path) -> None:
    """
    Import scraped series data into the database.

    Args:
        json_file: Path to bookseries_complete.json
        db_path: Path to books.db
    """
    print(f"Loading data from {json_file}...")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    series_db = SeriesDatabaseManager(db_path)

    total_authors = len(data['authors'])
    total_series = 0
    total_books = 0
    skipped_authors = 0

    print(f"Importing {total_authors:,} authors...")

    for i, author_data in enumerate(data['authors'], 1):
        author_name = author_data['name']
        author_bio = author_data.get('bio', '')
        author_url = author_data.get('url', '')
        series_list = author_data.get('series', [])

        # Skip authors with no real data
        if not series_list or author_name == 'Author':
            skipped_authors += 1
            continue

        # Progress indicator
        if i % 100 == 0:
            print(f"  [{i}/{total_authors}] Processed {total_series:,} series, {total_books:,} books...")

        # Insert author
        try:
            author_id = series_db.upsert_author(
                name=author_name,
                bio=author_bio,
                source_url=author_url
            )

            if not author_id:
                print(f"Warning: Failed to insert author: {author_name}")
                continue

            # Insert each series for this author
            for series_data in series_list:
                series_title = series_data['title']
                book_count = series_data.get('book_count', 0)
                books = series_data.get('books', [])

                # Skip obviously wrong data (navigation elements, etc)
                skip_phrases = [
                    'recent authors', 'recent interviews', 'thoughts on',
                    'leave a reply', 'cancel reply'
                ]
                if any(phrase in series_title.lower() for phrase in skip_phrases):
                    continue

                # Insert series
                series_id = series_db.upsert_series(
                    author_id=author_id,
                    title=series_title,
                    book_count=book_count,
                    source_url=author_url
                )

                if not series_id:
                    print(f"Warning: Failed to insert series: {series_title} by {author_name}")
                    continue

                total_series += 1

                # Insert books in the series
                for position, book_data in enumerate(books, 1):
                    book_title = book_data.get('title', '')

                    if not book_title or len(book_title) < 3:
                        continue

                    # Skip navigation/UI elements
                    if any(phrase in book_title.lower() for phrase in skip_phrases):
                        continue

                    series_db.add_series_book(
                        series_id=series_id,
                        book_title=book_title,
                        series_position=position,
                        source_link=book_data.get('link', '')
                    )

                    total_books += 1

        except Exception as e:
            print(f"Error processing author {author_name}: {e}")
            continue

    # Final stats
    stats = series_db.get_stats()

    print("\n" + "="*60)
    print("Import Complete!")
    print("="*60)
    print(f"Authors imported:  {stats['author_count']:,}")
    print(f"Series imported:   {stats['series_count']:,}")
    print(f"Books imported:    {stats['series_books_count']:,}")
    print(f"Skipped authors:   {skipped_authors:,}")
    print("="*60)

    series_db.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Import book series data into ISBN database'
    )
    parser.add_argument(
        '--json-file',
        type=Path,
        default=Path('bookseries_complete.json'),
        help='Path to bookseries JSON file (default: bookseries_complete.json)'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=Path('books.db'),
        help='Path to books database (default: books.db)'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear existing series data before importing'
    )

    args = parser.parse_args()

    if not args.json_file.exists():
        print(f"Error: JSON file not found: {args.json_file}")
        sys.exit(1)

    if not args.db.exists():
        print(f"Warning: Database file not found: {args.db}")
        print("A new database will be created.")

    if args.clear:
        print("Clearing existing series data...")
        series_db = SeriesDatabaseManager(args.db)
        series_db.clear_all()
        series_db.close()
        print("Cleared.")

    import_series_data(args.json_file, args.db)


if __name__ == '__main__':
    main()
