"""
Populate sold_comps fields from existing market data.

Since eBay Marketplace Insights API isn't available, we'll use Track B approach:
estimate sold prices from active listings using conservative heuristic (75% of median).
"""

import sqlite3
import sys
from pathlib import Path


def populate_sold_comps(db_path: Path) -> int:
    """
    Populate sold_comps fields from active market data.

    Args:
        db_path: Path to catalog.db

    Returns:
        Number of books updated
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get books with active market data but missing sold comps
    cursor.execute("""
        SELECT
            isbn,
            json_extract(market_json, '$.active_median_price') as active_median,
            json_extract(market_json, '$.active_count') as active_count
        FROM books
        WHERE market_json IS NOT NULL
          AND json_extract(market_json, '$.active_median_price') IS NOT NULL
          AND CAST(json_extract(market_json, '$.active_median_price') AS REAL) > 0
          AND (sold_comps_median IS NULL OR sold_comps_median = 0)
    """)

    books = cursor.fetchall()
    updated_count = 0

    for isbn, active_median, active_count in books:
        # Conservative estimate: 75% of active median
        # This approximates typical sold/active price ratio from eBay data
        estimated_sold_median = float(active_median) * 0.75
        estimated_sold_min = float(active_median) * 0.65
        estimated_sold_max = float(active_median) * 0.85

        # Update book with estimated sold comps
        cursor.execute("""
            UPDATE books
            SET
                sold_comps_count = ?,
                sold_comps_min = ?,
                sold_comps_median = ?,
                sold_comps_max = ?,
                sold_comps_is_estimate = 1,
                sold_comps_source = 'active_estimate',
                updated_at = CURRENT_TIMESTAMP
            WHERE isbn = ?
        """, (
            int(active_count),
            round(estimated_sold_min, 2),
            round(estimated_sold_median, 2),
            round(estimated_sold_max, 2),
            isbn
        ))

        updated_count += 1

    conn.commit()
    conn.close()

    return updated_count


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate sold comp estimates from active market data"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print("Populating sold comp estimates from active market data...")
    print("Using Track B approach: sold_median = 0.75 × active_median")
    print()

    updated = populate_sold_comps(db_path)

    print(f"\n✓ Updated {updated} books with estimated sold comps")
    print(f"\nNow ready to train ML model:")
    print(f"  python3 scripts/train_price_model.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
