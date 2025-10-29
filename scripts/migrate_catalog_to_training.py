"""
Migrate books from catalog.db to training_data.db.

Since the POC collector can't fetch fresh eBay data (API/token broker not configured),
this script migrates books that already have good data from your catalog to the
training database for testing the POC architecture.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.training_db import TrainingDataManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_books(limit: int = 50, category: str = 'first_edition_hardcover'):
    """
    Migrate books from catalog to training database.

    Args:
        limit: Maximum number of books to migrate
        category: Collection category for these books
    """
    catalog_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    if not catalog_path.exists():
        logger.error(f"Catalog not found at {catalog_path}")
        return

    # Connect to catalog
    catalog_conn = sqlite3.connect(catalog_path)
    catalog_conn.row_factory = sqlite3.Row
    cursor = catalog_conn.cursor()

    # Initialize training database
    training_db = TrainingDataManager()

    # Query books with good sold comps
    # Lowered threshold to $5+ to include more training data
    query = """
    SELECT
        isbn,
        sold_comps_count,
        sold_comps_median,
        sold_comps_min,
        sold_comps_max,
        cover_type,
        printing,
        signed,
        metadata_json,
        market_json,
        bookscouter_json
    FROM books
    WHERE sold_comps_count >= 8
      AND sold_comps_median >= 5
      AND market_json IS NOT NULL
    ORDER BY sold_comps_count DESC, sold_comps_median DESC
    LIMIT ?
    """

    logger.info("=" * 70)
    logger.info("MIGRATING CATALOG BOOKS TO TRAINING DATABASE")
    logger.info("=" * 70)
    logger.info(f"Target category: {category}")
    logger.info(f"Max books: {limit}")
    logger.info("")

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()

    logger.info(f"Found {len(rows)} candidate books in catalog")
    logger.info("")

    migrated_count = 0
    skipped_count = 0

    for i, row in enumerate(rows, 1):
        isbn = row['isbn']

        # Check if already in training DB or blacklisted
        if training_db.is_blacklisted(isbn):
            logger.info(f"[{i}/{len(rows)}] {isbn}: Skipping (blacklisted)")
            skipped_count += 1
            continue

        try:
            # Extract sold comps data
            sold_count = row['sold_comps_count']
            sold_median = row['sold_comps_median']
            sold_min = row['sold_comps_min']
            sold_max = row['sold_comps_max']

            # Use median as avg (best proxy we have)
            sold_avg_price = sold_median

            # Get JSON blobs
            metadata_json = row['metadata_json'] or '{}'
            market_json = row['market_json'] or '{}'
            bookscouter_json = row['bookscouter_json']

            # Add to training database
            training_db.add_training_book(
                isbn=isbn,
                category=category,
                sold_avg_price=sold_avg_price,
                sold_count=sold_count,
                sold_median_price=sold_median,
                metadata_json=metadata_json,
                market_json=market_json,
                bookscouter_json=bookscouter_json
            )

            migrated_count += 1

            cover = row['cover_type'] or '?'
            printing = row['printing'] or '?'
            signed = '✓' if row['signed'] else '✗'

            logger.info(f"[{i}/{len(rows)}] {isbn}: ✓ Migrated (${sold_median:.2f}, {sold_count} comps, {cover}, {printing}, signed:{signed})")

            # Update target count
            training_db.update_target_count(category)

        except Exception as e:
            logger.error(f"[{i}/{len(rows)}] {isbn}: Failed to migrate: {e}")
            skipped_count += 1

    catalog_conn.close()

    # Final statistics
    logger.info("")
    logger.info("=" * 70)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Successfully migrated: {migrated_count} books")
    logger.info(f"Skipped: {skipped_count} books")
    logger.info("")

    # Database stats
    db_stats = training_db.get_stats()
    logger.info(f"Training database now has {db_stats['total_books']} books")
    logger.info(f"  - Signed books: {db_stats.get('signed_books', 0)}")
    logger.info(f"  - First editions: {db_stats.get('first_editions', 0)}")
    logger.info("")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Migrate catalog books to training database')
    parser.add_argument('--limit', type=int, default=50, help='Max books to migrate (default: 50)')
    parser.add_argument('--category', type=str, default='first_edition_hardcover',
                       help='Category to assign (default: first_edition_hardcover)')

    args = parser.parse_args()

    migrate_books(limit=args.limit, category=args.category)
