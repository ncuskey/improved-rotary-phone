#!/usr/bin/env python3
"""
Database migration to add lot pricing fields to existing catalog databases.

This migration adds the following columns to the lots table:
- lot_market_value: Market-based pricing from eBay lot comps
- lot_optimal_size: Optimal lot size identified from market analysis
- lot_per_book_price: Per-book price at optimal lot size
- lot_comps_count: Number of comparable lot listings found
- use_lot_pricing: Boolean flag indicating whether lot pricing is used

Run this migration ONCE on existing databases to add the new columns.
New databases will have these columns automatically via the CREATE TABLE schema.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: Path) -> None:
    """Add lot pricing columns to an existing database."""
    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if migration is needed
    cursor.execute("PRAGMA table_info(lots)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "lot_market_value": "REAL",
        "lot_optimal_size": "INTEGER",
        "lot_per_book_price": "REAL",
        "lot_comps_count": "INTEGER",
        "use_lot_pricing": "INTEGER DEFAULT 0",
    }

    migrations_needed = []
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            migrations_needed.append((col_name, col_type))

    if not migrations_needed:
        print(f"✓ Database already migrated: {db_path}")
        conn.close()
        return

    print(f"→ Migrating database: {db_path}")
    print(f"  Adding {len(migrations_needed)} columns...")

    try:
        for col_name, col_type in migrations_needed:
            sql = f"ALTER TABLE lots ADD COLUMN {col_name} {col_type}"
            print(f"  + {col_name} ({col_type})")
            cursor.execute(sql)

        conn.commit()
        print(f"✓ Migration successful: {db_path}")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


def main():
    # Default database path
    default_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if len(sys.argv) > 1:
        db_paths = [Path(arg) for arg in sys.argv[1:]]
    else:
        db_paths = [default_db]

    print("=" * 60)
    print("Lot Pricing Fields Migration")
    print("=" * 60)
    print()

    for db_path in db_paths:
        try:
            migrate_database(db_path)
        except Exception as e:
            print(f"✗ Error migrating {db_path}: {e}")
            sys.exit(1)
        print()

    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
