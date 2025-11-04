#!/usr/bin/env python3
"""
Enrich sold listings by scraping URLs directly to extract prices.

Takes sold_listings records with URLs but no prices, scrapes each URL using
Decodo API, parses the HTML to extract price/date/condition, and updates
the database records.

Workflow:
1. Query sold_listings WHERE url IS NOT NULL AND price IS NULL
2. Fetch HTML using Decodo Core API (30 req/s, batch support)
3. Parse using platform-specific parsers (eBay, Mercari, Amazon)
4. Update database with extracted data

Usage:
    python scripts/enrich_sold_listings_urls.py --limit 10  # Test mode
    python scripts/enrich_sold_listings_urls.py             # Full run
    python scripts/enrich_sold_listings_urls.py --batch-size 100
"""

import sys
import time
import os
import argparse
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient, DecodoAPIError
from shared.sold_parser_factory import parse_sold_listing, detect_platform
from shared.feature_detector import parse_all_features
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SoldListingEnricher:
    """Enriches sold listings by scraping URLs for missing prices."""

    def __init__(
        self,
        db_path: Path = None,
        decodo_username: str = None,
        decodo_password: str = None,
        rate_limit: int = 30
    ):
        """
        Initialize enricher.

        Args:
            db_path: Path to catalog.db
            decodo_username: Decodo API username
            decodo_password: Decodo API password
            rate_limit: Requests per second (default: 30 for Core plan)
        """
        self.db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

        # Get Decodo credentials from env if not provided
        if not decodo_username:
            decodo_username = os.environ.get('DECODO_CORE_AUTHENTICATION') or os.environ.get('DECODO_AUTHENTICATION')
        if not decodo_password:
            decodo_password = os.environ.get('DECODO_CORE_PASSWORD') or os.environ.get('DECODO_PASSWORD')

        if not decodo_username or not decodo_password:
            raise ValueError(
                "Decodo credentials not provided. Set DECODO_CORE_AUTHENTICATION and "
                "DECODO_CORE_PASSWORD environment variables or pass as arguments."
            )

        # Initialize Decodo client
        self.decodo = DecodoClient(
            username=decodo_username,
            password=decodo_password,
            rate_limit=rate_limit,
            plan='core'
        )

        logger.info(f"Initialized with Decodo Core (rate: {rate_limit} req/s)")
        logger.info(f"Database: {self.db_path}")

    def get_urls_to_scrape(self, limit: Optional[int] = None) -> List[Tuple[str, str, str]]:
        """
        Get URLs from sold_listings that need price enrichment.

        Args:
            limit: Maximum number of URLs to fetch

        Returns:
            List of (url, platform, isbn) tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT url, platform, isbn
            FROM sold_listings
            WHERE url IS NOT NULL
              AND price IS NULL
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(results)} URLs needing price enrichment")
        return results

    def scrape_url(self, url: str, platform: str) -> Optional[Dict[str, Any]]:
        """
        Scrape a single URL using Decodo API and parse the result.

        Args:
            url: URL to scrape
            platform: Platform name (ebay, mercari, amazon)

        Returns:
            Parsed listing data or None if failed
        """
        try:
            # Fetch HTML using Decodo
            response = self.decodo.scrape_url(url)

            if response.status_code != 200:
                logger.warning(f"  ✗ Failed to fetch {url}: HTTP {response.status_code}")
                return None

            if not response.body:
                logger.warning(f"  ✗ Empty response for {url}")
                return None

            # Parse using platform-specific parser
            parsed = parse_sold_listing(url, response.body, snippet="", platform=platform)

            if not parsed.get('success'):
                logger.warning(f"  ✗ Parse failed for {url}: {parsed.get('error', 'Unknown error')}")
                return None

            return parsed

        except DecodoAPIError as e:
            logger.error(f"  ✗ Decodo API error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"  ✗ Unexpected error scraping {url}: {e}")
            return None

    def update_listing(self, url: str, parsed_data: Dict[str, Any]):
        """
        Update sold_listings record with scraped data.

        Args:
            url: URL of the listing
            parsed_data: Parsed listing data from scraper
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Extract features from title if we got a new/better title
            title = parsed_data.get('title')
            features_dict = {}
            signed = 0
            edition = None
            cover_type = None
            dust_jacket = 0

            if title:
                features = parse_all_features(title, include_reasons=False)
                signed = 1 if features.signed else 0
                edition = features.edition
                cover_type = features.cover_type
                dust_jacket = 1 if features.dust_jacket else 0

                features_dict = {
                    'signed': features.signed,
                    'edition': features.edition,
                    'cover_type': features.cover_type,
                    'dust_jacket': features.dust_jacket,
                    'special_features': list(features.special_features) if features.special_features else []
                }

            # Build update query dynamically based on what we have
            updates = []
            params = []

            if parsed_data.get('price') is not None:
                updates.append("price = ?")
                params.append(parsed_data['price'])

            if parsed_data.get('condition'):
                updates.append("condition = ?")
                params.append(parsed_data['condition'])

            if parsed_data.get('sold_date'):
                updates.append("sold_date = ?")
                params.append(parsed_data['sold_date'])

            if title:
                updates.append("title = ?")
                params.append(title)

            if features_dict:
                updates.append("signed = ?")
                params.append(signed)
                updates.append("edition = ?")
                params.append(edition)
                updates.append("cover_type = ?")
                params.append(cover_type)
                updates.append("dust_jacket = ?")
                params.append(dust_jacket)
                updates.append("features_json = ?")
                params.append(json.dumps(features_dict))

            if parsed_data.get('is_lot') is not None:
                updates.append("is_lot = ?")
                params.append(1 if parsed_data['is_lot'] else 0)

            # Always update scraped_at
            updates.append("scraped_at = CURRENT_TIMESTAMP")

            if not updates:
                logger.warning(f"  ⚠ No data to update for {url}")
                return

            query = f"""
                UPDATE sold_listings
                SET {', '.join(updates)}
                WHERE url = ?
            """
            params.append(url)

            cursor.execute(query, params)
            conn.commit()

        except Exception as e:
            logger.error(f"  ✗ Database error updating {url}: {e}")
        finally:
            conn.close()

    def run(
        self,
        limit: Optional[int] = None,
        batch_size: int = 100
    ):
        """
        Run enrichment process.

        Args:
            limit: Maximum number of URLs to process (None = all)
            batch_size: Number of URLs to process before progress update
        """
        print("=" * 80)
        print("SOLD LISTING URL ENRICHMENT")
        print("=" * 80)
        print()

        # Get URLs to scrape
        urls_to_scrape = self.get_urls_to_scrape(limit)
        total_urls = len(urls_to_scrape)

        if total_urls == 0:
            print("No URLs need enrichment!")
            return

        print(f"URLs to process: {total_urls:,}")
        print(f"Estimated time: {total_urls / self.decodo.rate_limit / 60:.1f} minutes")
        print(f"Rate limit: {self.decodo.rate_limit} req/s")
        print()

        # Process URLs
        stats = {
            'total': total_urls,
            'scraped': 0,
            'parsed': 0,
            'updated': 0,
            'failed': 0
        }

        start_time = time.time()

        for idx, (url, platform, isbn) in enumerate(urls_to_scrape, 1):
            # Scrape and parse
            parsed = self.scrape_url(url, platform)
            stats['scraped'] += 1

            if parsed:
                stats['parsed'] += 1

                # Update database
                self.update_listing(url, parsed)
                stats['updated'] += 1

                price_str = f"${parsed.get('price', 0):.2f}" if parsed.get('price') else "N/A"
                logger.info(f"  ✓ [{idx}/{total_urls}] {platform}: {price_str} - {url[:60]}...")
            else:
                stats['failed'] += 1
                logger.info(f"  ✗ [{idx}/{total_urls}] {platform}: Failed - {url[:60]}...")

            # Progress update every batch_size URLs
            if idx % batch_size == 0 or idx == total_urls:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (total_urls - idx) / rate if rate > 0 else 0

                print()
                print(f"Progress: {idx}/{total_urls} URLs ({idx/total_urls*100:.1f}%)")
                print(f"  Scraped: {stats['scraped']}")
                print(f"  Parsed successfully: {stats['parsed']} ({stats['parsed']/stats['scraped']*100:.1f}%)")
                print(f"  Updated: {stats['updated']}")
                print(f"  Failed: {stats['failed']}")
                print(f"  Rate: {rate:.2f} URLs/sec")
                print(f"  ETA: {remaining/60:.1f} minutes")
                print()

        # Final summary
        elapsed = time.time() - start_time

        print()
        print("=" * 80)
        print("ENRICHMENT COMPLETE")
        print("=" * 80)
        print(f"Total URLs processed: {stats['total']:,}")
        print(f"Successfully scraped: {stats['scraped']:,}")
        print(f"Successfully parsed: {stats['parsed']:,} ({stats['parsed']/stats['total']*100:.1f}%)")
        print(f"Database updated: {stats['updated']:,}")
        print(f"Failed: {stats['failed']:,}")
        print(f"Total time: {elapsed/60:.1f} minutes")
        print(f"Average rate: {stats['total']/elapsed:.2f} URLs/sec")
        print()

        # Calculate new price coverage
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sold_listings WHERE price IS NOT NULL")
        with_price = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sold_listings")
        total = cursor.fetchone()[0]
        conn.close()

        coverage = with_price / total * 100 if total > 0 else 0
        print(f"NEW PRICE COVERAGE: {with_price:,}/{total:,} ({coverage:.1f}%)")
        print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Enrich sold listings by scraping URLs for prices'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of URLs to process (for testing)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Progress update frequency (default: 100)'
    )

    parser.add_argument(
        '--rate-limit',
        type=int,
        default=30,
        help='Requests per second (default: 30 for Core plan)'
    )

    args = parser.parse_args()

    try:
        # Initialize enricher
        enricher = SoldListingEnricher(rate_limit=args.rate_limit)

        # Run enrichment
        enricher.run(
            limit=args.limit,
            batch_size=args.batch_size
        )

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
