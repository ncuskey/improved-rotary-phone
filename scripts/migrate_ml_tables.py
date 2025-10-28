"""
Database migration: Add ML prediction tables.

Creates tables for:
- price_predictions: Store ML model predictions
- actual_outcomes: Track actual sale outcomes for continuous learning
"""

import sqlite3
import sys
from pathlib import Path


def migrate(db_path: Path) -> None:
    """
    Apply ML tables migration to database.

    Args:
        db_path: Path to catalog.db
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Creating ML prediction tables...")

    # Table 1: price_predictions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            predicted_price REAL,
            confidence REAL,
            prediction_lower REAL,
            prediction_upper REAL,
            model_version TEXT,
            features_json TEXT,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (isbn) REFERENCES books(isbn)
        )
    """)

    # Index for fast ISBN lookup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_predictions_isbn
        ON price_predictions(isbn)
    """)

    # Index for model version tracking
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_predictions_model_version
        ON price_predictions(model_version)
    """)

    print("✓ Created price_predictions table")

    # Table 2: actual_outcomes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actual_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            actual_sold_price REAL,
            sold_at TIMESTAMP,
            condition TEXT,
            listing_duration_days INTEGER,
            source TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (isbn) REFERENCES books(isbn)
        )
    """)

    # Index for ISBN lookup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_actual_outcomes_isbn
        ON actual_outcomes(isbn)
    """)

    # Index for date range queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_actual_outcomes_sold_at
        ON actual_outcomes(sold_at)
    """)

    print("✓ Created actual_outcomes table")

    conn.commit()
    conn.close()

    print("\nMigration complete!")
    print("  - price_predictions: Track ML model predictions")
    print("  - actual_outcomes: Track actual sale outcomes")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate database for ML tables")
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

    migrate(db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
