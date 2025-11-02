#!/usr/bin/env python3
"""
Database restoration utility with safety checks.

Usage:
    # List available backups
    python restore_database.py --list
    python restore_database.py --list --db-name catalog

    # Restore from specific backup
    python restore_database.py --backup <backup_file>
    python restore_database.py --backup ~/.isbn_lot_optimizer/backups/catalog_pre-enrichment_20250131_143022.db

    # Restore most recent backup
    python restore_database.py --latest --db-name catalog

    # Skip safety backup (not recommended)
    python restore_database.py --backup <file> --no-backup

Safety Features:
- Automatically backs up current state before restoring
- Validates backup file integrity
- Confirms database path is correct
- Shows file sizes and modification times
"""

import shutil
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import argparse
from backup_database import backup_database, list_backups


def validate_db_file(db_path: Path) -> bool:
    """
    Validate that a file is a valid SQLite database.

    Args:
        db_path: Path to database file to validate

    Returns:
        True if valid SQLite database, False otherwise
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # Try to query sqlite_master table (exists in all SQLite DBs)
        cursor.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True
    except Exception as e:
        print(f"Validation error: {e}")
        return False


def get_backup_info(backup_path: Path) -> dict:
    """
    Get information about a backup file.

    Args:
        backup_path: Path to backup file

    Returns:
        Dictionary with backup information
    """
    stat = backup_path.stat()

    # Parse metadata from filename
    # Format: catalog_reason_20250131_143022.db
    parts = backup_path.stem.split('_')

    if len(parts) >= 3:
        db_name = parts[0]
        # Timestamp is last 2 parts (date and time)
        timestamp_str = f"{parts[-2]}_{parts[-1]}"
        # Reason is everything in between
        reason = '_'.join(parts[1:-2]) if len(parts) > 3 else parts[1]
    else:
        db_name = "unknown"
        reason = "unknown"
        timestamp_str = ""

    return {
        'path': backup_path,
        'db_name': db_name,
        'reason': reason,
        'timestamp': timestamp_str,
        'size_mb': stat.st_size / (1024 * 1024),
        'mtime': datetime.fromtimestamp(stat.st_mtime),
    }


def restore_database(
    backup_path: Path,
    target_db_path: Path = None,
    create_safety_backup: bool = True
) -> bool:
    """
    Restore a database from a backup file.

    Args:
        backup_path: Path to backup file to restore from
        target_db_path: Optional target database path (inferred from backup name if not provided)
        create_safety_backup: If True, backup current state before restoring

    Returns:
        True if restoration successful

    Example:
        >>> restore_database(Path("backups/catalog_pre-enrichment_20250131.db"))
        ✓ Safety backup created: catalog_pre-restore_20250131_143500.db
        ✓ Database restored from: catalog_pre-enrichment_20250131.db
    """
    backup_path = Path(backup_path).expanduser().resolve()

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Validate backup is a real SQLite database
    print("Validating backup file...")
    if not validate_db_file(backup_path):
        raise ValueError(f"Backup file is not a valid SQLite database: {backup_path}")
    print("✓ Backup file is valid")

    # Infer target database path if not provided
    if target_db_path is None:
        backup_info = get_backup_info(backup_path)
        db_name = backup_info['db_name']

        # Standard location for databases
        target_db_path = Path.home() / ".isbn_lot_optimizer" / f"{db_name}.db"

        print(f"Target database inferred: {target_db_path}")
    else:
        target_db_path = Path(target_db_path).expanduser().resolve()

    # Get backup info for display
    backup_info = get_backup_info(backup_path)

    # Show what's about to happen
    print("\n" + "=" * 70)
    print("RESTORE OPERATION")
    print("=" * 70)
    print(f"FROM: {backup_path.name}")
    print(f"      Created: {backup_info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"      Reason: {backup_info['reason']}")
    print(f"      Size: {backup_info['size_mb']:.1f} MB")
    print()
    print(f"TO:   {target_db_path}")

    if target_db_path.exists():
        current_size = target_db_path.stat().st_size / (1024 * 1024)
        current_mtime = datetime.fromtimestamp(target_db_path.stat().st_mtime)
        print(f"      Current size: {current_size:.1f} MB")
        print(f"      Last modified: {current_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("      (File does not currently exist)")

    print("=" * 70)

    # Confirmation prompt
    response = input("\nProceed with restore? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Restore cancelled by user")
        return False

    # Create safety backup of current state
    if create_safety_backup and target_db_path.exists():
        print("\nCreating safety backup of current state...")
        try:
            safety_backup_path = backup_database(target_db_path, reason="pre-restore")
            print(f"✓ Safety backup created: {safety_backup_path.name}")
        except Exception as e:
            print(f"Error creating safety backup: {e}")
            response = input("Continue without safety backup? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("Restore cancelled")
                return False

    # Perform the restoration
    print("\nRestoring database...")
    try:
        # Copy backup to target location
        shutil.copy2(backup_path, target_db_path)

        # Validate restored database
        if not validate_db_file(target_db_path):
            raise ValueError("Restored database failed validation")

        restored_size = target_db_path.stat().st_size / (1024 * 1024)

        print(f"✓ Database restored successfully")
        print(f"  Size: {restored_size:.1f} MB")
        print(f"  Location: {target_db_path}")

        return True

    except Exception as e:
        print(f"✗ Error during restore: {e}", file=sys.stderr)

        # If we created a safety backup, offer to restore it
        if create_safety_backup and 'safety_backup_path' in locals():
            print(f"\nSafety backup available at: {safety_backup_path}")
            response = input("Restore from safety backup? (yes/no): ")
            if response.lower() in ['yes', 'y']:
                try:
                    shutil.copy2(safety_backup_path, target_db_path)
                    print("✓ Restored from safety backup")
                except Exception as e2:
                    print(f"✗ Failed to restore safety backup: {e2}")

        return False


def restore_latest(db_name: str, create_safety_backup: bool = True) -> bool:
    """
    Restore the most recent backup for a given database.

    Args:
        db_name: Name of database (e.g., "catalog", "training_data")
        create_safety_backup: If True, backup current state before restoring

    Returns:
        True if restoration successful
    """
    backup_dir = Path.home() / ".isbn_lot_optimizer" / "backups"

    if not backup_dir.exists():
        print(f"Error: Backup directory not found: {backup_dir}")
        return False

    # Find most recent backup for this database
    pattern = f"{db_name}_*.db"
    backups = sorted(
        backup_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    if not backups:
        print(f"Error: No backups found for database '{db_name}'")
        print(f"Searched for: {backup_dir}/{pattern}")
        return False

    latest_backup = backups[0]
    print(f"Most recent backup: {latest_backup.name}")

    return restore_database(
        latest_backup,
        create_safety_backup=create_safety_backup
    )


def main():
    parser = argparse.ArgumentParser(
        description="Restore database from backup with safety checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available backups
  %(prog)s --list

  # List backups for specific database
  %(prog)s --list --db-name catalog

  # Restore from specific backup
  %(prog)s --backup backups/catalog_pre-enrichment_20250131_143022.db

  # Restore most recent backup
  %(prog)s --latest --db-name catalog

  # Restore without creating safety backup (not recommended)
  %(prog)s --backup <file> --no-backup
        """
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available backups"
    )
    parser.add_argument(
        "--db-name",
        help="Database name (e.g., 'catalog', 'training_data')"
    )
    parser.add_argument(
        "--backup",
        help="Path to backup file to restore from"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Restore the most recent backup for --db-name"
    )
    parser.add_argument(
        "--target",
        help="Target database path (defaults to inferred from backup name)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating safety backup before restore (not recommended)"
    )

    args = parser.parse_args()

    # Handle --list
    if args.list:
        list_backups(args.db_name)
        return

    # Handle --latest
    if args.latest:
        if not args.db_name:
            parser.error("--latest requires --db-name")

        success = restore_latest(
            args.db_name,
            create_safety_backup=not args.no_backup
        )
        sys.exit(0 if success else 1)

    # Handle --backup
    if args.backup:
        success = restore_database(
            Path(args.backup),
            target_db_path=Path(args.target) if args.target else None,
            create_safety_backup=not args.no_backup
        )
        sys.exit(0 if success else 1)

    # No action specified
    parser.error("Must specify --list, --latest, or --backup")


if __name__ == "__main__":
    main()
