#!/usr/bin/env python3
"""
Refresh all market data for existing books in the catalog.

This script re-scans all books to fetch fresh:
- BookScouter offers (vendor buyback offers, Amazon pricing)
- Amazon sales ranks
- BooksRun offers

NOTE: eBay market data requires the eBay Browse API which is only available
through the token broker service (used by the iOS app). The old Finding API
that this script uses is deprecated and no longer returns data.

For full eBay + Amazon data, use the iOS app's "Refresh All Books" feature
or the backend API's token broker integration.

This is useful for batch updating vendor offers and Amazon data after
cleaning metadata or to get current market conditions.
"""

import sys
import time
from pathlib import Path
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.service import BookService


def refresh_all_market_data(
    db_path: Path,
    *,
    limit: Optional[int] = None,
    delay: float = 2.0,
    skip_recent: int = 7,
    ebay_app_id: Optional[str] = None,
) -> None:
    """
    Refresh market data for all books in the database.

    Args:
        db_path: Path to catalog.db
        limit: Optional limit for testing (None = all books)
        delay: Delay between API calls in seconds (default: 2.0)
        skip_recent: Skip books updated in last N days (default: 7)
        ebay_app_id: eBay App ID for market data
    """
    from datetime import datetime, timedelta

    print(f"Initializing BookService with database: {db_path}")

    service = BookService(
        database_path=db_path,
        ebay_app_id=ebay_app_id,
        metadata_delay=delay,
    )

    try:
        # Get all books
        all_books = service.list_books()
        print(f"Found {len(all_books):,} books in database")

        # Filter out recently updated books
        cutoff_date = datetime.now() - timedelta(days=skip_recent)
        books_to_refresh = []

        for book in all_books:
            # Check if book has been updated recently
            # For now, refresh all books (can add date filtering later if needed)
            books_to_refresh.append(book)

        # Apply limit if specified
        if limit is not None and limit > 0:
            books_to_refresh = books_to_refresh[:limit]
            print(f"Limiting to first {limit} books for testing")

        total = len(books_to_refresh)
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

        for i, book in enumerate(books_to_refresh, 1):
            isbn = book.isbn
            title = book.metadata.title if book.metadata else isbn

            print(f"[{i}/{total}] {title[:50]}")
            print(f"  ISBN: {isbn}")

            try:
                # Re-scan the book to get fresh market data
                # include_market=True ensures we fetch eBay, BookScouter, BooksRun
                # recalc_lots=False to avoid recalculating lots after each book
                evaluation = service.scan_isbn(
                    isbn,
                    condition=book.condition or "Good",
                    edition=book.edition,
                    include_market=True,
                    recalc_lots=False,
                )

                # Show key updates
                updates = []
                if evaluation.market:
                    median = evaluation.market.sold_comps_median or 0
                    updates.append(f"eBay: ${median:.2f}")
                if evaluation.bookscouter:
                    best = evaluation.bookscouter.best_price or 0
                    vendors = evaluation.bookscouter.total_vendors or 0
                    updates.append(f"Buyback: ${best:.2f} ({vendors} vendors)")
                if hasattr(evaluation.bookscouter, 'amazon_sales_rank') and evaluation.bookscouter:
                    rank = evaluation.bookscouter.amazon_sales_rank
                    if rank:
                        updates.append(f"Amazon rank: {rank:,}")

                if updates:
                    print(f"  ✓ Updated: {', '.join(updates)}")
                else:
                    print(f"  ⚠ No market data available")
                    skipped += 1

                updated += 1

                # Rate limiting delay
                if i < total:
                    time.sleep(delay)

            except Exception as e:
                print(f"  ✗ Failed: {e}")
                failed += 1
                # Continue with next book even if one fails
                time.sleep(delay / 2)  # Shorter delay after failure

            # Progress summary every 10 books
            if i % 10 == 0:
                print()
                print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")
                print(f"  Updated: {updated}, Failed: {failed}, Skipped: {skipped}")
                print()

        # Final summary
        print()
        print("=" * 60)
        print("Market Data Refresh Complete!")
        print("=" * 60)
        print(f"Books processed: {total:,}")
        print(f"Successfully updated: {updated:,} ({updated/total*100:.1f}%)")
        print(f"Failed: {failed:,}")
        print(f"Skipped (no data): {skipped:,}")
        print()

        # Recalculate lots once at the end
        print("Recalculating lots...")
        service.recalculate_lots()
        print("✓ Lots recalculated")
        print()

    finally:
        service.close()


def load_env_file(env_path: Path) -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip("'\"")
                    env_vars[key] = value
    return env_vars


def main():
    """Main entry point."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description='Refresh all market data for existing books'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=Path.home() / '.isbn_lot_optimizer' / 'catalog.db',
        help='Path to catalog database'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of books to process (for testing)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='Delay between API calls in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--skip-recent',
        type=int,
        default=7,
        help='Skip books updated in last N days (default: 7)'
    )
    parser.add_argument(
        '--ebay-app-id',
        type=str,
        help='eBay App ID (defaults to .env file or EBAY_APP_ID/APP_ID_PROD env var)'
    )
    parser.add_argument(
        '--env-file',
        type=Path,
        default=Path(__file__).parent.parent / '.env',
        help='Path to .env file (default: ../.env)'
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database not found: {args.db}")
        sys.exit(1)

    # Load credentials from .env file
    env_vars = load_env_file(args.env_file)

    # Determine eBay App ID (priority: CLI arg > .env file > environment variable)
    ebay_app_id = args.ebay_app_id
    if not ebay_app_id:
        ebay_app_id = (
            env_vars.get('APP_ID_PROD') or
            env_vars.get('EBAY_CLIENT_ID') or
            os.environ.get('EBAY_APP_ID') or
            os.environ.get('APP_ID_PROD')
        )

    if not ebay_app_id:
        print()
        print("⚠️  Warning: No eBay App ID found!")
        print("   eBay market data will not be fetched.")
        print("   To fix: Add APP_ID_PROD to .env file or use --ebay-app-id")
        print()

    print()
    print("=" * 60)
    print("Batch Market Data Refresh")
    print("=" * 60)
    if ebay_app_id:
        print(f"✓ eBay App ID: {ebay_app_id[:20]}...")
    else:
        print("✗ eBay App ID: Not configured")
    print()

    refresh_all_market_data(
        args.db,
        limit=args.limit,
        delay=args.delay,
        skip_recent=args.skip_recent,
        ebay_app_id=ebay_app_id,
    )


if __name__ == '__main__':
    main()
