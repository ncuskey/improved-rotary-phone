#!/usr/bin/env python3
"""Migration script to create ebay_products table for ePID caching.

This table stores eBay Product IDs (ePIDs) discovered during keyword analysis,
allowing us to use product-based listings with auto-populated Item Specifics.

Usage:
    python3 scripts/migrate_ebay_products.py
"""

import sqlite3
import sys
from pathlib import Path


def migrate(db_path: Path) -> None:
    """Create ebay_products table if it doesn't exist."""

    print(f"Migrating database: {db_path}")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ebay_products'"
        )
        if cursor.fetchone():
            print("✓ Table 'ebay_products' already exists")
            return

        # Create ebay_products table
        print("Creating 'ebay_products' table...")
        cursor.execute("""
            CREATE TABLE ebay_products (
                isbn TEXT PRIMARY KEY,
                epid TEXT NOT NULL,
                product_title TEXT,
                product_url TEXT,
                category_id TEXT,
                discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_verified TEXT,
                times_used INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                notes TEXT
            )
        """)

        # Create index on epid for reverse lookups
        print("Creating index on epid...")
        cursor.execute("""
            CREATE INDEX idx_ebay_products_epid
            ON ebay_products(epid)
        """)

        # Create index on discovered_at for cleanup queries
        cursor.execute("""
            CREATE INDEX idx_ebay_products_discovered_at
            ON ebay_products(discovered_at DESC)
        """)

        conn.commit()

        print("✓ Table 'ebay_products' created successfully")
        print("✓ Indexes created successfully")
        print()
        print("Table schema:")
        print("  - isbn: TEXT PRIMARY KEY (ISBN-13)")
        print("  - epid: TEXT NOT NULL (eBay Product ID)")
        print("  - product_title: TEXT (Product title from eBay)")
        print("  - product_url: TEXT (URL to product page)")
        print("  - category_id: TEXT (eBay category ID)")
        print("  - discovered_at: TEXT (ISO 8601 timestamp)")
        print("  - last_verified: TEXT (Last time ePID was verified)")
        print("  - times_used: INTEGER (How many times used in listings)")
        print("  - success_count: INTEGER (Successful listing creations)")
        print("  - failure_count: INTEGER (Failed listing creations)")
        print("  - notes: TEXT (Any notes about this ePID)")

    except sqlite3.Error as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

    print("=" * 70)
    print("✓ Migration completed successfully")


def main():
    """Run migration on default database."""

    # Default database path
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    # Allow custom path via command line
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        print("  Create the database first or provide a valid path:")
        print(f"    python3 {sys.argv[0]} <db_path>")
        sys.exit(1)

    try:
        migrate(db_path)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
