#!/usr/bin/env python3
"""
Add feature columns to sold_listings table for tracking book attributes.

Adds columns for: signed, edition, printing, cover_type, dust_jacket, etc.
"""

import sys
import sqlite3
from pathlib import Path

def add_feature_columns(db_path: Path):
    """Add feature columns to sold_listings table."""

    print("Adding feature columns to sold_listings table...")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Columns to add
    columns = [
        ("signed", "INTEGER DEFAULT 0", "Whether book is signed/autographed"),
        ("edition", "TEXT", "Edition info (1st, 2nd, Limited, etc.)"),
        ("printing", "TEXT", "Printing info (1st printing, 2nd printing, etc.)"),
        ("cover_type", "TEXT", "Hardcover, Paperback, Mass Market"),
        ("dust_jacket", "INTEGER DEFAULT 0", "Whether has dust jacket"),
        ("features_json", "TEXT", "JSON of all detected features"),
    ]

    for col_name, col_type, description in columns:
        try:
            # Check if column exists
            cursor.execute(f"PRAGMA table_info(sold_listings)")
            existing_cols = [row[1] for row in cursor.fetchall()]

            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE sold_listings ADD COLUMN {col_name} {col_type}")
                print(f"  ✓ Added column: {col_name} - {description}")
            else:
                print(f"  • Column exists: {col_name}")

        except Exception as e:
            print(f"  ✗ Error adding {col_name}: {e}")

    conn.commit()
    conn.close()

    print()
    print("Feature columns added successfully!")
    print()


if __name__ == "__main__":
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    add_feature_columns(db_path)
