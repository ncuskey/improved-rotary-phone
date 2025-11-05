#!/usr/bin/env python3
"""
WatchCount infrastructure deprecation script.

Removes WatchCount-related code and database tables now that we're using
the new Serper.dev-based sold listing discovery system.

This script:
1. Drops watchcount_sold table and indexes
2. Removes WatchCount-related Python files
3. Cleans up __pycache__ files
4. Provides summary of changes
"""

import sys
import sqlite3
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def drop_watchcount_table(db_path: Path, dry_run: bool = False):
    """
    Drop watchcount_sold table and indexes.

    Args:
        db_path: Path to catalog.db
        dry_run: If True, only report what would be done
    """
    print("1. Database Cleanup")
    print("-" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='watchcount_sold'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        print("  ✓ watchcount_sold table does not exist (already removed)")
        conn.close()
        return

    # Check row count
    cursor.execute("SELECT COUNT(*) FROM watchcount_sold")
    row_count = cursor.fetchone()[0]

    print(f"  Found watchcount_sold table with {row_count} rows")

    if row_count > 0:
        print("  ⚠ WARNING: Table contains data!")
        response = input("  Continue with deletion? (yes/no): ")
        if response.lower() != 'yes':
            print("  Aborted")
            conn.close()
            return

    if dry_run:
        print("  [DRY RUN] Would drop watchcount_sold table and indexes")
    else:
        # Drop indexes
        cursor.execute("DROP INDEX IF EXISTS idx_watchcount_isbn")
        cursor.execute("DROP INDEX IF EXISTS idx_watchcount_sold_date")

        # Drop table
        cursor.execute("DROP TABLE IF EXISTS watchcount_sold")

        conn.commit()
        print("  ✓ Dropped watchcount_sold table")
        print("  ✓ Dropped indexes: idx_watchcount_isbn, idx_watchcount_sold_date")

    conn.close()
    print()


def remove_watchcount_files(project_root: Path, dry_run: bool = False):
    """
    Remove WatchCount-related Python files.

    Args:
        project_root: Project root directory
        dry_run: If True, only report what would be done
    """
    print("2. File Cleanup")
    print("-" * 80)

    files_to_remove = [
        project_root / 'shared' / 'watchcount_parser.py',
        project_root / 'shared' / 'watchcount_scraper.py',
        project_root / 'scripts' / 'test_watchcount_scraper.py',
        project_root / 'scripts' / 'collect_watchcount_sold.py',
    ]

    # Add __pycache__ files
    pycache_files = list(project_root.glob('shared/__pycache__/watchcount_*.pyc'))
    files_to_remove.extend(pycache_files)

    removed_count = 0
    for file_path in files_to_remove:
        if file_path.exists():
            if dry_run:
                print(f"  [DRY RUN] Would remove: {file_path.relative_to(project_root)}")
            else:
                file_path.unlink()
                print(f"  ✓ Removed: {file_path.relative_to(project_root)}")
            removed_count += 1

    if removed_count == 0:
        print("  ✓ No WatchCount files found (already removed)")

    print()


def print_summary():
    """Print summary of deprecation."""
    print("=" * 80)
    print("WATCHCOUNT DEPRECATION COMPLETE")
    print("=" * 80)
    print()
    print("WatchCount infrastructure has been removed and replaced with:")
    print()
    print("New System:")
    print("  • Serper.dev Google Search API for URL discovery")
    print("  • Decodo scraping for HTML retrieval")
    print("  • Platform-specific parsers (eBay, Mercari, Amazon)")
    print("  • Unified sold_listings database table")
    print("  • sold_stats.py for aggregated statistics")
    print()
    print("Benefits:")
    print("  • Multi-platform support (not just eBay)")
    print("  • More reliable (no bot detection like WatchCount)")
    print("  • Cost-effective ($50 for 50,000 searches)")
    print("  • Direct source data (no aggregator dependency)")
    print()
    print("Next Steps:")
    print("  1. Run: python scripts/collect_sold_listings.py --limit 10")
    print("  2. Verify data in sold_listings table")
    print("  3. Compute statistics with sold_stats.py")
    print()


def main():
    """Run deprecation process."""
    import argparse

    parser = argparse.ArgumentParser(description='Deprecate WatchCount infrastructure')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--skip-db',
        action='store_true',
        help='Skip database cleanup (only remove files)'
    )
    parser.add_argument(
        '--skip-files',
        action='store_true',
        help='Skip file cleanup (only drop database table)'
    )

    args = parser.parse_args()

    print()
    print("=" * 80)
    print("WATCHCOUNT INFRASTRUCTURE DEPRECATION")
    print("=" * 80)
    print()

    if args.dry_run:
        print("⚠ DRY RUN MODE - No changes will be made")
        print()

    project_root = Path(__file__).parent.parent
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    # Drop database table
    if not args.skip_db:
        drop_watchcount_table(db_path, args.dry_run)

    # Remove files
    if not args.skip_files:
        remove_watchcount_files(project_root, args.dry_run)

    # Print summary
    if not args.dry_run:
        print_summary()
    else:
        print()
        print("To apply these changes, run without --dry-run")
        print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
