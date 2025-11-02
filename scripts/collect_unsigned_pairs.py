"""
Collect unsigned counterparts for signed book collection.

This script collects eBay sold comps for the SAME ISBNs that we've already
collected signed data for, but this time filtering OUT signed/autographed copies.

This creates paired data for A/B testing the signature premium.

Usage:
    python3 scripts/collect_unsigned_pairs.py --signed-db training_data.db --limit 30
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value.strip('"').strip("'")

from isbn_lot_optimizer.training_db import TrainingDataManager
from shared.ebay_sold_comps import EbaySoldComps
from shared.metadata import fetch_metadata, create_http_session
from shared.utils import normalise_isbn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnsignedPairCollector:
    """
    Collects unsigned counterparts for signed books.

    For each ISBN that we've collected signed data for, this collector
    fetches unsigned sold comps to create paired data for A/B testing.
    """

    def __init__(self, signed_db_path: Path, unsigned_db_path: Path):
        """
        Initialize unsigned pair collector.

        Args:
            signed_db_path: Path to training_data.db with signed books
            unsigned_db_path: Path to store unsigned counterparts
        """
        self.signed_db = TrainingDataManager(signed_db_path)
        self.unsigned_db = TrainingDataManager(unsigned_db_path)
        self.ebay = EbaySoldComps()
        self.session = create_http_session()

        # Stats
        self.stats = {
            'total_signed': 0,
            'collected': 0,
            'insufficient_comps': 0,
            'failed': 0
        }

    def get_signed_isbns(self, limit: Optional[int] = None) -> List[str]:
        """
        Get ISBNs from signed book database.

        Args:
            limit: Maximum number of ISBNs to return

        Returns:
            List of ISBNs
        """
        # Query signed database for ISBNs
        import sqlite3
        conn = sqlite3.connect(self.signed_db.db_path)
        cursor = conn.cursor()

        query = "SELECT isbn FROM training_books ORDER BY collected_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        isbns = [row[0] for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Found {len(isbns)} signed books to match")
        return isbns

    def collect_unsigned_comp(self, isbn: str) -> Optional[Dict]:
        """
        Collect unsigned sold comps for an ISBN.

        Args:
            isbn: ISBN to collect

        Returns:
            Dict with unsigned sold comp data, or None if insufficient comps
        """
        try:
            # Fetch unsigned comps (include_signed=False)
            result = self.ebay.get_sold_comps(
                gtin=isbn,
                fallback_to_estimate=False,
                max_samples=10,
                include_signed=False  # KEY: Filter OUT signed copies
            )

            if not result:
                logger.warning(f"  {isbn}: No unsigned comps found")
                return None

            if result['count'] < 5:
                logger.warning(f"  {isbn}: Insufficient unsigned comps ({result['count']})")
                return None

            logger.info(f"  {isbn}: {result['count']} unsigned sold comps found")

            # Fetch metadata (reuse from cache if possible)
            metadata = fetch_metadata(isbn, session=self.session)

            return {
                'isbn': isbn,
                'ebay_data': result,
                'metadata': metadata,
                'collected_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"  {isbn}: Error collecting unsigned comps: {e}")
            return None

    def collect_all_pairs(self, limit: Optional[int] = None):
        """
        Collect unsigned counterparts for all signed books.

        Args:
            limit: Maximum number of pairs to collect
        """
        logger.info("=" * 70)
        logger.info("UNSIGNED COUNTERPART COLLECTION")
        logger.info("=" * 70)
        logger.info("")

        # Get signed ISBNs
        signed_isbns = self.get_signed_isbns(limit=limit)
        self.stats['total_signed'] = len(signed_isbns)

        logger.info(f"Collecting unsigned counterparts for {len(signed_isbns)} signed books")
        logger.info("")

        # Collect unsigned comps for each
        for i, isbn in enumerate(signed_isbns, 1):
            logger.info(f"[{i}/{len(signed_isbns)}] Processing {isbn}")

            # Check if already collected
            try:
                import sqlite3
                conn = sqlite3.connect(self.unsigned_db.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM training_books WHERE isbn = ?", (isbn,))
                exists = cursor.fetchone()[0] > 0
                conn.close()

                if exists:
                    logger.info(f"  {isbn}: Already collected (skipping)")
                    self.stats['collected'] += 1
                    continue
            except Exception:
                pass  # DB might not exist yet, proceed with collection

            # Collect unsigned comps
            data = self.collect_unsigned_comp(isbn)

            if data:
                # Store in unsigned database
                self.unsigned_db.store_book(
                    isbn=isbn,
                    ebay_data=data['ebay_data'],
                    metadata=data['metadata'],
                    amazon_data=None  # Not needed for comparison
                )
                logger.info(f"  {isbn}: ✓ Stored in unsigned database")
                self.stats['collected'] += 1
            elif data is None and 'Insufficient' in str(data):
                self.stats['insufficient_comps'] += 1
            else:
                self.stats['failed'] += 1

            # Rate limit
            time.sleep(1)

            # Progress update every 10 books
            if i % 10 == 0:
                logger.info("")
                logger.info(f"Progress: {self.stats['collected']}/{len(signed_isbns)} pairs collected")
                logger.info("")

        # Final stats
        logger.info("")
        logger.info("=" * 70)
        logger.info("COLLECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Successfully collected: {self.stats['collected']} unsigned books")
        logger.info(f"Insufficient comps: {self.stats['insufficient_comps']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info("")

        # Show paired data stats
        logger.info("Paired Data Summary:")
        logger.info(f"  Total signed books: {self.stats['total_signed']}")
        logger.info(f"  Total unsigned books: {self.stats['collected']}")
        logger.info(f"  Complete pairs: {min(self.stats['total_signed'], self.stats['collected'])}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Collect unsigned counterparts for signed books")
    parser.add_argument(
        "--signed-db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "training_data.db"),
        help="Path to signed book training database"
    )
    parser.add_argument(
        "--unsigned-db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "unsigned_pairs.db"),
        help="Path to store unsigned counterparts"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of pairs to collect"
    )
    args = parser.parse_args()

    signed_db = Path(args.signed_db)
    unsigned_db = Path(args.unsigned_db)

    if not signed_db.exists():
        logger.error(f"Signed database not found: {signed_db}")
        return 1

    collector = UnsignedPairCollector(signed_db, unsigned_db)
    collector.collect_all_pairs(limit=args.limit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
