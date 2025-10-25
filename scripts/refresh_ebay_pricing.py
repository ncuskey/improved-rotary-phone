#!/usr/bin/env python3
"""
Refresh eBay pricing (Track B sold comps) for all books in the catalog.

This script fetches:
- Active listing data from eBay Browse API
- Track B sold comps (25th percentile for used, median for new)
- Updates sold_comps_median field in database

This provides conservative pricing estimates from active eBay listings.
"""

import sys
import time
import sqlite3
import os
from pathlib import Path
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from isbn_lot_optimizer.market import fetch_market_stats_v2


def refresh_ebay_pricing(
    db_path: Path,
    *,
    limit: Optional[int] = None,
    delay: float = 1.5,
) -> None:
    """
    Refresh eBay pricing for all books in the database.

    Args:
        db_path: Path to catalog.db
        limit: Optional limit for testing (None = all books)
        delay: Delay between API calls in seconds (default: 1.5)
    """
    print("=" * 60)
    print("eBay Track B Pricing Refresh")
    print("=" * 60)
    print()

    # Get all accepted books
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT isbn, title, condition
        FROM books
        WHERE status = 'ACCEPT'
        ORDER BY title
    """)
    books = cursor.fetchall()
    conn.close()

    print(f"Found {len(books):,} accepted books in database")

    # Apply limit if specified
    if limit is not None and limit > 0:
        books = books[:limit]
        print(f"Limiting to first {limit} books for testing")

    total = len(books)
    if total == 0:
        print("No books to refresh!")
        return

    print(f"Refreshing {total:,} books...")
    print(f"Delay between requests: {delay}s")
    print(f"Estimated time: {(total * delay) / 60:.1f} minutes")
    print()

    updated = 0
    failed = 0
    skipped = 0

    for i, (isbn, title, condition) in enumerate(books, 1):
        print(f"[{i}/{total}] {title[:50]}")
        print(f"  ISBN: {isbn}")

        try:
            # Fetch eBay market stats with sold comps
            stats_dict = fetch_market_stats_v2(isbn, include_sold_comps=True)

            if stats_dict and "error" not in stats_dict:
                # Extract sold comps data
                sold_comps_count = stats_dict.get("sold_comps_count")
                sold_comps_median = stats_dict.get("sold_comps_median")
                sold_comps_min = stats_dict.get("sold_comps_min")
                sold_comps_max = stats_dict.get("sold_comps_max")
                sold_comps_is_estimate = stats_dict.get("sold_comps_is_estimate", True)
                sold_comps_source = stats_dict.get("sold_comps_source", "estimate")

                # Update database
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE books
                    SET sold_comps_count = ?,
                        sold_comps_median = ?,
                        sold_comps_min = ?,
                        sold_comps_max = ?,
                        sold_comps_is_estimate = ?,
                        sold_comps_source = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE isbn = ?
                """, (
                    sold_comps_count,
                    sold_comps_median,
                    sold_comps_min,
                    sold_comps_max,
                    1 if sold_comps_is_estimate else 0,
                    sold_comps_source,
                    isbn
                ))
                conn.commit()
                conn.close()

                if sold_comps_median:
                    print(f"  ✓ Updated: eBay median ${sold_comps_median:.2f} ({sold_comps_source})")
                else:
                    print(f"  ⚠ No pricing data available")
                    skipped += 1
                updated += 1
            else:
                error_msg = stats_dict.get("error", "Unknown error") if stats_dict else "No response"
                print(f"  ⚠ Failed: {error_msg}")
                failed += 1

        except Exception as e:
            print(f"  ⚠ Error: {e}")
            failed += 1

        # Progress summary every 50 books
        if i % 50 == 0:
            print()
            print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")
            print(f"  Updated: {updated}, Failed: {failed}, Skipped: {skipped}")
            print()

        # Rate limiting
        if i < total:
            time.sleep(delay)

    print()
    print("=" * 60)
    print("Refresh Complete")
    print("=" * 60)
    print(f"Total: {total}")
    print(f"✓ Updated: {updated}")
    print(f"✗ Failed: {failed}")
    print(f"⊘ Skipped: {skipped}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh eBay pricing for all books")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of books to refresh (for testing)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay between API calls in seconds (default: 1.5)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to catalog.db (default: ~/.isbn_lot_optimizer/catalog.db)",
    )

    args = parser.parse_args()

    if args.db:
        db_path = Path(args.db)
    else:
        db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    refresh_ebay_pricing(
        db_path=db_path,
        limit=args.limit,
        delay=args.delay,
    )
