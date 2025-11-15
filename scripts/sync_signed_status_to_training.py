#!/usr/bin/env python3
"""
Sync signed book status from multiple sources to training database.

This script aggregates signed book information from:
1. BookFinder offers (bookfinder_offers table in metadata_cache.db)
2. eBay sold listings (sold_listings table in catalog.db)
3. eBay active listings (ebay_listings table in catalog.db)

And updates the cached_books.signed field for training.

Usage:
    python3 scripts/sync_signed_status_to_training.py [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Set

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.feature_detector import is_signed


def get_signed_isbns_from_bookfinder(metadata_db: str) -> Set[str]:
    """Get ISBNs with signed BookFinder offers from metadata_cache.db."""
    try:
        conn = sqlite3.connect(metadata_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT isbn
            FROM bookfinder_offers
            WHERE is_signed = 1
        """)
        isbns = {row[0] for row in cursor.fetchall()}
        conn.close()

        print(f"  ✓ BookFinder: {len(isbns)} signed ISBNs")
        return isbns
    except sqlite3.OperationalError as e:
        print(f"  ⚠ BookFinder query failed: {e}")
        return set()


def get_signed_isbns_from_sold_listings(catalog_db: str) -> Set[str]:
    """Get ISBNs with signed sold listings from catalog.db."""
    try:
        conn = sqlite3.connect(catalog_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT isbn
            FROM sold_listings
            WHERE signed = 1
        """)
        isbns = {row[0] for row in cursor.fetchall()}
        conn.close()

        print(f"  ✓ Sold listings: {len(isbns)} signed ISBNs")
        return isbns
    except sqlite3.OperationalError as e:
        print(f"  ⚠ Sold listings query failed: {e}")
        return set()


def get_signed_isbns_from_active_listings(catalog_db: str) -> Set[str]:
    """Get ISBNs with signed active listings by parsing titles from catalog.db."""
    try:
        conn = sqlite3.connect(catalog_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT isbn, title
            FROM ebay_listings
            WHERE title IS NOT NULL
        """)

        isbns = set()
        for row in cursor.fetchall():
            isbn, title = row
            if is_signed(title):
                isbns.add(isbn)

        conn.close()
        print(f"  ✓ Active listings: {len(isbns)} signed ISBNs (parsed from titles)")
        return isbns
    except sqlite3.OperationalError as e:
        print(f"  ⚠ Active listings query failed: {e}")
        return set()


def sync_signed_status(metadata_db: str, catalog_db: str, dry_run: bool = False) -> None:
    """Sync signed status from all sources to cached_books."""

    print("="*80)
    print("SYNCING SIGNED BOOK STATUS TO TRAINING DATA")
    print("="*80)
    print()

    # Connect to metadata_cache.db (where cached_books lives)
    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    # Check if cached_books table exists
    try:
        cursor.execute("SELECT COUNT(*) FROM cached_books")
        total_books = cursor.fetchone()[0]
        print(f"Training database: {total_books} total books in cached_books")
        print()
    except sqlite3.OperationalError:
        print("✗ cached_books table not found in metadata_cache.db")
        print("  Database may not be initialized.")
        conn.close()
        return

    # Check current signed count
    cursor.execute("SELECT COUNT(*) FROM cached_books WHERE signed = 1")
    current_signed = cursor.fetchone()[0]
    if total_books > 0:
        print(f"Current signed books: {current_signed} ({current_signed/total_books*100:.2f}%)")
    else:
        print(f"Current signed books: {current_signed}")
    print()

    # Collect signed ISBNs from all sources
    print("Collecting signed ISBNs from data sources...")
    all_signed_isbns = set()

    # BookFinder offers (in metadata_cache.db)
    all_signed_isbns.update(get_signed_isbns_from_bookfinder(metadata_db))

    # Sold listings and active listings (in catalog.db)
    all_signed_isbns.update(get_signed_isbns_from_sold_listings(catalog_db))
    all_signed_isbns.update(get_signed_isbns_from_active_listings(catalog_db))

    print()
    print(f"Total unique signed ISBNs found: {len(all_signed_isbns)}")

    if len(all_signed_isbns) == 0:
        print("⚠ No signed ISBNs found in data sources")
        conn.close()
        return

    # Check how many are not yet flagged
    placeholders = ','.join('?' * len(all_signed_isbns))
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM cached_books
        WHERE isbn IN ({placeholders}) AND signed = 0
    """, tuple(all_signed_isbns))

    to_update = cursor.fetchone()[0]
    print(f"ISBNs to update (currently signed=0): {to_update}")
    print()

    if to_update == 0:
        print("✓ All signed ISBNs are already flagged in cached_books")
        conn.close()
        return

    if dry_run:
        print("DRY RUN: Would update signed=1 for the following ISBNs:")
        cursor.execute(f"""
            SELECT isbn, title
            FROM cached_books
            WHERE isbn IN ({placeholders}) AND signed = 0
            LIMIT 10
        """, tuple(all_signed_isbns))

        for row in cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")

        if to_update > 10:
            print(f"  ... and {to_update - 10} more")
    else:
        print(f"Updating signed=1 for {to_update} ISBNs...")

        cursor.execute(f"""
            UPDATE cached_books
            SET signed = 1
            WHERE isbn IN ({placeholders}) AND signed = 0
        """, tuple(all_signed_isbns))

        conn.commit()
        print(f"✓ Updated {cursor.rowcount} records")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM cached_books WHERE signed = 1")
        new_signed = cursor.fetchone()[0]
        print()
        if total_books > 0:
            print(f"New signed book count: {new_signed} ({new_signed/total_books*100:.2f}%)")
        else:
            print(f"New signed book count: {new_signed}")
        print(f"Improvement: +{new_signed - current_signed} signed books")

    conn.close()

    print()
    print("="*80)
    print("SYNC COMPLETE")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Sync signed book status to training database"
    )
    parser.add_argument(
        '--metadata-db',
        default=str(Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'),
        help='Path to metadata_cache.db (default: ~/.isbn_lot_optimizer/metadata_cache.db)'
    )
    parser.add_argument(
        '--catalog-db',
        default=str(Path.home() / '.isbn_lot_optimizer' / 'catalog.db'),
        help='Path to catalog.db (default: ~/.isbn_lot_optimizer/catalog.db)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    args = parser.parse_args()

    # Check databases exist
    metadata_path = Path(args.metadata_db)
    catalog_path = Path(args.catalog_db)

    if not metadata_path.exists():
        print(f"✗ Metadata database not found: {metadata_path}")
        return 1

    if not catalog_path.exists():
        print(f"✗ Catalog database not found: {catalog_path}")
        return 1

    sync_signed_status(args.metadata_db, args.catalog_db, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
