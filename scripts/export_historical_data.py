#!/usr/bin/env python3
"""
Export scan_history and lots tables from catalog.db to CSV files.
Part of migration to unified metadata_cache.db system.
"""

import sqlite3
import csv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def export_table_to_csv(db_path: str, table_name: str, output_csv: str):
    """Export a table from SQLite to CSV."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]

        # Get all rows
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # Write to CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)  # Header
            writer.writerows(rows)    # Data

        conn.close()
        return len(rows), columns

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"⚠️  Table {table_name} does not exist in {db_path}")
            return 0, []
        raise


def main():
    catalog_db = Path("/Users/nickcuskey/ISBN/catalog.db")
    backup_dir = Path("/Users/nickcuskey/ISBN/backups/migration_20251105")

    if not catalog_db.exists():
        print(f"❌ ERROR: catalog.db not found at {catalog_db}")
        return 1

    print("=" * 60)
    print("EXPORTING HISTORICAL DATA FROM CATALOG.DB")
    print("=" * 60)
    print()

    # Export scan_history
    print("📋 Exporting scan_history table...")
    scan_csv = backup_dir / "scan_history_export.csv"
    scan_count, scan_cols = export_table_to_csv(
        str(catalog_db),
        "scan_history",
        str(scan_csv)
    )
    print(f"   ✅ Exported {scan_count:,} scan records")
    print(f"   📁 Saved to: {scan_csv}")
    print(f"   📊 Columns: {len(scan_cols)} ({', '.join(scan_cols[:5])}...)")
    print()

    # Export lots
    print("📦 Exporting lots table...")
    lots_csv = backup_dir / "lots_export.csv"
    lots_count, lots_cols = export_table_to_csv(
        str(catalog_db),
        "lots",
        str(lots_csv)
    )
    print(f"   ✅ Exported {lots_count:,} lot records")
    print(f"   📁 Saved to: {lots_csv}")
    print(f"   📊 Columns: {len(lots_cols)} ({', '.join(lots_cols[:5])}...)")
    print()

    print("=" * 60)
    print("EXPORT COMPLETE ✅")
    print("=" * 60)
    print(f"Total records exported: {scan_count + lots_count:,}")
    print(f"Backup directory: {backup_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
