#!/usr/bin/env python3
"""
Migrate all books from catalog.db to metadata_cache.db (unified training database).

This script syncs all existing catalog books to the training database before
clearing catalog.db. It uses the OrganicGrowthManager to calculate quality
scores and set in_training flags appropriately.
"""

import json
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.organic_growth import OrganicGrowthManager


def migrate_catalog_to_training():
    """Migrate all catalog books to training database."""
    print("=" * 80)
    print("MIGRATING CATALOG.DB TO TRAINING DATABASE")
    print("=" * 80)
    print()

    # Connect to catalog.db
    catalog_db = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    if not catalog_db.exists():
        print(f"❌ ERROR: catalog.db not found at {catalog_db}")
        return 1

    print(f"📖 Reading books from catalog.db...")
    conn = sqlite3.connect(str(catalog_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all books (only columns that exist in catalog.db)
    cursor.execute("""
        SELECT
            isbn, title, authors, publication_year, edition,
            condition, estimated_price, price_reference, rarity,
            probability_label, probability_score, probability_reasons,
            sell_through, ebay_active_count, ebay_sold_count, ebay_currency,
            time_to_sell_days, sold_comps_count, sold_comps_min, sold_comps_median,
            sold_comps_max, sold_comps_is_estimate, sold_comps_source,
            metadata_json, market_json, booksrun_json, bookscouter_json, source_json,
            cover_type, signed, printing,
            market_fetched_at, metadata_fetched_at,
            dust_jacket
        FROM books
    """)

    books = cursor.fetchall()
    conn.close()

    total_books = len(books)
    print(f"   Found {total_books} books to migrate")
    print()

    # Initialize organic growth manager
    print("🌱 Initializing organic growth manager...")
    growth_manager = OrganicGrowthManager()
    print()

    # Migrate each book
    print("📦 Migrating books to training database...")
    print()

    migrated_count = 0
    training_eligible_count = 0
    errors = []

    for i, book in enumerate(books, 1):
        isbn = book['isbn']

        # Convert row to dict
        book_data = dict(book)

        # Parse JSON fields back to dicts for processing
        for json_field in ['metadata_json', 'market_json', 'booksrun_json', 'bookscouter_json', 'source_json']:
            if book_data.get(json_field):
                try:
                    book_data[json_field] = json.loads(book_data[json_field])
                except:
                    book_data[json_field] = {}

        try:
            # Sync to training database
            success = growth_manager.sync_book_to_training_db(book_data)

            if success:
                migrated_count += 1

                # Check if eligible for training
                quality_score = growth_manager.calculate_training_quality_score(book_data)
                is_eligible = growth_manager._is_eligible_for_training(book_data, quality_score)

                if is_eligible:
                    training_eligible_count += 1

                # Progress indicator
                if i % 50 == 0:
                    print(f"   Progress: {i}/{total_books} ({i/total_books*100:.1f}%) - "
                          f"{training_eligible_count} eligible for training")
            else:
                errors.append(isbn)

        except Exception as e:
            errors.append(f"{isbn}: {str(e)}")

    # Final summary
    print()
    print("=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)
    print(f"Total books processed: {total_books}")
    print(f"Successfully migrated: {migrated_count}")
    print(f"Training eligible (in_training=1): {training_eligible_count}")
    print(f"Training percentage: {training_eligible_count/total_books*100:.1f}%")
    print(f"Errors: {len(errors)}")
    print()

    if errors:
        print("⚠️  ERRORS:")
        for error in errors[:10]:  # Show first 10 errors
            print(f"   {error}")
        if len(errors) > 10:
            print(f"   ... and {len(errors) - 10} more")
        print()

    # Show training database stats
    print("📊 TRAINING DATABASE STATISTICS:")
    stats = growth_manager.get_training_stats()
    print(f"   Total books: {stats.get('total_books', 0)}")
    print(f"   Training eligible: {stats.get('training_eligible', 0)}")
    print(f"   Average quality score: {stats.get('avg_quality_score', 0):.2f}")
    print()

    quality_dist = stats.get('quality_distribution', {})
    if quality_dist:
        print("   Quality distribution:")
        for tier, count in quality_dist.items():
            print(f"      {tier}: {count} books")
    print()

    print("✅ All catalog books have been migrated to training database!")
    print("   You can now safely clear catalog.db and rescan your inventory.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(migrate_catalog_to_training())
