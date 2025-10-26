#!/usr/bin/env python3
"""Migration script to add ebay_listings table for tracking eBay listings and sales.

This table enables:
1. Tracking listings created from the app
2. Recording when items sell on eBay
3. Calculating actual TTS (time-to-sell) values
4. Comparing estimated vs actual sale prices
5. Building training data to improve model accuracy

Usage:
    python3 scripts/migrate_ebay_listings_table.py
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def migrate_ebay_listings_table(db_path: Path) -> None:
    """Add ebay_listings table to the database."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ebay_listings'
        """)

        if cursor.fetchone():
            print("✓ ebay_listings table already exists")
            return

        print("Creating ebay_listings table...")

        # Create ebay_listings table
        cursor.execute("""
            CREATE TABLE ebay_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- Item reference (exactly one must be set)
                isbn TEXT,
                lot_id INTEGER,

                -- eBay identifiers
                ebay_listing_id TEXT,
                ebay_offer_id TEXT,
                sku TEXT,

                -- Listing content
                title TEXT NOT NULL,
                description TEXT,
                photos TEXT,  -- JSON array of photo URLs/paths

                -- Pricing
                listing_price REAL NOT NULL,
                estimated_price REAL,  -- Our estimate at time of listing
                cost_basis REAL,  -- What we paid for it

                -- Listing details
                quantity INTEGER DEFAULT 1,
                condition TEXT,  -- Good, Very Good, Like New, etc.
                format TEXT,  -- Hardcover, Paperback, etc.

                -- Status tracking
                status TEXT NOT NULL DEFAULT 'draft',  -- draft, active, sold, ended, error
                error_message TEXT,

                -- Timestamps
                listed_at TEXT,  -- When posted to eBay
                sold_at TEXT,  -- When sold
                ended_at TEXT,  -- When ended (if not sold)

                -- Sales data (populated when sold)
                final_sale_price REAL,  -- Actual sale price
                actual_tts_days INTEGER,  -- Calculated: sold_at - listed_at
                buyer_location TEXT,  -- For geographic insights

                -- Learning metrics
                price_accuracy REAL,  -- final_sale_price / estimated_price
                tts_accuracy REAL,  -- actual_tts_days / estimated_tts_days
                estimated_tts_days INTEGER,  -- Our TTS estimate at listing time

                -- AI generation metadata
                ai_generated INTEGER DEFAULT 0,  -- 1 if title/desc were AI-generated
                ai_model TEXT,  -- Model used (e.g., "llama3.1:8b")
                user_edited INTEGER DEFAULT 0,  -- 1 if user edited AI content

                -- Standard timestamps
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                -- Foreign key constraints
                FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
                FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE,

                -- Ensure either isbn or lot_id is set (but not both)
                CHECK ((isbn IS NOT NULL AND lot_id IS NULL) OR (isbn IS NULL AND lot_id IS NOT NULL)),

                -- Ensure status is valid
                CHECK (status IN ('draft', 'active', 'sold', 'ended', 'error'))
            )
        """)

        # Create indexes for common queries
        print("Creating indexes...")

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_isbn ON ebay_listings(isbn)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_lot_id ON ebay_listings(lot_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_status ON ebay_listings(status)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_listed_at ON ebay_listings(listed_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_sold_at ON ebay_listings(sold_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_ebay_listing_id ON ebay_listings(ebay_listing_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_listings_sku ON ebay_listings(sku)
        """)

        conn.commit()
        print("✓ ebay_listings table created successfully")
        print("✓ Created 7 indexes for efficient querying")

        # Print schema info
        cursor.execute("PRAGMA table_info(ebay_listings)")
        columns = cursor.fetchall()
        print(f"\n✓ Table has {len(columns)} columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

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

    print(f"Running migration on database: {db_path}")
    print("=" * 70)

    migrate_ebay_listings_table(db_path)

    print("=" * 70)
    print("✓ Migration complete!")
    print("\nNext steps:")
    print("  1. Install Llama 3.1 8B: ollama pull llama3.1:8b")
    print("  2. Create listing generator service")
    print("  3. Test AI generation with sample book")


if __name__ == '__main__':
    main()
