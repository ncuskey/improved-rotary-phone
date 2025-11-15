#!/usr/bin/env python3
"""
Import AbeBooks enrichment data from Decodo Core bulk collection into metadata_cache.db.

Stores rich marketplace features from direct AbeBooks scraping:
- Price statistics (min/max/avg/median)
- Market depth (offer count, condition spread)
- Binding analysis (hardcover premium)
- Condition flags (has_new, has_used)

Usage:
    python3 scripts/import_abebooks_enrichment.py /path/to/abebooks_results.json
    python3 scripts/import_abebooks_enrichment.py --test  # Test with sample data
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_metadata_cache_db() -> Path:
    """Get path to metadata_cache database."""
    return Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'


def add_abebooks_columns(db_path: Path):
    """
    Add AbeBooks enrichment columns to cached_books table.

    Schema mirrors amazon_fbm_* and sold_comps_* patterns.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(cached_books)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        "abebooks_enr_count INTEGER DEFAULT 0",           # Number of offers
        "abebooks_enr_min REAL",                          # Minimum price
        "abebooks_enr_median REAL",                       # Median price (best predictor)
        "abebooks_enr_avg REAL",                          # Average price
        "abebooks_enr_max REAL",                          # Maximum price
        "abebooks_enr_spread REAL",                       # Price spread (max - min)
        "abebooks_enr_has_new INTEGER DEFAULT 0",         # Has new condition offers
        "abebooks_enr_has_used INTEGER DEFAULT 0",        # Has used condition offers
        "abebooks_enr_hc_premium REAL",                   # Hardcover premium over softcover
        "abebooks_enr_collected_at TEXT",                 # Collection timestamp
    ]

    for column_def in columns_to_add:
        column_name = column_def.split()[0]
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE cached_books ADD COLUMN {column_def}")
                print(f"✓ Added column: {column_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

    conn.commit()
    conn.close()
    print("✓ Schema updated successfully")


def import_abebooks_data(json_file: Path, db_path: Path):
    """
    Import AbeBooks enrichment data from JSON file into database.

    Args:
        json_file: Path to abebooks_results_*.json file from bulk collection
        db_path: Path to metadata_cache.db
    """
    # Load JSON data
    print(f"Loading data from: {json_file}")
    with open(json_file) as f:
        data = json.load(f)

    print(f"✓ Loaded data for {len(data)} ISBNs")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Import data
    imported = 0
    skipped = 0
    errors = 0

    for isbn, abebooks_data in data.items():
        try:
            # Extract ML features
            ml_features = abebooks_data.get('ml_features', {})
            stats = abebooks_data.get('stats', {})

            # Skip if no offers
            if stats.get('count', 0) == 0:
                skipped += 1
                continue

            # Update cached_books with enrichment data
            cursor.execute("""
                UPDATE cached_books
                SET
                    abebooks_enr_count = ?,
                    abebooks_enr_min = ?,
                    abebooks_enr_median = ?,
                    abebooks_enr_avg = ?,
                    abebooks_enr_max = ?,
                    abebooks_enr_spread = ?,
                    abebooks_enr_has_new = ?,
                    abebooks_enr_has_used = ?,
                    abebooks_enr_hc_premium = ?,
                    abebooks_enr_collected_at = ?
                WHERE isbn = ?
            """, (
                stats.get('count', 0),
                stats.get('min_price'),
                stats.get('median_price'),
                stats.get('avg_price'),
                stats.get('max_price'),
                ml_features.get('abebooks_condition_spread'),
                1 if ml_features.get('abebooks_has_new') else 0,
                1 if ml_features.get('abebooks_has_used') else 0,
                ml_features.get('abebooks_hardcover_premium'),
                abebooks_data.get('fetched_at', datetime.now().isoformat()),
                isbn
            ))

            if cursor.rowcount > 0:
                imported += 1
            else:
                # ISBN not in cached_books, skip
                skipped += 1

        except Exception as e:
            print(f"❌ Error importing ISBN {isbn}: {e}")
            errors += 1

    conn.commit()
    conn.close()

    # Print summary
    print()
    print("=" * 80)
    print("IMPORT SUMMARY")
    print("=" * 80)
    print(f"Total ISBNs in file:  {len(data)}")
    print(f"  ✓ Imported:         {imported}")
    print(f"  ⚠️  Skipped:          {skipped}")
    print(f"  ❌ Errors:           {errors}")
    print("=" * 80)

    return imported, skipped, errors


def test_import():
    """Test import with sample test data."""
    test_json = Path("/tmp/test_abebooks_results.json")

    if not test_json.exists():
        print(f"❌ Error: Test file not found: {test_json}")
        print("Run: PYTHONPATH=/Users/nickcuskey/ISBN ./.venv/bin/python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/test_abebooks_isbns.txt")
        return 1

    db_path = get_metadata_cache_db()

    print("Testing AbeBooks enrichment import")
    print("-" * 80)

    # Add columns
    add_abebooks_columns(db_path)
    print()

    # Import data
    imported, skipped, errors = import_abebooks_data(test_json, db_path)

    if imported > 0:
        print()
        print("✓ Test import successful!")
        print()
        print("Sample enriched data:")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT isbn, abebooks_enr_count, abebooks_enr_min, abebooks_enr_median,
                   abebooks_enr_max, abebooks_enr_spread
            FROM cached_books
            WHERE abebooks_enr_count > 0
            LIMIT 3
        """)
        for row in cursor.fetchall():
            isbn, count, min_p, median_p, max_p, spread = row
            print(f"  {isbn}: {count} offers, ${min_p:.2f}-${max_p:.2f}, median ${median_p:.2f}, spread ${spread:.2f}")
        conn.close()

    return 0 if errors == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Import AbeBooks enrichment data into metadata_cache.db"
    )

    parser.add_argument(
        "json_file",
        nargs="?",
        type=Path,
        help="Path to abebooks_results_*.json file"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test import with /tmp/test_abebooks_results.json"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=get_metadata_cache_db(),
        help="Path to metadata_cache.db (default: ~/.isbn_lot_optimizer/metadata_cache.db)"
    )

    args = parser.parse_args()

    # Test mode
    if args.test:
        return test_import()

    # Require JSON file
    if not args.json_file:
        parser.print_help()
        return 1

    if not args.json_file.exists():
        print(f"❌ Error: File not found: {args.json_file}")
        return 1

    # Add schema columns
    print("Updating database schema...")
    add_abebooks_columns(args.db)
    print()

    # Import data
    print("Importing AbeBooks enrichment data...")
    imported, skipped, errors = import_abebooks_data(args.json_file, args.db)

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
