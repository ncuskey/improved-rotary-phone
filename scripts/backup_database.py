#!/usr/bin/env python3
"""
Automated database backup before enrichment operations.

Usage:
    from scripts.backup_database import backup_database

    # Before any enrichment operation
    backup_path = backup_database(db_path, reason="pre-enrichment")
    # Now safe to make changes

Command line:
    python backup_database.py <db_path> [--reason <reason>]
    python backup_database.py ~/.isbn_lot_optimizer/catalog.db --reason pre-enrichment
"""

import shutil
import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse


def backup_database(db_path: Path, reason: str = "manual") -> Path:
    """
    Create a timestamped backup of a database file.

    Args:
        db_path: Path to the database file to backup
        reason: Reason for backup (e.g., "pre-enrichment", "manual", "daily")

    Returns:
        Path to the created backup file

    Example:
        >>> backup_path = backup_database(Path("~/.isbn_lot_optimizer/catalog.db"), "pre-enrichment")
        >>> print(f"Backup created at {backup_path}")
    """
    db_path = Path(db_path).expanduser().resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # Create backup directory if it doesn't exist
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    # Generate timestamped backup name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{db_path.stem}_{reason}_{timestamp}.db"
    backup_path = backup_dir / backup_name

    # Copy database file
    shutil.copy2(db_path, backup_path)

    # Get size for reporting
    size_mb = backup_path.stat().st_size / (1024 * 1024)

    print(f"✓ Backup created: {backup_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Reason: {reason}")

    # Cleanup old backups
    cleanup_old_backups(backup_dir, days=30)

    return backup_path


def cleanup_old_backups(backup_dir: Path, days: int = 30):
    """
    Remove backups older than specified days, with retention policy.

    Retention policy:
    - Keep all backups for 30 days
    - Keep weekly backups for 6 months
    - Keep monthly backups for 1 year

    Args:
        backup_dir: Directory containing backups
        days: Number of days to keep all backups
    """
    if not backup_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=days)
    six_months_ago = datetime.now() - timedelta(days=180)
    one_year_ago = datetime.now() - timedelta(days=365)

    deleted_count = 0
    kept_count = 0

    # Group backups by week and month
    weekly_backups = {}  # week_key -> newest backup
    monthly_backups = {}  # month_key -> newest backup

    for backup_file in backup_dir.glob("*.db"):
        try:
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

            # Keep all backups less than 30 days old
            if mtime > cutoff_date:
                kept_count += 1
                continue

            # For backups 30 days to 6 months old, keep one per week
            if mtime > six_months_ago:
                week_key = mtime.strftime("%Y-W%W")
                if week_key not in weekly_backups or mtime > weekly_backups[week_key][0]:
                    weekly_backups[week_key] = (mtime, backup_file)
                continue

            # For backups 6 months to 1 year old, keep one per month
            if mtime > one_year_ago:
                month_key = mtime.strftime("%Y-%m")
                if month_key not in monthly_backups or mtime > monthly_backups[month_key][0]:
                    monthly_backups[month_key] = (mtime, backup_file)
                continue

            # Delete backups older than 1 year
            backup_file.unlink()
            deleted_count += 1

        except Exception as e:
            print(f"Warning: Error processing {backup_file}: {e}")

    # Keep the weekly and monthly backups we selected
    kept_weekly = {path for _, path in weekly_backups.values()}
    kept_monthly = {path for _, path in monthly_backups.values()}

    # Delete old backups that aren't weekly or monthly keepers
    for backup_file in backup_dir.glob("*.db"):
        try:
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

            if cutoff_date < mtime <= six_months_ago:
                if backup_file not in kept_weekly:
                    backup_file.unlink()
                    deleted_count += 1
                else:
                    kept_count += 1

            elif six_months_ago < mtime <= one_year_ago:
                if backup_file not in kept_monthly:
                    backup_file.unlink()
                    deleted_count += 1
                else:
                    kept_count += 1

        except Exception as e:
            pass  # Already processed or error

    if deleted_count > 0:
        print(f"  Cleaned up {deleted_count} old backups (keeping {kept_count} recent/weekly/monthly)")


def list_backups(db_name: str = None):
    """
    List available backups, optionally filtered by database name.

    Args:
        db_name: Optional database name to filter (e.g., "catalog")
    """
    backup_dir = Path.home() / ".isbn_lot_optimizer" / "backups"

    if not backup_dir.exists():
        print("No backups found (backup directory doesn't exist)")
        return

    pattern = f"{db_name}_*.db" if db_name else "*.db"
    backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        print(f"No backups found for {db_name or 'any database'}")
        return

    print(f"\nAvailable backups in {backup_dir}:")
    print("=" * 80)

    for i, backup in enumerate(backups, 1):
        size = backup.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)
        age = datetime.now() - mtime

        # Parse reason from filename
        parts = backup.stem.split('_')
        if len(parts) >= 3:
            reason = '_'.join(parts[1:-2]) if len(parts) > 3 else parts[1]
        else:
            reason = "unknown"

        age_str = f"{age.days}d ago" if age.days > 0 else f"{age.seconds//3600}h ago"

        print(f"{i:3d}. {backup.name}")
        print(f"     Size: {size:.1f} MB | Created: {mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age_str}) | Reason: {reason}")


def main():
    parser = argparse.ArgumentParser(description="Backup database before enrichment operations")
    parser.add_argument("db_path", nargs='?', help="Path to database file")
    parser.add_argument("--reason", default="manual", help="Reason for backup (e.g., pre-enrichment)")
    parser.add_argument("--list", action="store_true", help="List available backups")
    parser.add_argument("--db-name", help="Filter backups by database name when using --list")

    args = parser.parse_args()

    if args.list:
        list_backups(args.db_name)
        return

    if not args.db_path:
        parser.error("db_path is required unless using --list")

    try:
        backup_path = backup_database(Path(args.db_path), args.reason)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
