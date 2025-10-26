#!/usr/bin/env python3
"""Migration script to add keyword scoring columns to ebay_listings table.

This migration adds support for SEO-optimized title generation with keyword ranking:
1. title_score: Combined SEO score of the title (sum of keyword scores)
2. keyword_scores: JSON array of top keywords with their scores, frequencies, and prices

These columns enable:
- Tracking effectiveness of SEO-optimized titles
- A/B testing standard vs SEO titles
- Analysis of which keywords correlate with faster sales
- Continuous improvement of keyword ranking algorithm

Usage:
    python3 scripts/migrate_keyword_scores.py
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def migrate_keyword_scores(db_path: Path) -> None:
    """Add title_score and keyword_scores columns to ebay_listings table."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ebay_listings'
        """)

        if not cursor.fetchone():
            print("✗ ebay_listings table does not exist")
            print("  Run scripts/migrate_ebay_listings_table.py first")
            sys.exit(1)

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(ebay_listings)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'title_score' in columns and 'keyword_scores' in columns:
            print("✓ Keyword scoring columns already exist")
            return

        print("Adding keyword scoring columns to ebay_listings table...")

        # Add title_score column
        if 'title_score' not in columns:
            cursor.execute("""
                ALTER TABLE ebay_listings
                ADD COLUMN title_score REAL
            """)
            print("  ✓ Added title_score column (REAL)")

        # Add keyword_scores column
        if 'keyword_scores' not in columns:
            cursor.execute("""
                ALTER TABLE ebay_listings
                ADD COLUMN keyword_scores TEXT
            """)
            print("  ✓ Added keyword_scores column (TEXT/JSON)")

        # Create index on title_score for performance analysis
        if 'title_score' in columns or 'title_score' not in columns:  # Will exist after ALTER
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ebay_listings_title_score
                    ON ebay_listings(title_score DESC)
                """)
                print("  ✓ Created index on title_score")
            except Exception as e:
                print(f"  Note: Index may already exist: {e}")

        conn.commit()
        print("\n✓ Migration successful!")

        # Show updated schema
        cursor.execute("PRAGMA table_info(ebay_listings)")
        columns = cursor.fetchall()
        print(f"\n✓ Table now has {len(columns)} columns")

        # Show example of what gets stored
        print("\nExample keyword_scores JSON format:")
        print("""
[
  {
    "word": "fantasy",
    "score": 8.7,
    "frequency": 42,
    "avg_price": 15.99
  },
  {
    "word": "martin",
    "score": 8.2,
    "frequency": 38,
    "avg_price": 16.50
  },
  ...
]
        """)

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise

    finally:
        conn.close()


def main():
    """Run the migration."""

    # Use standard database path
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    if not db_path.exists():
        print(f"✗ Database not found at {db_path}")
        print("  Please ensure the database exists before running migration")
        sys.exit(1)

    print("=" * 70)
    print("Keyword Scoring Migration")
    print("=" * 70)
    print(f"Database: {db_path}\n")

    migrate_keyword_scores(db_path)

    print("\n" + "=" * 70)
    print("Next steps:")
    print("  1. Use keyword analyzer: python -m isbn_lot_optimizer.keyword_analyzer <isbn>")
    print("  2. Create listing with SEO: use_seo_optimization=True")
    print("  3. Compare title_score values to measure SEO effectiveness")
    print("=" * 70)


if __name__ == '__main__':
    main()
