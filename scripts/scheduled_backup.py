#!/usr/bin/env python3
"""
Scheduled database backup script.

Backs up all critical ISBN Lot Optimizer databases on a schedule.
Designed to run via cron/launchd for automated daily/hourly backups.

Usage:
    # Manual run
    python scripts/scheduled_backup.py

    # With custom reason tag
    python scripts/scheduled_backup.py --reason daily

    # Backup only changed databases (modified in last N hours)
    python scripts/scheduled_backup.py --if-changed 6

Setup automated backups (macOS launchd):
    # Hourly backups during scraping
    cp scripts/com.isbn.hourly-backup.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.isbn.hourly-backup.plist

    # Daily backups (3 AM)
    cp scripts/com.isbn.daily-backup.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.isbn.daily-backup.plist

Setup automated backups (Linux cron):
    # Hourly backups during scraping
    0 * * * * /usr/bin/python3 /path/to/scripts/scheduled_backup.py --reason hourly

    # Daily backups at 3 AM
    0 3 * * * /usr/bin/python3 /path/to/scripts/scheduled_backup.py --reason daily
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backup_database import backup_database


def get_all_databases() -> list[Path]:
    """Get list of all ISBN Lot Optimizer database files."""
    db_dir = Path.home() / '.isbn_lot_optimizer'

    # Critical databases to backup
    databases = [
        db_dir / 'catalog.db',
        db_dir / 'metadata_cache.db',
        db_dir / 'books.db',
        db_dir / 'training_data.db',
        db_dir / 'unified_index.db',
        db_dir / 'unsigned_pairs.db',
    ]

    # Return only existing databases
    return [db for db in databases if db.exists()]


def should_backup_database(db_path: Path, hours_threshold: int) -> bool:
    """
    Check if database has been modified within the last N hours.

    Args:
        db_path: Path to database file
        hours_threshold: Number of hours to check

    Returns:
        True if database was modified within threshold, False otherwise
    """
    try:
        mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
        threshold = datetime.now() - timedelta(hours=hours_threshold)
        return mtime > threshold
    except Exception:
        # If we can't determine, backup anyway (safer)
        return True


def main():
    """Run scheduled backup of all databases."""
    parser = argparse.ArgumentParser(description='Scheduled database backup')
    parser.add_argument(
        '--reason',
        default='scheduled',
        help='Reason tag for backup (e.g., hourly, daily, weekly)'
    )
    parser.add_argument(
        '--if-changed',
        type=int,
        metavar='HOURS',
        help='Only backup databases modified in last N hours'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress output (for cron jobs)'
    )

    args = parser.parse_args()

    if not args.quiet:
        print("=" * 70)
        print("ISBN LOT OPTIMIZER - SCHEDULED DATABASE BACKUP")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Reason: {args.reason}")
        print("=" * 70)
        print()

    databases = get_all_databases()

    if not databases:
        print("⚠️  No databases found in ~/.isbn_lot_optimizer/")
        return 1

    backed_up = 0
    skipped = 0
    failed = 0
    total_size = 0

    for db_path in databases:
        db_name = db_path.name

        # Check if we should backup based on modification time
        if args.if_changed:
            if not should_backup_database(db_path, args.if_changed):
                if not args.quiet:
                    print(f"⏭️  {db_name}: Skipped (not modified in last {args.if_changed} hours)")
                skipped += 1
                continue

        # Perform backup
        try:
            if not args.quiet:
                print(f"📦 {db_name}: Backing up...", end=' ', flush=True)

            backup_path = backup_database(db_path, reason=args.reason)
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            total_size += size_mb

            if not args.quiet:
                print(f"✅ ({size_mb:.1f} MB)")
            backed_up += 1

        except Exception as e:
            if not args.quiet:
                print(f"❌ Failed: {e}")
            failed += 1

    # Summary
    if not args.quiet:
        print()
        print("=" * 70)
        print("BACKUP SUMMARY")
        print("=" * 70)
        print(f"✅ Backed up: {backed_up} databases ({total_size:.1f} MB)")
        if skipped > 0:
            print(f"⏭️  Skipped: {skipped} databases")
        if failed > 0:
            print(f"❌ Failed: {failed} databases")
        print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
