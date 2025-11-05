#!/usr/bin/env python3
"""
Migrate incorrectly placed metadata_cache records from catalog.db to metadata_cache.db.

This script:
1. Backs up both databases
2. Identifies ISBNs in catalog.db that aren't in the books table
3. Copies their offers and progress to metadata_cache.db
4. Removes them from catalog.db
"""

import sqlite3
from pathlib import Path
import sys
import os

# Add parent directory to path to import backup function
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.backup_database import backup_database

def get_catalog_db_path():
    return Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

def get_metadata_cache_db_path():
    return Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

def backup_databases():
    """Create backups before migration."""
    catalog_db = get_catalog_db_path()
    metadata_db = get_metadata_cache_db_path()

    print("Creating pre-migration backups...")
    backup_database(catalog_db, reason="pre-migration")
    backup_database(metadata_db, reason="pre-migration")
    print("✅ Backups created")

def get_misplaced_isbns():
    """Get ISBNs in catalog.db that don't belong there."""
    catalog_db = get_catalog_db_path()
    conn = sqlite3.connect(catalog_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT p.isbn
        FROM bookfinder_progress p
        LEFT JOIN books b ON p.isbn = b.isbn
        WHERE b.isbn IS NULL
        ORDER BY p.isbn
    """)

    isbns = [row[0] for row in cursor.fetchall()]
    conn.close()
    return isbns

def migrate_isbn_data(isbn, catalog_conn, metadata_conn):
    """Migrate one ISBN's data from catalog to metadata_cache."""

    # Copy progress record
    catalog_cursor = catalog_conn.cursor()
    metadata_cursor = metadata_conn.cursor()

    catalog_cursor.execute("""
        SELECT isbn, status, offer_count, error_message, scraped_at
        FROM bookfinder_progress
        WHERE isbn = ?
    """, (isbn,))

    progress = catalog_cursor.fetchone()
    if progress:
        metadata_cursor.execute("""
            INSERT OR REPLACE INTO bookfinder_progress
            (isbn, status, offer_count, error_message, scraped_at)
            VALUES (?, ?, ?, ?, ?)
        """, progress)

    # Copy offers
    catalog_cursor.execute("""
        SELECT isbn, vendor, seller, price, shipping, condition, binding,
               title, authors, publisher, is_signed, is_first_edition, is_oldworld,
               description, offer_id, clickout_type, destination, seller_location
        FROM bookfinder_offers
        WHERE isbn = ?
    """, (isbn,))

    offers = catalog_cursor.fetchall()
    for offer in offers:
        metadata_cursor.execute("""
            INSERT INTO bookfinder_offers
            (isbn, vendor, seller, price, shipping, condition, binding,
             title, authors, publisher, is_signed, is_first_edition, is_oldworld,
             description, offer_id, clickout_type, destination, seller_location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, offer)

    return len(offers)

def delete_isbn_from_catalog(isbn, catalog_conn):
    """Remove ISBN data from catalog.db."""
    cursor = catalog_conn.cursor()

    cursor.execute("DELETE FROM bookfinder_progress WHERE isbn = ?", (isbn,))
    cursor.execute("DELETE FROM bookfinder_offers WHERE isbn = ?", (isbn,))

def verify_migration(isbns):
    """Verify migration was successful."""
    catalog_db = get_catalog_db_path()
    metadata_db = get_metadata_cache_db_path()

    print("\n=== Verification ===")

    # Check catalog.db
    catalog_conn = sqlite3.connect(catalog_db)
    cursor = catalog_conn.cursor()
    cursor.execute("""
        SELECT COUNT(DISTINCT p.isbn)
        FROM bookfinder_progress p
        LEFT JOIN books b ON p.isbn = b.isbn
        WHERE b.isbn IS NULL
    """)
    remaining = cursor.fetchone()[0]
    catalog_conn.close()

    # Check metadata_cache.db
    metadata_conn = sqlite3.connect(metadata_db)
    cursor = metadata_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bookfinder_progress")
    metadata_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bookfinder_offers")
    metadata_offers = cursor.fetchone()[0]
    metadata_conn.close()

    print(f"  Catalog.db: {remaining} misplaced ISBNs remaining (should be 0)")
    print(f"  Metadata_cache.db: {metadata_count} ISBNs, {metadata_offers} offers")

    if remaining == 0:
        print("  ✅ Migration successful!")
        return True
    else:
        print(f"  ❌ Migration incomplete: {remaining} ISBNs still misplaced")
        return False

def main():
    print("=" * 80)
    print("MIGRATING METADATA_CACHE RECORDS FROM CATALOG.DB")
    print("=" * 80)
    print()

    # Step 1: Backup
    backup_databases()
    print()

    # Step 2: Identify misplaced ISBNs
    print("Identifying misplaced ISBNs...")
    isbns = get_misplaced_isbns()
    print(f"  Found {len(isbns)} ISBNs to migrate")
    print()

    if len(isbns) == 0:
        print("✅ No migration needed - all ISBNs are in correct database")
        return 0

    # Confirm with user
    response = input(f"Migrate {len(isbns)} ISBNs from catalog.db to metadata_cache.db? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled")
        return 1

    # Step 3: Migrate data
    print("\nMigrating data...")
    catalog_conn = sqlite3.connect(get_catalog_db_path())
    metadata_conn = sqlite3.connect(get_metadata_cache_db_path())

    total_offers = 0
    for i, isbn in enumerate(isbns, 1):
        offers = migrate_isbn_data(isbn, catalog_conn, metadata_conn)
        total_offers += offers

        if i % 100 == 0:
            print(f"  Progress: {i}/{len(isbns)} ISBNs ({i/len(isbns)*100:.1f}%)")

    # Commit metadata_cache changes
    metadata_conn.commit()
    print(f"  ✅ Copied {len(isbns)} ISBNs ({total_offers} offers) to metadata_cache.db")

    # Step 4: Delete from catalog
    print("\nRemoving migrated data from catalog.db...")
    for isbn in isbns:
        delete_isbn_from_catalog(isbn, catalog_conn)

    catalog_conn.commit()
    print(f"  ✅ Removed {len(isbns)} ISBNs from catalog.db")

    # Close connections
    catalog_conn.close()
    metadata_conn.close()

    # Step 5: Verify
    verify_migration(isbns)

    print()
    print("=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)

    return 0

if __name__ == '__main__':
    sys.exit(main())
