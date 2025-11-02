"""
Collect Amazon pricing data for books in metadata cache.

Uses Decodo's amazon_pricing target to get current marketplace prices.
Enriches metadata cache with median "Used - Good" prices for ML training.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AmazonPricingCollector:
    """Collects Amazon pricing data via Decodo API."""

    def __init__(self, cache_db_path: Path, rate_limit: int = 100):
        """
        Initialize pricing collector.

        Args:
            cache_db_path: Path to metadata_cache.db
            rate_limit: Rate limit in requests per second
        """
        self.cache_db_path = cache_db_path
        self.rate_limit = rate_limit
        self.min_request_interval = 1.0 / rate_limit
        self.last_request_time = 0

        # Initialize Decodo client
        username = os.environ.get('DECODO_AUTHENTICATION')
        password = os.environ.get('DECODO_PASSWORD')

        if not username or not password:
            raise ValueError("DECODO_AUTHENTICATION and DECODO_PASSWORD must be set")

        self.decodo = DecodoClient(username, password)

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize pricing table in metadata cache database."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        # Create pricing table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS amazon_pricing (
                isbn TEXT PRIMARY KEY,
                pricing_json TEXT,
                median_used_good REAL,
                median_used_very_good REAL,
                min_price REAL,
                max_price REAL,
                offer_count INTEGER,
                collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (isbn) REFERENCES cached_books(isbn)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pricing_isbn
            ON amazon_pricing(isbn)
        """)

        conn.commit()
        conn.close()

        logger.info(f"Pricing database initialized at {self.cache_db_path}")
        logger.info(f"Initialized with rate limit: {self.rate_limit} req/s")

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

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

    def _parse_pricing_data(self, pricing_list: List[Dict]) -> Dict:
        """
        Parse pricing data and calculate statistics.

        Args:
            pricing_list: List of pricing offers from Decodo

        Returns:
            Dict with pricing statistics
        """
        if not pricing_list:
            return {}

        # Group by condition
        used_good = []
        used_very_good = []
        all_prices = []

        for offer in pricing_list:
            price = offer.get('price', 0)
            condition = offer.get('condition', '').lower()

            if price > 0:
                all_prices.append(price)

                if 'good' in condition and 'very' not in condition:
                    used_good.append(price)
                elif 'very good' in condition:
                    used_very_good.append(price)

        # Calculate statistics
        stats = {
            'offer_count': len(pricing_list),
            'min_price': min(all_prices) if all_prices else None,
            'max_price': max(all_prices) if all_prices else None,
        }

        # Calculate medians
        if used_good:
            used_good.sort()
            median_idx = len(used_good) // 2
            stats['median_used_good'] = used_good[median_idx]

        if used_very_good:
            used_very_good.sort()
            median_idx = len(used_very_good) // 2
            stats['median_used_very_good'] = used_very_good[median_idx]

        return stats

    def collect_pricing(self, isbn: str) -> bool:
        """
        Collect pricing for a single ISBN.

        Args:
            isbn: ISBN-13 string

        Returns:
            True if successful, False otherwise
        """
        try:
            # Rate limiting
            self._rate_limit()

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
                logger.debug(f"Failed to fetch pricing for {isbn}: status {response.status_code}")
                return False

            # Parse response
            try:
                response_data = json.loads(response.body)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response for {isbn}: {e}")
                return False

            # Extract pricing data
            if isinstance(response_data, dict) and 'results' in response_data:
                results_list = response_data['results']

                if isinstance(results_list, list) and len(results_list) > 0:
                    result = results_list[0]

                    if result.get('status_code') != 200:
                        logger.debug(f"Amazon returned status {result.get('status_code')} for {isbn}")
                        return False

                    content = result.get('content', {})
                    amazon_data = content.get('results', {})
                    pricing_list = amazon_data.get('pricing', [])

                    if not pricing_list:
                        logger.debug(f"No pricing data for {isbn}")
                        return False

                    # Parse pricing statistics
                    stats = self._parse_pricing_data(pricing_list)

                    # Store in database
                    conn = sqlite3.connect(self.cache_db_path)
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT OR REPLACE INTO amazon_pricing
                        (isbn, pricing_json, median_used_good, median_used_very_good,
                         min_price, max_price, offer_count, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """, (
                        isbn,
                        json.dumps(pricing_list),
                        stats.get('median_used_good'),
                        stats.get('median_used_very_good'),
                        stats.get('min_price'),
                        stats.get('max_price'),
                        stats.get('offer_count', 0)
                    ))

                    conn.commit()
                    conn.close()

                    return True

            return False

        except Exception as e:
            logger.error(f"Error collecting pricing for {isbn}: {e}")
            return False

    def get_books_needing_pricing(self, limit: Optional[int] = None,
                                  skip_existing: bool = True) -> List[str]:
        """
        Get list of ISBNs that need pricing data.

        Args:
            limit: Maximum number of ISBNs to return
            skip_existing: Skip ISBNs that already have pricing

        Returns:
            List of ISBN-13 strings
        """
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        if skip_existing:
            query = """
                SELECT isbn FROM cached_books
                WHERE source = 'amazon_decodo'
                AND isbn NOT IN (SELECT isbn FROM amazon_pricing)
                ORDER BY created_at DESC
            """
        else:
            query = """
                SELECT isbn FROM cached_books
                WHERE source = 'amazon_decodo'
                ORDER BY created_at DESC
            """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        isbns = [row[0] for row in cursor.fetchall()]
        conn.close()

        return isbns

    def collect_batch(self, isbns: List[str]):
        """
        Collect pricing for a batch of ISBNs.

        Args:
            isbns: List of ISBN-13 strings
        """
        logger.info("=" * 70)
        logger.info("AMAZON PRICING COLLECTION")
        logger.info("=" * 70)
        logger.info(f"Total ISBNs: {len(isbns)}")
        logger.info(f"Rate limit: {self.rate_limit} req/s")
        logger.info("")

        successful = 0
        failed = 0

        start_time = time.time()

        for i, isbn in enumerate(isbns, 1):
            logger.info(f"[{i}/{len(isbns)}] Processing {isbn}")

            if self.collect_pricing(isbn):
                successful += 1
                logger.info(f"  {isbn}: ✓ Pricing collected")
            else:
                failed += 1
                logger.warning(f"  {isbn}: Failed to collect pricing")

        elapsed = time.time() - start_time

        logger.info("")
        logger.info("=" * 70)
        logger.info("COLLECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total processed: {len(isbns)}")
        logger.info(f"Successfully collected: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Average time per book: {elapsed/len(isbns):.2f} seconds")
        logger.info(f"Average rate: {len(isbns)/elapsed:.1f} books/sec")
        logger.info("")

        # Print pricing stats
        self._print_pricing_stats()

    def _print_pricing_stats(self):
        """Print statistics about collected pricing data."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(median_used_good) as has_used_good,
                COUNT(median_used_very_good) as has_used_very_good,
                AVG(median_used_good) as avg_used_good,
                AVG(offer_count) as avg_offers
            FROM amazon_pricing
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            total, has_good, has_very_good, avg_good, avg_offers = row
            logger.info(f"Pricing database now has {total} books")
            logger.info(f"  Books with 'Used - Good' price: {has_good}")
            logger.info(f"  Books with 'Used - Very Good' price: {has_very_good}")
            if avg_good:
                logger.info(f"  Average 'Used - Good' price: ${avg_good:.2f}")
            if avg_offers:
                logger.info(f"  Average offers per book: {avg_offers:.1f}")
        logger.info("")


def main():
    """Main entry point for pricing collection."""
    parser = argparse.ArgumentParser(description="Collect Amazon pricing data")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of ISBNs to process"
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=100,
        help="Rate limit in requests per second (default: 100)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip ISBNs that already have pricing (default: True)"
    )
    parser.add_argument(
        "--isbn-file",
        type=str,
        default=None,
        help="Path to file containing ISBNs (one per line)"
    )
    args = parser.parse_args()

    # Get metadata cache path
    cache_db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    if not cache_db_path.exists():
        logger.error(f"Metadata cache not found at {cache_db_path}")
        return 1

    # Initialize collector
    collector = AmazonPricingCollector(cache_db_path, rate_limit=args.rate_limit)

    # Get ISBNs needing pricing
    if args.isbn_file:
        logger.info(f"Loading ISBNs from {args.isbn_file}...")
        isbn_file = Path(args.isbn_file)
        if not isbn_file.exists():
            logger.error(f"ISBN file not found: {args.isbn_file}")
            return 1

        isbns = []
        with open(isbn_file) as f:
            for line in f:
                isbn = line.strip()
                if isbn:
                    isbns.append(isbn)

        logger.info(f"Loaded {len(isbns)} ISBNs from file")
    else:
        logger.info("Finding books needing pricing data...")
        isbns = collector.get_books_needing_pricing(
            limit=args.limit,
            skip_existing=args.skip_existing
        )

    if not isbns:
        logger.info("No books need pricing data!")
        return 0

    logger.info(f"Found {len(isbns)} books needing pricing")

    # Collect pricing
    collector.collect_batch(isbns)

    return 0


if __name__ == "__main__":
    sys.exit(main())
