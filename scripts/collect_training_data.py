"""
Collect training data for ML price estimation model.

Fetches eBay sold comps for books with Amazon pricing data to build
initial training dataset.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.ebay_sold_comps import EbaySoldComps


def get_books_with_amazon_data(db_path: Path, limit: Optional[int] = None) -> List[str]:
    """
    Get ISBNs of books that have Amazon pricing data.

    Args:
        db_path: Path to catalog.db
        limit: Maximum number of ISBNs to return

    Returns:
        List of ISBNs
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
    SELECT isbn
    FROM books
    WHERE bookscouter_json IS NOT NULL
      AND json_extract(bookscouter_json, '$.amazon_lowest_price') IS NOT NULL
      AND CAST(json_extract(bookscouter_json, '$.amazon_lowest_price') AS REAL) > 0
    ORDER BY updated_at DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    isbns = [row[0] for row in cursor.fetchall()]
    conn.close()

    return isbns


def fetch_sold_comps_for_book(isbn: str, sold_comps_service: EbaySoldComps) -> Optional[dict]:
    """
    Fetch eBay sold comps for a single book.

    Args:
        isbn: Book ISBN
        sold_comps_service: eBay sold comps service instance

    Returns:
        Sold comps result dict or None if failed
    """
    try:
        result = sold_comps_service.get_sold_comps(
            gtin=isbn,
            fallback_to_estimate=True,
            max_samples=5,
            include_signed=False
        )
        return result
    except Exception as e:
        print(f"  Error fetching comps for {isbn}: {e}")
        return None


def update_book_with_comps(db_path: Path, isbn: str, comps: dict) -> None:
    """
    Update book record with fetched sold comps.

    Args:
        db_path: Path to catalog.db
        isbn: Book ISBN
        comps: Sold comps result
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Update market_json with sold comps data
    cursor.execute(
        """
        UPDATE books
        SET market_json = json_patch(
                COALESCE(market_json, '{}'),
                json(?)
            ),
            sold_comps_count = ?,
            sold_comps_min = ?,
            sold_comps_median = ?,
            sold_comps_max = ?,
            sold_comps_is_estimate = ?,
            sold_comps_source = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE isbn = ?
        """,
        (
            json.dumps({
                "sold_comps_count": comps["count"],
                "sold_comps_min": comps["min"],
                "sold_comps_median": comps["median"],
                "sold_comps_max": comps["max"],
                "sold_comps_is_estimate": comps["is_estimate"],
                "sold_comps_source": comps["source"],
                "sold_comps_last_sold_date": comps.get("last_sold_date"),
            }),
            comps["count"],
            comps["min"],
            comps["median"],
            comps["max"],
            1 if comps["is_estimate"] else 0,
            comps["source"],
            isbn,
        )
    )

    conn.commit()
    conn.close()


def main():
    """Main entry point for training data collection."""
    import argparse

    parser = argparse.ArgumentParser(description="Collect eBay sold comps for ML training")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of books to fetch (default: all)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    # Initialize eBay sold comps service
    sold_comps = EbaySoldComps()

    # Get books with Amazon data
    print(f"Finding books with Amazon pricing data...")
    isbns = get_books_with_amazon_data(db_path, limit=args.limit)
    print(f"Found {len(isbns)} books to process")

    if not isbns:
        print("No books found with Amazon data")
        return 0

    # Fetch sold comps for each book
    success_count = 0
    failed_count = 0

    for i, isbn in enumerate(isbns, 1):
        print(f"[{i}/{len(isbns)}] Fetching comps for {isbn}...")

        comps = fetch_sold_comps_for_book(isbn, sold_comps)

        if comps:
            update_book_with_comps(db_path, isbn, comps)
            print(f"  ✓ Found {comps['count']} comps, median ${comps['median']:.2f} ({comps['source']})")
            success_count += 1
        else:
            print(f"  ✗ Failed to fetch comps")
            failed_count += 1

        # Rate limiting
        if i < len(isbns):
            time.sleep(args.delay)

    print("\n" + "=" * 70)
    print(f"Collection complete:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {len(isbns)}")

    if success_count > 0:
        print(f"\n✓ Ready to train ML model with {success_count} samples")
        print(f"  Run: python scripts/train_price_model.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
