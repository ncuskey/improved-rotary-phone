#!/usr/bin/env python3
"""
Database migration: Create sold_listings and sold_statistics tables.

This migration creates a unified multi-platform sold listings table to replace
the platform-specific watchcount_sold table.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def migrate_database(db_path: Path):
    """Create sold_listings and sold_statistics tables."""

    print("=" * 80)
    print("DATABASE MIGRATION: Sold Listings Schema")
    print("=" * 80)
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create sold_listings table (unified multi-platform)
    print("1. Creating sold_listings table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            platform TEXT NOT NULL,  -- 'ebay', 'abebooks', 'mercari', 'amazon'

            -- Listing identification
            url TEXT NOT NULL,
            listing_id TEXT,  -- Platform-specific ID extracted from URL

            -- Price data
            price REAL,
            currency TEXT DEFAULT 'USD',

            -- Sale details
            sold_date TEXT,  -- ISO format YYYY-MM-DD
            days_ago INTEGER,

            -- Listing details
            title TEXT,
            condition TEXT,  -- 'New', 'Like New', 'Very Good', 'Good', 'Acceptable'

            -- Engagement metrics (eBay primarily)
            watchers INTEGER,
            sold_quantity INTEGER DEFAULT 1,

            -- Quality flags
            is_lot INTEGER DEFAULT 0,  -- 1 if multi-book lot detected

            -- Raw data for debugging
            snippet TEXT,  -- Search result snippet
            raw_html_hash TEXT,  -- Hash of scraped HTML (for deduplication)

            -- Metadata
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Unique constraint: same listing across multiple scrapes
            UNIQUE(platform, listing_id)
        )
    """)

    # Indexes for sold_listings
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_isbn
        ON sold_listings(isbn)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_platform
        ON sold_listings(platform)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_isbn_platform
        ON sold_listings(isbn, platform)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_sold_date
        ON sold_listings(sold_date DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_is_lot
        ON sold_listings(is_lot)
    """)

    print("  ✓ sold_listings table created")
    print("  ✓ Indexes created (isbn, platform, sold_date, is_lot)")
    print()

    # 2. Create sold_statistics table (aggregated stats cache)
    print("2. Creating sold_statistics table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            platform TEXT,  -- NULL = all platforms aggregated

            -- Time window for statistics
            days_lookback INTEGER DEFAULT 365,  -- How far back data was collected

            -- Sale counts
            total_sales INTEGER,
            lot_count INTEGER,  -- How many were lot sales (excluded from price stats)
            single_sales INTEGER,  -- Sales of individual books only

            -- Price statistics (excluding lots)
            min_price REAL,
            max_price REAL,
            avg_price REAL,
            median_price REAL,
            std_dev REAL,

            -- Percentiles
            p25_price REAL,  -- 25th percentile
            p75_price REAL,  -- 75th percentile

            -- Sell-through rate (if we have active listing data)
            active_listings INTEGER,
            sell_through_rate REAL,  -- sold / (sold + active)

            -- Sales velocity
            avg_sales_per_month REAL,

            -- Data quality
            data_completeness REAL,  -- % of listings with all key fields

            -- Metadata
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,  -- When to recompute

            UNIQUE(isbn, platform, days_lookback)
        )
    """)

    # Indexes for sold_statistics
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_statistics_isbn
        ON sold_statistics(isbn)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_statistics_expires
        ON sold_statistics(expires_at)
    """)

    print("  ✓ sold_statistics table created")
    print("  ✓ Indexes created (isbn, expires_at)")
    print()

    conn.commit()
    conn.close()

    print("=" * 80)
    print("MIGRATION COMPLETE!")
    print("=" * 80)
    print()
    print("New tables:")
    print("  • sold_listings - Unified multi-platform sold listing data")
    print("  • sold_statistics - Cached aggregated statistics")
    print()
    print("Ready for Phase 3: Platform parser implementation")
    print()


def main():
    """Run migration on catalog.db."""

    # Default database path
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    # Allow custom path via command line
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print(f"Database: {db_path}")
    print()

    migrate_database(db_path)

    return 0


if __name__ == '__main__':
    sys.exit(main())
