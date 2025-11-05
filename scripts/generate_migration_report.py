#!/usr/bin/env python3
"""
Generate migration report showing current state of databases.
Analyzes catalog.db and metadata_cache.db before migration.
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

def count_table_rows(db_path: str, table_name: str) -> int:
    """Count rows in a table."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.OperationalError:
        return 0


def get_table_names(db_path: str) -> list:
    """Get all table names in database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except:
        return []


def get_db_size(db_path: str) -> str:
    """Get database file size."""
    try:
        size_bytes = Path(db_path).stat().st_size
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    except:
        return "N/A"


def main():
    catalog_db = "/Users/nickcuskey/ISBN/catalog.db"
    metadata_cache_db = "/Users/nickcuskey/ISBN/metadata_cache.db"
    report_path = Path("/Users/nickcuskey/ISBN/backups/migration_20251105/migration_report.txt")

    report = []
    report.append("=" * 80)
    report.append("DATABASE MIGRATION REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Purpose: Migrate catalog.db → metadata_cache.db (unified training DB)")
    report.append("")

    # Analyze catalog.db
    report.append("─" * 80)
    report.append("CATALOG.DB (Source Database)")
    report.append("─" * 80)
    report.append(f"Path: {catalog_db}")
    report.append(f"Size: {get_db_size(catalog_db)}")
    report.append("")

    catalog_tables = get_table_names(catalog_db)
    report.append(f"Tables found: {len(catalog_tables)}")
    for table in catalog_tables:
        count = count_table_rows(catalog_db, table)
        report.append(f"  • {table}: {count:,} rows")
    report.append("")

    # Analyze metadata_cache.db
    report.append("─" * 80)
    report.append("METADATA_CACHE.DB (Target Database)")
    report.append("─" * 80)
    report.append(f"Path: {metadata_cache_db}")
    report.append(f"Size: {get_db_size(metadata_cache_db)}")
    report.append("")

    cache_tables = get_table_names(metadata_cache_db)
    report.append(f"Tables found: {len(cache_tables)}")
    for table in cache_tables:
        count = count_table_rows(metadata_cache_db, table)
        report.append(f"  • {table}: {count:,} rows")
    report.append("")

    # Migration Plan
    report.append("─" * 80)
    report.append("MIGRATION PLAN")
    report.append("─" * 80)

    catalog_books = count_table_rows(catalog_db, "books")
    cache_books = count_table_rows(metadata_cache_db, "cached_books")

    report.append(f"Source records (catalog.db books): {catalog_books:,}")
    report.append(f"Existing records (metadata_cache.db cached_books): {cache_books:,}")
    report.append(f"Estimated total after migration: ~{catalog_books + cache_books:,}")
    report.append("")
    report.append("Steps:")
    report.append("  1. Expand metadata_cache.db schema (add market data columns)")
    report.append("  2. Migrate all books from catalog.db → metadata_cache.db")
    report.append("  3. Calculate training quality scores for each book")
    report.append("  4. Update unified_index.db with new ISBNs")
    report.append("  5. Delete catalog.db and create fresh")
    report.append("  6. Implement organic growth system")
    report.append("")

    # Quality Thresholds
    report.append("─" * 80)
    report.append("QUALITY GATES FOR TRAINING")
    report.append("─" * 80)
    report.append("Books must meet these criteria to be in_training=1:")
    report.append("  • sold_comps_count >= 8 (sufficient eBay comparables)")
    report.append("  • sold_comps_median >= $5 (minimum price threshold)")
    report.append("  • training_quality_score >= 0.6 (composite score)")
    report.append("")

    # Backup Info
    report.append("─" * 80)
    report.append("BACKUPS CREATED")
    report.append("─" * 80)
    backup_dir = Path("/Users/nickcuskey/ISBN/backups/migration_20251105")
    backups = list(backup_dir.glob("*.backup-*"))
    for backup in sorted(backups):
        size = get_db_size(str(backup))
        report.append(f"  ✅ {backup.name} ({size})")
    report.append("")

    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)

    # Write to file
    report_text = "\n".join(report)
    report_path.write_text(report_text)

    # Also print to console
    print(report_text)
    print()
    print(f"📄 Report saved to: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
