#!/usr/bin/env python3
"""
Test script to add sample series books and generate series lots.
This is useful for testing the series lot feature without scanning real books.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.series_lots import build_series_lots_enhanced


def add_test_books(service: BookService) -> None:
    """Add some test books from popular series."""

    test_books = [
        # Harry Potter Series - ISBNs for books 1, 2, 4, 5
        ("9780439708180", "Good", None),  # Sorcerer's Stone
        ("9780439064873", "Good", None),  # Chamber of Secrets
        ("9780439139601", "Good", None),  # Goblet of Fire
        ("9780439358071", "Good", None),  # Order of Phoenix

        # Hunger Games Series - ISBNs for books 1, 2
        ("9780439023481", "Good", None),  # The Hunger Games
        ("9780439023498", "Good", None),  # Catching Fire

        # Divergent Series - ISBN for book 1 only
        ("9780062024039", "Good", None),  # Divergent
    ]

    print("Adding test books to database...")
    for isbn, condition, edition in test_books:
        try:
            print(f"  Scanning {isbn}...")
            service.scan_isbn(
                raw_isbn=isbn,
                condition=condition,
                edition=edition,
                include_market=False,  # Skip market lookup for speed
                recalc_lots=False  # Don't recalc lots yet
            )
            print(f"    ✓ Added")
        except Exception as e:
            print(f"    ✗ Error: {e}")


def main():
    """Main test function."""
    print("=" * 60)
    print("Series Lots Test Script")
    print("=" * 60)
    print()

    db_path = Path("books.db")

    # Initialize service
    print("Initializing book service...")
    service = BookService(
        database_path=db_path,
        ebay_app_id=None,  # Skip eBay
        metadata_delay=0.5  # Be respectful to metadata APIs
    )

    # Add test books
    add_test_books(service)
    print()

    # Match books to series
    print("Matching books to series...")
    from isbn_lot_optimizer.series_matcher import SeriesMatcher

    matcher = SeriesMatcher(db_path)
    books = service.list_books()

    matched_count = 0
    for book in books:
        title = book.metadata.title if book.metadata else ""
        authors = list(book.metadata.authors) if book.metadata and book.metadata.authors else []

        if not title or not authors:
            continue

        matches = matcher.match_book(
            isbn=book.isbn,
            book_title=title,
            book_authors=authors,
            auto_save=True
        )

        if matches:
            matched_count += 1
            best = matches[0]
            print(f"  ✓ {title[:40]}")
            print(f"    → {best['series_title']} ({best['confidence']:.0%})")

    matcher.close()
    print(f"\nMatched {matched_count} of {len(books)} books to series")
    print()

    # Generate series lots
    print("Generating series lots...")
    series_lots = build_series_lots_enhanced(books, db_path)

    print(f"Generated {len(series_lots)} series lots:\n")

    for i, lot in enumerate(series_lots, 1):
        print(f"{i}. {lot.name}")
        print(f"   Strategy: {lot.strategy}")
        print(f"   Books: {len(lot.book_isbns)}")
        print(f"   Value: ${lot.estimated_value:.2f}")
        print(f"   Probability: {lot.probability_label} ({lot.probability_score:.0f}%)")
        print(f"   Details:")
        for line in lot.justification:
            if "Have:" in line:
                print(f"      ✓ {line}")
            elif "Missing:" in line:
                print(f"      ○ {line}")
            elif "% complete" in line:
                print(f"      📊 {line}")
            else:
                print(f"      {line}")
        print()

    # Save lots to database
    print("Saving lots to database...")
    service.recalculate_lots()
    print("✓ Done")
    print()

    print("=" * 60)
    print("Test complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Start your web server: python3 -m isbn_web.main")
    print("2. Go to the Suggested Lots page")
    print("3. Look for series lots with have/missing information")
    print()


if __name__ == "__main__":
    main()
