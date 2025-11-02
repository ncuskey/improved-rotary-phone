#!/usr/bin/env python3
"""
Integrate AbeBooks pricing data into catalog.db for ML training.

Takes AbeBooks JSON files and merges them into catalog.db books table.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any
import glob

def load_abebooks_data(batch_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all AbeBooks batch files and merge into single dict."""
    all_data = {}

    batch_files = sorted(glob.glob(str(batch_dir / "batch_*_output.json")))

    for batch_file in batch_files:
        with open(batch_file) as f:
            data = json.load(f)
            all_data.update(data)

    print(f"✓ Loaded {len(all_data)} ISBNs from {len(batch_files)} batch files")
    return all_data

def add_abebooks_columns(conn: sqlite3.Connection):
    """Add AbeBooks columns to books table if they don't exist."""
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(books)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("abebooks_min_price", "REAL"),
        ("abebooks_avg_price", "REAL"),
        ("abebooks_seller_count", "INTEGER"),
        ("abebooks_condition_spread", "REAL"),
        ("abebooks_has_new", "INTEGER"),
        ("abebooks_has_used", "INTEGER"),
        ("abebooks_hardcover_premium", "REAL"),
        ("abebooks_fetched_at", "TEXT"),
    ]

    added = 0
    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE books ADD COLUMN {col_name} {col_type}")
            added += 1

    if added > 0:
        conn.commit()
        print(f"✓ Added {added} new columns to books table")
    else:
        print("✓ AbeBooks columns already exist")

def update_books_with_abebooks(conn: sqlite3.Connection, abebooks_data: Dict[str, Dict[str, Any]]) -> int:
    """Update books table with AbeBooks pricing data."""
    cursor = conn.cursor()

    updated = 0
    skipped = 0

    for isbn, data in abebooks_data.items():
        ml_features = data.get('ml_features', {})
        fetched_at = data.get('fetched_at')

        # Skip if no useful data
        if not ml_features or ml_features.get('abebooks_seller_count', 0) == 0:
            skipped += 1
            continue

        # Update or insert
        cursor.execute("""
            UPDATE books
            SET
                abebooks_min_price = ?,
                abebooks_avg_price = ?,
                abebooks_seller_count = ?,
                abebooks_condition_spread = ?,
                abebooks_has_new = ?,
                abebooks_has_used = ?,
                abebooks_hardcover_premium = ?,
                abebooks_fetched_at = ?
            WHERE isbn = ?
        """, (
            ml_features.get('abebooks_min_price'),
            ml_features.get('abebooks_avg_price'),
            ml_features.get('abebooks_seller_count'),
            ml_features.get('abebooks_condition_spread'),
            1 if ml_features.get('abebooks_has_new') else 0,
            1 if ml_features.get('abebooks_has_used') else 0,
            ml_features.get('abebooks_hardcover_premium'),
            fetched_at,
            isbn,
        ))

        if cursor.rowcount > 0:
            updated += 1

    conn.commit()
    print(f"✓ Updated {updated} books with AbeBooks data")
    if skipped > 0:
        print(f"  (Skipped {skipped} ISBNs with no valid data)")

    return updated

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Integrate AbeBooks data into catalog')
    parser.add_argument(
        '--batch-dir',
        type=str,
        default='abebooks_batches',
        help='Directory containing batch_*_output.json files'
    )
    parser.add_argument(
        '--catalog-db',
        type=str,
        default=str(Path.home() / '.isbn_lot_optimizer' / 'catalog.db'),
        help='Path to catalog.db'
    )

    args = parser.parse_args()

    batch_dir = Path(args.batch_dir)
    catalog_db = Path(args.catalog_db)

    if not batch_dir.exists():
        print(f"Error: Batch directory not found: {batch_dir}")
        return 1

    if not catalog_db.exists():
        print(f"Error: Catalog database not found: {catalog_db}")
        return 1

    print("="*70)
    print("Integrating AbeBooks Data into Catalog")
    print("="*70)
    print()

    # Load AbeBooks data
    print("1. Loading AbeBooks data...")
    abebooks_data = load_abebooks_data(batch_dir)

    # Connect to catalog
    print(f"\n2. Connecting to catalog: {catalog_db}")
    conn = sqlite3.connect(catalog_db)

    # Add columns
    print("\n3. Ensuring AbeBooks columns exist...")
    add_abebooks_columns(conn)

    # Update books
    print("\n4. Updating books with AbeBooks pricing...")
    updated = update_books_with_abebooks(conn, abebooks_data)

    conn.close()

    print("\n" + "="*70)
    print("Integration Complete!")
    print("="*70)
    print(f"✓ {updated} books now have AbeBooks pricing data")
    print(f"✓ Ready for ML training with enhanced features")
    print()
    print("Next step: python3 scripts/train_price_model.py")

    return 0

if __name__ == "__main__":
    sys.exit(main())
