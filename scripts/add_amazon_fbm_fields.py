#!/usr/bin/env python3
"""
Add Amazon FBM (Fulfilled by Merchant) fields to metadata_cache database.

Adds columns to track third-party Amazon seller data separately from FBA.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_metadata_cache_db_path() -> Path:
    """Get path to metadata_cache database."""
    return Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'


def add_fbm_fields():
    """Add Amazon FBM fields to cached_books table."""
    db_path = get_metadata_cache_db_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check which columns already exist
    cursor.execute("PRAGMA table_info(cached_books)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    fields_to_add = {
        'amazon_fbm_count': 'INTEGER',          # Number of FBM sellers
        'amazon_fbm_min': 'REAL',               # Lowest FBM price
        'amazon_fbm_median': 'REAL',            # Median FBM price
        'amazon_fbm_max': 'REAL',               # Highest FBM price
        'amazon_fbm_avg_rating': 'REAL',        # Average seller rating
        'amazon_fbm_collected_at': 'TEXT',      # Collection timestamp
    }

    added_count = 0
    for field_name, field_type in fields_to_add.items():
        if field_name not in existing_columns:
            print(f"Adding column: {field_name} ({field_type})")
            cursor.execute(f"ALTER TABLE cached_books ADD COLUMN {field_name} {field_type}")
            added_count += 1
        else:
            print(f"Column already exists: {field_name}")

    # Create index on amazon_fbm_median for faster queries
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_amazon_fbm_median
            ON cached_books(amazon_fbm_median)
        """)
        print("Created index: idx_amazon_fbm_median")
    except sqlite3.OperationalError:
        print("Index already exists: idx_amazon_fbm_median")

    # Create index on amazon_fbm_count
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_amazon_fbm_count
            ON cached_books(amazon_fbm_count)
        """)
        print("Created index: idx_amazon_fbm_count")
    except sqlite3.OperationalError:
        print("Index already exists: idx_amazon_fbm_count")

    conn.commit()
    conn.close()

    print(f"\n✓ Migration complete: Added {added_count} new columns")
    return True


if __name__ == "__main__":
    success = add_fbm_fields()
    sys.exit(0 if success else 1)
