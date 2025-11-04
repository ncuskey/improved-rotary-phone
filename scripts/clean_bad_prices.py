#!/usr/bin/env python3
"""
Clean up bad price data in sold_listings table.

Fixes:
1. Prices > $10,000 (likely ISBNs matched as prices)
2. Prices < $0.01 (invalid)
"""

import sqlite3
from pathlib import Path


def clean_bad_prices(db_path: Path = None):
    """Clean up invalid prices in sold_listings table."""
    db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("CLEANING BAD PRICE DATA")
    print("=" * 80)
    print()

    # Check current state
    cursor.execute("SELECT COUNT(*) FROM sold_listings WHERE price IS NOT NULL")
    total_with_price = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sold_listings WHERE price > 10000")
    high_prices = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sold_listings WHERE price < 0.01")
    low_prices = cursor.fetchone()[0]

    print(f"Current state:")
    print(f"  Total listings with price: {total_with_price:,}")
    print(f"  Invalid high prices (> $10,000): {high_prices}")
    print(f"  Invalid low prices (< $0.01): {low_prices}")
    print()

    if high_prices == 0 and low_prices == 0:
        print("No bad prices to clean!")
        conn.close()
        return

    # Show some examples of bad data
    if high_prices > 0:
        print("Examples of high prices (likely ISBNs):")
        cursor.execute("""
            SELECT isbn, title, price
            FROM sold_listings
            WHERE price > 10000
            LIMIT 5
        """)
        for isbn, title, price in cursor.fetchall():
            print(f"  {isbn}: ${price:,.0f} - {title[:60]}")
        print()

    # Clean up bad prices
    print("Cleaning up...")

    cursor.execute("UPDATE sold_listings SET price = NULL WHERE price > 10000 OR price < 0.01")
    cleaned = cursor.rowcount

    conn.commit()

    # Show final state
    cursor.execute("SELECT COUNT(*) FROM sold_listings WHERE price IS NOT NULL")
    final_with_price = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            AVG(price) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price
        FROM sold_listings
        WHERE price IS NOT NULL
    """)
    avg, min_p, max_p = cursor.fetchone()

    print()
    print(f"✓ Cleaned {cleaned} invalid prices")
    print()
    print(f"Final state:")
    print(f"  Valid prices remaining: {final_with_price:,}")
    print(f"  Average price: ${avg:.2f}")
    print(f"  Price range: ${min_p:.2f} - ${max_p:.2f}")
    print()

    conn.close()


if __name__ == '__main__':
    clean_bad_prices()
