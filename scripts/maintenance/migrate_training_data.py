#!/usr/bin/env python3
"""
Training Data Migration Script
Migrates missing ISBNs from training_data.db to metadata_cache.db
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    print("="*70)
    print("TRAINING DATA MIGRATION SCRIPT")
    print("="*70)
    print(f"Timestamp: {datetime.now()}")
    print()

    # Database paths
    home = Path.home()
    training_db_path = home / ".isbn_lot_optimizer" / "training_data.db"
    metadata_cache_path = home / ".isbn_lot_optimizer" / "metadata_cache.db"

    if not training_db_path.exists():
        print(f"✗ training_data.db not found at: {training_db_path}")
        sys.exit(1)

    if not metadata_cache_path.exists():
        print(f"✗ metadata_cache.db not found at: {metadata_cache_path}")
        sys.exit(1)

    print(f"Source: {training_db_path}")
    print(f"Target: {metadata_cache_path}")
    print()

    # Connect to both databases
    training_conn = sqlite3.connect(str(training_db_path))
    training_conn.row_factory = sqlite3.Row

    cache_conn = sqlite3.connect(str(metadata_cache_path))
    cache_conn.row_factory = sqlite3.Row

    # Find ISBNs in training_data.db but not in metadata_cache.db
    print("Finding ISBNs to migrate...")
    training_cursor = training_conn.cursor()
    training_cursor.execute("SELECT isbn FROM training_books")
    training_isbns = set(row['isbn'] for row in training_cursor.fetchall())
    print(f"  Training ISBNs: {len(training_isbns)}")

    cache_cursor = cache_conn.cursor()
    cache_cursor.execute("SELECT isbn FROM cached_books")
    cache_isbns = set(row['isbn'] for row in cache_cursor.fetchall())
    print(f"  Cache ISBNs: {len(cache_isbns)}")

    missing_isbns = training_isbns - cache_isbns
    print(f"  Missing ISBNs: {len(missing_isbns)}")
    print()

    if len(missing_isbns) == 0:
        print("✓ No ISBNs need migration - already complete!")
        training_conn.close()
        cache_conn.close()
        return

    # Create backup before migration
    backup_path = home / "backups" / "isbn_databases_cleanup_migration" / f"metadata_cache_pre-migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creating backup: {backup_path}")
    import shutil
    shutil.copy2(metadata_cache_path, backup_path)
    print("✓ Backup created")
    print()

    # Migrate each missing ISBN
    print(f"Migrating {len(missing_isbns)} ISBNs...")
    print()

    migrated_count = 0
    failed_count = 0

    for isbn in sorted(missing_isbns):
        try:
            # Fetch full record from training_data.db
            training_cursor.execute("""
                SELECT
                    isbn, title, authors, publication_year,
                    page_count, metadata_json, market_json, bookscouter_json,
                    sold_avg_price, sold_median_price, sold_count,
                    cover_type, signed, printing, source
                FROM training_books
                WHERE isbn = ?
            """, (isbn,))

            row = training_cursor.fetchone()
            if not row:
                print(f"  ✗ {isbn}: Not found in training_data.db")
                failed_count += 1
                continue

            # Parse JSON fields
            metadata_json = json.loads(row['metadata_json']) if row['metadata_json'] else {}
            market_json = json.loads(row['market_json']) if row['market_json'] else {}
            bookscouter_json = json.loads(row['bookscouter_json']) if row['bookscouter_json'] else {}

            # Insert into metadata_cache.db
            # Note: publisher not in training_data.db, set to NULL
            cache_cursor.execute("""
                INSERT INTO cached_books (
                    isbn, title, authors, publisher, publication_year,
                    page_count, source, quality_score,
                    sold_comps_median, sold_comps_count,
                    market_json, bookscouter_json,
                    cover_type, signed, printing,
                    training_quality_score, in_training,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                isbn,
                row['title'],
                row['authors'],
                None,  # publisher not available in training_data.db
                row['publication_year'],
                row['page_count'],
                row['source'] if row['source'] else 'training_data_migration',
                0.5,  # Default quality score
                row['sold_median_price'],
                row['sold_count'],
                row['market_json'],
                row['bookscouter_json'],
                row['cover_type'],
                row['signed'] if row['signed'] is not None else 0,
                row['printing'],
                0.6,  # Training quality score (assuming good quality from legacy DB)
                1,    # Mark as training-eligible
            ))

            cache_conn.commit()
            migrated_count += 1
            print(f"  ✓ {isbn}: {row['title'][:50] if row['title'] else 'No title'}")

        except Exception as e:
            print(f"  ✗ {isbn}: Migration failed - {str(e)}")
            failed_count += 1
            continue

    print()
    print("="*70)
    print("MIGRATION SUMMARY")
    print("="*70)
    print(f"Migrated successfully: {migrated_count}")
    print(f"Failed: {failed_count}")
    print()

    if migrated_count > 0:
        print("✓ Migration completed successfully!")
        print()
        print("Verifying migration...")

        # Re-check missing ISBNs
        cache_cursor.execute("SELECT isbn FROM cached_books")
        new_cache_isbns = set(row['isbn'] for row in cache_cursor.fetchall())
        remaining_missing = training_isbns - new_cache_isbns

        print(f"  ISBNs still missing: {len(remaining_missing)}")
        if len(remaining_missing) == 0:
            print("  ✓ All ISBNs successfully migrated!")
        else:
            print(f"  ⚠ {len(remaining_missing)} ISBNs still missing:")
            for isbn in sorted(remaining_missing):
                print(f"    - {isbn}")

    print()
    print("Backup location: {backup_path}")

    # Close connections
    training_conn.close()
    cache_conn.close()

if __name__ == "__main__":
    main()
