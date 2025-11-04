#!/usr/bin/env python3
"""
Async enrichment of sold listings by scraping URLs concurrently.

High-throughput version using asyncio and concurrent Decodo API requests.
Processes multiple URLs simultaneously while respecting rate limits.

Usage:
    python scripts/enrich_sold_listings_urls_async.py --limit 50     # Test
    python scripts/enrich_sold_listings_urls_async.py --concurrency 20  # Full run
"""

import sys
import time
import os
import argparse
import sqlite3
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from functools import wraps

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.sold_parser_factory import parse_sold_listing, detect_platform
from shared.feature_detector import parse_all_features
import json
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter for async operations."""

    def __init__(self, rate: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second (requests per second)
        """
        self.rate = rate
        self.tokens = rate
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available, then consume it."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Add new tokens based on elapsed time
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            # Wait if no tokens available
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class AsyncDecodoClient:
    """Async wrapper for Decodo API using aiohttp."""

    def __init__(self, username: str, password: str, rate_limit: int = 30):
        """
        Initialize async Decodo client.

        Args:
            username: Decodo username
            password: Decodo password
            rate_limit: Requests per second
        """
        self.username = username
        self.password = password
        self.rate_limiter = TokenBucket(rate_limit)
        self.base_url = "https://scraper-api.decodo.com/v2"

        # Auth header
        import base64
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ISBN-Lot-Optimizer-Async/1.0"
        }

    async def scrape_url(self, session: aiohttp.ClientSession, url: str) -> Tuple[int, str, Optional[str]]:
        """
        Scrape URL using Decodo API (async).

        Args:
            session: aiohttp session
            url: URL to scrape

        Returns:
            Tuple of (status_code, body, error)
        """
        # Rate limit
        await self.rate_limiter.acquire()

        endpoint = f"{self.base_url}/scrape"
        payload = {"url": url}

        try:
            async with session.post(
                endpoint,
                json=payload,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=150)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Extract HTML from response
                    html_body = ""
                    if isinstance(data, dict) and "results" in data:
                        results = data["results"]
                        if results and len(results) > 0:
                            html_body = results[0].get("content", "")
                    return (200, html_body, None)
                else:
                    error = f"HTTP {response.status}"
                    return (response.status, "", error)

        except asyncio.TimeoutError:
            return (408, "", "Timeout")
        except Exception as e:
            return (500, "", str(e))


class AsyncSoldListingEnricher:
    """Async enricher for sold listings."""

    def __init__(
        self,
        db_path: Path = None,
        decodo_username: str = None,
        decodo_password: str = None,
        rate_limit: int = 30,
        concurrency: int = 20
    ):
        """
        Initialize async enricher.

        Args:
            db_path: Path to catalog.db
            decodo_username: Decodo username
            decodo_password: Decodo password
            rate_limit: Requests per second
            concurrency: Number of concurrent requests
        """
        self.db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.concurrency = concurrency

        # Get credentials
        if not decodo_username:
            decodo_username = os.environ.get('DECODO_CORE_AUTHENTICATION') or os.environ.get('DECODO_AUTHENTICATION')
        if not decodo_password:
            decodo_password = os.environ.get('DECODO_CORE_PASSWORD') or os.environ.get('DECODO_PASSWORD')

        if not decodo_username or not decodo_password:
            raise ValueError("Decodo credentials not found in environment")

        # Initialize async Decodo client
        self.decodo = AsyncDecodoClient(decodo_username, decodo_password, rate_limit)

        logger.info(f"Initialized async enricher")
        logger.info(f"  Rate limit: {rate_limit} req/s")
        logger.info(f"  Concurrency: {concurrency}")
        logger.info(f"  Database: {self.db_path}")

    def get_urls_to_scrape(self, limit: Optional[int] = None) -> List[Tuple[str, str, str]]:
        """Get URLs needing enrichment (sync)."""
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

        logger.info(f"Found {len(results)} URLs to enrich")
        return results

    async def scrape_and_parse_url(
        self,
        session: aiohttp.ClientSession,
        url: str,
        platform: str
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape and parse a single URL (async).

        Args:
            session: aiohttp session
            url: URL to scrape
            platform: Platform name

        Returns:
            Parsed data or None
        """
        # Scrape
        status, html, error = await self.decodo.scrape_url(session, url)

        if status != 200 or not html:
            return None

        # Parse (CPU-bound, but fast enough to not need executor)
        try:
            parsed = parse_sold_listing(url, html, snippet="", platform=platform)
            if parsed.get('success'):
                return parsed
        except Exception as e:
            logger.debug(f"Parse error for {url}: {e}")

        return None

    def update_listing(self, url: str, parsed_data: Dict[str, Any]):
        """Update database with scraped data (sync)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Extract features
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

            # Build update
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

            updates.append("scraped_at = CURRENT_TIMESTAMP")

            if updates:
                query = f"UPDATE sold_listings SET {', '.join(updates)} WHERE url = ?"
                params.append(url)
                cursor.execute(query, params)
                conn.commit()

        finally:
            conn.close()

    async def process_batch(
        self,
        session: aiohttp.ClientSession,
        batch: List[Tuple[str, str, str]],
        stats: Dict[str, int],
        batch_num: int,
        total_batches: int
    ):
        """Process a batch of URLs concurrently."""
        tasks = [
            self.scrape_and_parse_url(session, url, platform)
            for url, platform, isbn in batch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Update database with results
        for (url, platform, isbn), result in zip(batch, results):
            stats['scraped'] += 1

            if isinstance(result, Exception):
                stats['failed'] += 1
                logger.debug(f"  ✗ Exception for {url}: {result}")
            elif result:
                stats['parsed'] += 1
                self.update_listing(url, result)
                stats['updated'] += 1

                price_str = f"${result.get('price', 0):.2f}" if result.get('price') else "N/A"
                if stats['updated'] % 100 == 0:  # Log every 100th success
                    logger.info(f"  ✓ [{stats['updated']}] {platform}: {price_str}")
            else:
                stats['failed'] += 1

    async def run_async(self, limit: Optional[int] = None):
        """Run async enrichment."""
        print("=" * 80)
        print("ASYNC SOLD LISTING URL ENRICHMENT")
        print("=" * 80)
        print()

        # Get URLs
        urls_to_scrape = self.get_urls_to_scrape(limit)
        total_urls = len(urls_to_scrape)

        if total_urls == 0:
            print("No URLs to enrich!")
            return

        print(f"URLs to process: {total_urls:,}")
        print(f"Concurrency: {self.concurrency}")
        print(f"Estimated time: {total_urls / self.decodo.rate_limiter.rate / 60:.1f} minutes")
        print()

        # Stats
        stats = {
            'total': total_urls,
            'scraped': 0,
            'parsed': 0,
            'updated': 0,
            'failed': 0
        }

        start_time = time.time()

        # Process in batches
        async with aiohttp.ClientSession() as session:
            for batch_start in range(0, total_urls, self.concurrency):
                batch_end = min(batch_start + self.concurrency, total_urls)
                batch = urls_to_scrape[batch_start:batch_end]
                batch_num = batch_start // self.concurrency + 1
                total_batches = (total_urls + self.concurrency - 1) // self.concurrency

                await self.process_batch(session, batch, stats, batch_num, total_batches)

                # Progress update
                elapsed = time.time() - start_time
                rate = stats['scraped'] / elapsed if elapsed > 0 else 0
                remaining = (total_urls - stats['scraped']) / rate if rate > 0 else 0

                print(f"Batch {batch_num}/{total_batches}: {stats['scraped']}/{total_urls} URLs ({stats['scraped']/total_urls*100:.1f}%)")
                print(f"  Parsed: {stats['parsed']} ({stats['parsed']/stats['scraped']*100:.1f}%)")
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
        print(f"Total URLs: {stats['total']:,}")
        print(f"Successfully parsed: {stats['parsed']:,} ({stats['parsed']/stats['total']*100:.1f}%)")
        print(f"Database updated: {stats['updated']:,}")
        print(f"Failed: {stats['failed']:,}")
        print(f"Total time: {elapsed/60:.1f} minutes")
        print(f"Average rate: {stats['total']/elapsed:.2f} URLs/sec")
        print()

        # New coverage
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

    def run(self, limit: Optional[int] = None):
        """Sync wrapper for async run."""
        asyncio.run(self.run_async(limit))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Async URL enrichment for sold listings')

    parser.add_argument('--limit', type=int, help='Max URLs to process (for testing)')
    parser.add_argument('--concurrency', type=int, default=20, help='Concurrent requests (default: 20)')
    parser.add_argument('--rate-limit', type=int, default=30, help='Requests per second (default: 30)')

    args = parser.parse_args()

    try:
        enricher = AsyncSoldListingEnricher(
            rate_limit=args.rate_limit,
            concurrency=args.concurrency
        )

        enricher.run(limit=args.limit)
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
