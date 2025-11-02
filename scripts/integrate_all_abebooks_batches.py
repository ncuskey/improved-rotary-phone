#!/usr/bin/env python3
"""Integrate all AbeBooks batch files into catalog.db."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

def integrate_batches(start_batch: int = 1, end_batch: int = 20):
    """Integrate AbeBooks data from multiple batch files into catalog.db."""

    # Connect to catalog database
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    conn = sqlite3.connect(catalog_db)
    cursor = conn.cursor()

    # Stats
    total_processed = 0
    total_updated = 0
    total_not_found = 0

    print("🔄 Integrating AbeBooks batch data into catalog.db\n")

    for batch_num in range(start_batch, end_batch + 1):
        batch_file = Path(f"/Users/nickcuskey/ISBN/abebooks_batches/batch_{batch_num}_output.json")

        if not batch_file.exists():
            continue

        print(f"📦 Processing batch {batch_num}...")

        with open(batch_file) as f:
            batch_data = json.load(f)

        batch_updated = 0
        batch_not_found = 0

        for isbn, data in batch_data.items():
            total_processed += 1

            # Extract ML features
            ml_features = data.get('ml_features', {})

            # Check if book exists in catalog
            cursor.execute("SELECT isbn FROM books WHERE isbn = ?", (isbn,))
            if not cursor.fetchone():
                batch_not_found += 1
                total_not_found += 1
                continue

            # Update book with AbeBooks data
            cursor.execute("""
                UPDATE books SET
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
                ml_features.get('abebooks_min_price', 0.0),
                ml_features.get('abebooks_avg_price', 0.0),
                ml_features.get('abebooks_seller_count', 0),
                ml_features.get('abebooks_condition_spread'),
                1 if ml_features.get('abebooks_has_new') else 0,
                1 if ml_features.get('abebooks_has_used') else 0,
                ml_features.get('abebooks_hardcover_premium'),
                data.get('fetched_at', datetime.now().isoformat()),
                isbn
            ))

            batch_updated += 1
            total_updated += 1

        conn.commit()
        print(f"   ✓ Updated: {batch_updated}, Not in catalog: {batch_not_found}")

    conn.close()

    print("\n" + "="*60)
    print("📊 Integration Complete")
    print("="*60)
    print(f"Total ISBNs processed: {total_processed}")
    print(f"Successfully updated:  {total_updated}")
    print(f"Not found in catalog:  {total_not_found}")
    print(f"Success rate:          {total_updated/total_processed*100:.1f}%")
    print()

if __name__ == "__main__":
    integrate_batches(start_batch=1, end_batch=100)
