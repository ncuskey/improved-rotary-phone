#!/usr/bin/env python3
"""
Verify that series lots are being generated correctly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.series_lots import build_series_lots_enhanced
from isbn_lot_optimizer.service import BookService


def main():
    db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    print("="*70)
    print("Series Lots Verification")
    print("="*70)
    print()

    # Initialize service
    service = BookService(
        database_path=db_path,
        ebay_app_id=None
    )

    # Get all books
    books = service.list_books()
    print(f"Total books in database: {len(books)}")
    print()

    # Build series lots
    print("Building series lots...")
    series_lots = build_series_lots_enhanced(books, db_path)

    print(f"✓ Generated {len(series_lots)} series lots")
    print()

    if not series_lots:
        print("No series lots generated. This could mean:")
        print("  - No books are matched to series")
        print("  - No series has 2+ books")
        print("  - All lots below $10 value threshold")
        return

    # Show top 10 series lots
    print("Top Series Lots:")
    print("-" * 70)

    for i, lot in enumerate(series_lots[:10], 1):
        print(f"\n{i}. {lot.name}")
        print(f"   Books: {len(lot.book_isbns)} | Value: ${lot.estimated_value:.2f} | Probability: {lot.probability_label}")

        for line in lot.justification:
            if "% complete" in line:
                print(f"   📊 {line}")
            elif "Have:" in line:
                print(f"   ✓ {line}")
            elif "Missing:" in line:
                print(f"   ○ {line}")

    print()
    print("="*70)
    print("Verification complete!")
    print()
    print("These lots should appear in your web interface at:")
    print("http://localhost:8000/lots")
    print()


if __name__ == "__main__":
    main()
