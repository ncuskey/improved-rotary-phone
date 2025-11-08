#!/usr/bin/env python3
"""
Collect Amazon FBM (Fulfilled by Merchant) pricing data.

Collects third-party seller pricing from Amazon, filtering out FBA and Amazon direct.
FBM sellers are comparable to eBay sellers for ML training purposes.

Uses Decodo's amazon_pricing target and filters for FBM offers:
- NO "Fulfilled by Amazon" badge
- NO Amazon.com as seller
- Third-party merchants only

Features:
- Enriches metadata_cache.db with FBM pricing statistics
- Progress tracking & resume capability
- Rate limiting (configurable req/s)
- Detailed logging

Usage:
  python scripts/collect_amazon_fbm_prices.py --concurrency 10 --test
  python scripts/collect_amazon_fbm_prices.py --concurrency 50 --limit 1000

Database Updates:
- amazon_fbm_count: Number of FBM sellers
- amazon_fbm_min: Lowest FBM price
- amazon_fbm_median: Median FBM price
- amazon_fbm_max: Highest FBM price
- amazon_fbm_avg_rating: Average seller rating
- amazon_fbm_collected_at: Collection timestamp
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient
from shared.amazon_fbm_parser import parse_amazon_fbm_from_decodo, AmazonFBMParseError
from shared.db_monitor import monitored_connect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AmazonFBMCollector:
    """Collects Amazon FBM pricing data via Decodo API."""

    def __init__(
        self,
        cache_db_path: Path,
        concurrency: int = 10,
        test_mode: bool = False
    ):
        """
        Initialize FBM pricing collector.

        Args:
            cache_db_path: Path to metadata_cache.db
            concurrency: Number of concurrent requests (Decodo handles rate limiting)
            test_mode: If True, only process 10 ISBNs
        """
        self.cache_db_path = cache_db_path
        self.concurrency = concurrency
        self.test_mode = test_mode
        self.stats = {
            'processed': 0,
            'successful': 0,
            'fbm_found': 0,
            'errors': 0,
            'skipped': 0
        }

        # Initialize Decodo client (use regular credentials for amazon_pricing)
        username = os.environ.get('DECODO_AUTHENTICATION') or os.environ.get('DECODO_CORE_AUTHENTICATION')
        password = os.environ.get('DECODO_PASSWORD') or os.environ.get('DECODO_CORE_PASSWORD')

        if not username or not password:
            raise ValueError("DECODO_CORE_AUTHENTICATION/DECODO_AUTHENTICATION and DECODO_CORE_PASSWORD/DECODO_PASSWORD must be set")

        self.decodo = DecodoClient(username, password)

        logger.info(f"Initialized FBM collector (concurrency: {concurrency}, test: {test_mode})")

    def _convert_to_isbn10(self, isbn13: str) -> str:
        """
        Convert ISBN-13 to ISBN-10 (ASIN format for Amazon).

        Args:
            isbn13: ISBN-13 string

        Returns:
            ISBN-10 string
        """
        if len(isbn13) == 13 and isbn13.startswith('978'):
            # Remove 978 prefix and check digit
            isbn10_base = isbn13[3:12]

            # Calculate ISBN-10 check digit
            check_sum = 0
            for i, digit in enumerate(isbn10_base):
                check_sum += int(digit) * (10 - i)

            check_digit = (11 - (check_sum % 11)) % 11
            check_char = 'X' if check_digit == 10 else str(check_digit)

            return isbn10_base + check_char

        return isbn13

    def collect_fbm_pricing(self, isbn: str) -> bool:
        """
        Collect FBM pricing for a single ISBN.

        Args:
            isbn: ISBN-13 string

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to ISBN-10
            query_isbn = self._convert_to_isbn10(isbn)

            # Fetch pricing via Decodo
            response = self.decodo.scrape_realtime(
                query=query_isbn,
                target="amazon_pricing",
                domain="com",
                parse=True
            )

            if response.status_code != 200:
                logger.warning(f"Decodo request failed for {isbn}: status {response.status_code}")
                return False

            # Parse response body (should be JSON if parse=True)
            try:
                import json
                data = json.loads(response.body)

                # Extract pricing from nested structure
                # Structure: data['results'][0]['content']['results']['pricing']
                if 'results' in data and len(data['results']) > 0:
                    content = data['results'][0].get('content', {})
                    results = content.get('results', {})
                    pricing_list = results.get('pricing', [])
                else:
                    pricing_list = []

            except (json.JSONDecodeError, KeyError, TypeError, IndexError) as e:
                logger.warning(f"Failed to parse Decodo response for {isbn}: {e}")
                return False

            if not pricing_list:
                logger.debug(f"No pricing data for {isbn}")
                self.stats['skipped'] += 1
                return False

            # Parse FBM offers
            try:
                fbm_stats = parse_amazon_fbm_from_decodo(pricing_list)
            except AmazonFBMParseError as e:
                logger.warning(f"FBM parsing failed for {isbn}: {e}")
                return False

            # Save to database
            self._save_fbm_data(isbn, fbm_stats)

            if fbm_stats['fbm_count'] > 0:
                self.stats['fbm_found'] += 1
                logger.info(
                    f"✓ {isbn}: {fbm_stats['fbm_count']} FBM sellers "
                    f"(${fbm_stats['fbm_min']:.2f} - ${fbm_stats['fbm_max']:.2f}, "
                    f"median: ${fbm_stats['fbm_median']:.2f})"
                )
            else:
                logger.debug(f"No FBM sellers found for {isbn}")
                self.stats['skipped'] += 1

            self.stats['successful'] += 1
            return True

        except Exception as e:
            logger.error(f"Error collecting FBM pricing for {isbn}: {e}")
            self.stats['errors'] += 1
            return False

    def _save_fbm_data(self, isbn: str, fbm_stats: Dict):
        """
        Save FBM pricing data to database.

        Args:
            isbn: ISBN-13 string
            fbm_stats: Dict with FBM statistics
        """
        conn = monitored_connect(self.cache_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE cached_books
            SET
                amazon_fbm_count = ?,
                amazon_fbm_min = ?,
                amazon_fbm_median = ?,
                amazon_fbm_max = ?,
                amazon_fbm_avg_rating = ?,
                amazon_fbm_collected_at = ?
            WHERE isbn = ?
        """, (
            fbm_stats['fbm_count'],
            fbm_stats['fbm_min'],
            fbm_stats['fbm_median'],
            fbm_stats['fbm_max'],
            fbm_stats['fbm_avg_rating'],
            datetime.now().isoformat(),
            isbn
        ))

        conn.commit()
        conn.close()

    def get_isbns_to_process(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[str]:
        """
        Get ISBNs that need FBM pricing data.

        Prioritizes:
        1. High-quality training data (sold_comps_count >= 5)
        2. Books without FBM data yet (amazon_fbm_collected_at IS NULL)

        Args:
            limit: Optional limit on number of ISBNs to process
            offset: Optional offset for pagination (enables parallel processing)

        Returns:
            List of ISBN strings
        """
        conn = monitored_connect(self.cache_db_path)
        cursor = conn.cursor()

        # Build query - prioritize high quality but process all ISBNs
        query = """
            SELECT isbn
            FROM cached_books
            WHERE isbn IS NOT NULL
              AND amazon_fbm_collected_at IS NULL
            ORDER BY
                CASE WHEN sold_comps_count >= 5 THEN 0
                     WHEN sold_comps_count >= 3 THEN 1
                     ELSE 2 END,
                sold_comps_count DESC,
                training_quality_score DESC
        """

        if limit:
            query += f" LIMIT {limit}"
        if offset:
            query += f" OFFSET {offset}"

        cursor.execute(query)
        isbns = [row[0] for row in cursor.fetchall()]

        conn.close()

        logger.info(f"Found {len(isbns)} ISBNs needing FBM pricing data (offset: {offset or 0})")
        return isbns

    def run(self, limit: Optional[int] = None, offset: Optional[int] = None):
        """
        Run FBM pricing collection.

        Args:
            limit: Optional limit on number of ISBNs to process
            offset: Optional offset for pagination (enables parallel processing)
        """
        if self.test_mode:
            limit = 10
            logger.info("TEST MODE: Processing only 10 ISBNs")

        # Get ISBNs to process
        isbns = self.get_isbns_to_process(limit, offset)

        if not isbns:
            logger.info("No ISBNs to process")
            return

        logger.info(f"Processing {len(isbns)} ISBNs...")
        logger.info("=" * 80)

        start_time = time.time()

        # Process ISBNs
        for i, isbn in enumerate(isbns, 1):
            self.stats['processed'] += 1

            # Progress update every 10 ISBNs
            if i % 10 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta_seconds = (len(isbns) - i) / rate if rate > 0 else 0
                eta_hours = eta_seconds / 3600

                logger.info(f"Progress: {i}/{len(isbns)} ({i/len(isbns)*100:.1f}%) "
                           f"| Rate: {rate:.1f} ISBN/s "
                           f"| ETA: {eta_hours:.1f}h "
                           f"| FBM found: {self.stats['fbm_found']}")

            # Collect FBM pricing
            self.collect_fbm_pricing(isbn)

        # Final statistics
        elapsed = time.time() - start_time
        logger.info("=" * 80)
        logger.info("FBM Collection Complete!")
        logger.info(f"Processed: {self.stats['processed']} ISBNs")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"FBM Found: {self.stats['fbm_found']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info(f"Time: {elapsed/60:.1f} minutes")
        logger.info(f"Rate: {self.stats['processed']/elapsed:.1f} ISBN/s")


def main():
    parser = argparse.ArgumentParser(description='Collect Amazon FBM pricing data')
    parser.add_argument('--concurrency', type=int, default=10,
                       help='Number of concurrent requests (default: 10)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of ISBNs to process')
    parser.add_argument('--offset', type=int, default=None,
                       help='Offset for pagination (enables parallel processing)')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: process only 10 ISBNs')

    args = parser.parse_args()

    # Get database path
    cache_db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    if not cache_db_path.exists():
        logger.error(f"Database not found: {cache_db_path}")
        sys.exit(1)

    # Create collector
    collector = AmazonFBMCollector(
        cache_db_path=cache_db_path,
        concurrency=args.concurrency,
        test_mode=args.test
    )

    # Run collection
    collector.run(limit=args.limit, offset=args.offset)


if __name__ == "__main__":
    main()
