#!/usr/bin/env python3
"""
Expand metadata_cache.db schema to include market data for unified training database.

Adds columns for:
- Price estimates and references
- eBay market data (active/sold listings, sell-through)
- Book attributes (signed, printing, cover_type)
- Sold comps statistics
- Training quality tracking
- Market data JSON blobs
"""

import sqlite3
import sys
from pathlib import Path

def expand_schema(db_path: str):
    """Add market data columns to metadata_cache.db."""
    print("=" * 80)
    print("EXPANDING METADATA_CACHE.DB SCHEMA")
    print("=" * 80)
    print(f"Database: {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List of new columns to add
    new_columns = [
        # Price fields
        ("estimated_price", "REAL"),
        ("price_reference", "REAL"),
        ("rarity", "REAL"),

        # Probability/quality fields
        ("probability_label", "TEXT"),  # 'HIGH', 'MEDIUM', 'LOW'
        ("probability_score", "REAL"),  # 0.0 to 1.0

        # eBay market data
        ("sell_through", "REAL"),
        ("ebay_active_count", "INTEGER"),
        ("ebay_sold_count", "INTEGER"),
        ("ebay_currency", "TEXT DEFAULT 'USD'"),

        # Book attributes
        ("cover_type", "TEXT"),  # 'Hardcover', 'Paperback', 'Mass Market'
        ("signed", "INTEGER DEFAULT 0"),  # 1=signed, 0=unsigned
        ("printing", "TEXT"),  # '1st', '2nd', etc.

        # Sold comps statistics
        ("time_to_sell_days", "INTEGER"),
        ("sold_comps_count", "INTEGER"),
        ("sold_comps_min", "REAL"),
        ("sold_comps_median", "REAL"),
        ("sold_comps_max", "REAL"),
        ("sold_comps_is_estimate", "INTEGER DEFAULT 0"),
        ("sold_comps_source", "TEXT"),

        # JSON blobs for rich data
        ("market_json", "TEXT"),  # eBay market data
        ("booksrun_json", "TEXT"),  # BooksRun buyback prices
        ("bookscouter_json", "TEXT"),  # Amazon/BookScouter pricing

        # Training quality tracking
        ("training_quality_score", "REAL DEFAULT 0.0"),  # 0-1 composite score
        ("in_training", "INTEGER DEFAULT 0"),  # Flag for training eligibility

        # Staleness tracking
        ("market_fetched_at", "TEXT"),  # Last eBay market data fetch
        ("metadata_fetched_at", "TEXT"),  # Last metadata refresh
        ("last_enrichment_at", "TEXT"),  # Last enrichment run
    ]

    print("Adding new columns...")
    added_count = 0
    skipped_count = 0

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE cached_books ADD COLUMN {col_name} {col_type}")
            print(f"  ✅ Added: {col_name} ({col_type})")
            added_count += 1
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"  ⏭️  Skipped: {col_name} (already exists)")
                skipped_count += 1
            else:
                print(f"  ❌ Error adding {col_name}: {e}")

    print()
    print("Creating new indexes...")

    indexes = [
        ("idx_training_quality", "cached_books(training_quality_score DESC)"),
        ("idx_in_training", "cached_books(in_training)"),
        ("idx_sold_comps_count", "cached_books(sold_comps_count DESC)"),
        ("idx_sold_comps_median", "cached_books(sold_comps_median DESC)"),
        ("idx_market_fetched", "cached_books(market_fetched_at)"),
        ("idx_cover_type", "cached_books(cover_type)"),
        ("idx_signed", "cached_books(signed)"),
    ]

    for idx_name, idx_def in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            print(f"  ✅ Created index: {idx_name}")
        except sqlite3.OperationalError as e:
            print(f"  ⚠️  Index {idx_name}: {e}")

    conn.commit()

    # Get updated schema
    print()
    print("Verifying schema...")
    cursor.execute("PRAGMA table_info(cached_books)")
    columns = cursor.fetchall()
    print(f"  Total columns in cached_books: {len(columns)}")

    # Get indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='cached_books'")
    indexes = cursor.fetchall()
    print(f"  Total indexes on cached_books: {len(indexes)}")

    conn.close()

    print()
    print("=" * 80)
    print("SCHEMA EXPANSION COMPLETE ✅")
    print("=" * 80)
    print(f"Columns added: {added_count}")
    print(f"Columns skipped (already exist): {skipped_count}")
    print()
    print("metadata_cache.db is now ready as unified training database!")

    return 0


def main():
    # Expand both metadata_cache.db locations
    root_db = "/Users/nickcuskey/ISBN/metadata_cache.db"
    opt_db = "/Users/nickcuskey/ISBN/isbn_lot_optimizer/metadata_cache.db"

    # Expand root db
    if Path(root_db).exists():
        result = expand_schema(root_db)
        if result != 0:
            return result
    else:
        print(f"Creating new database: {root_db}")
        # Database will be created automatically on first connection
        conn = sqlite3.connect(root_db)
        conn.close()
        expand_schema(root_db)

    print()
    print()

    # Expand optimizer db
    if Path(opt_db).exists():
        result = expand_schema(opt_db)
        if result != 0:
            return result
    else:
        print(f"Creating new database: {opt_db}")
        Path(opt_db).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(opt_db)
        conn.close()
        expand_schema(opt_db)

    return 0


if __name__ == "__main__":
    sys.exit(main())
