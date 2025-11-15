#!/usr/bin/env python3
"""
Bulk Market Data Enrichment for metadata_cache.db

Uses Serper API (Google search) to find eBay sold listings, then uses
Decodo to scrape actual sold prices from those pages.

This avoids eBay API rate limits by going through Google search + web scraping.

Workflow:
1. Find ISBNs in metadata_cache.db without market data
2. Use Serper to search Google for "site:ebay.com ISBN sold"
3. Extract eBay listing URLs from search results
4. Use Decodo to scrape sold prices from those URLs
5. Aggregate prices and update metadata_cache.db
6. Recalculate training_quality_score and in_training flag

Usage:
    python scripts/enrich_metadata_cache_market_data.py --limit 100
    python scripts/enrich_metadata_cache_market_data.py --concurrency 20
    python scripts/enrich_metadata_cache_market_data.py --min-comps 3
"""

import sys
import time
import re
import argparse
import sqlite3
import asyncio
import logging
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

from shared.search_api_async import AsyncSerperSearchAPI
from shared.decodo import DecodoClient
from shared.db_monitor import monitored_connect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketDataEnricher:
    """Bulk enrichment of metadata_cache.db with eBay sold comps via Serper + Decodo."""

    def __init__(
        self,
        metadata_cache_path: Path = None,
        concurrency: int = 20,
        results_per_search: int = 10,
        min_comps_required: int = 5
    ):
        """
        Initialize market data enricher.

        Args:
            metadata_cache_path: Path to metadata_cache.db
            concurrency: Number of ISBNs to process concurrently
            results_per_search: Number of search results to fetch per ISBN
            min_comps_required: Minimum number of sold comps to save
        """
        self.metadata_cache_path = metadata_cache_path or Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
        self.concurrency = concurrency
        self.results_per_search = results_per_search
        self.min_comps_required = min_comps_required

        # Initialize Decodo client (try Core credentials first, then fallback)
        decodo_user = os.getenv('DECODO_CORE_USERNAME') or os.getenv('DECODO_AUTHENTICATION')
        decodo_pass = os.getenv('DECODO_CORE_PASSWORD') or os.getenv('DECODO_PASSWORD')
        if not decodo_user or not decodo_pass:
            raise ValueError("DECODO_CORE_USERNAME/DECODO_CORE_PASSWORD required in .env")

        self.decodo = DecodoClient(
            username=decodo_user,
            password=decodo_pass,
            rate_limit=30  # Core plan: 30 req/sec
        )

        logger.info(f"Initialized market data enricher")
        logger.info(f"Database: {self.metadata_cache_path}")
        logger.info(f"Concurrency: {self.concurrency} ISBNs")
        logger.info(f"Search results per ISBN: {self.results_per_search}")
        logger.info(f"Minimum comps required: {self.min_comps_required}")
        logger.info(f"Rate limits: Serper 50 req/sec, Decodo 30 req/sec")

    def get_isbns_needing_enrichment(
        self,
        limit: Optional[int] = None,
        max_quality: Optional[float] = None,
        force_reprocess: bool = False
    ) -> List[str]:
        """Get ISBNs from metadata_cache.db that need market data enrichment."""
        conn = monitored_connect(str(self.metadata_cache_path))
        cursor = conn.cursor()

        if force_reprocess:
            # Re-process ALL ISBNs that have market data (to capture missed sold listings)
            conditions = ["market_json IS NOT NULL"]
        else:
            conditions = [
                "(market_json IS NULL OR market_json = '{}')",
                "OR sold_comps_median IS NULL",
                "OR sold_comps_count IS NULL",
                "OR sold_comps_count < 5"
            ]

        if max_quality is not None:
            conditions.append(f"OR training_quality_score <= {max_quality}")

        query = f"""
            SELECT isbn, title, training_quality_score
            FROM cached_books
            WHERE ({' '.join(conditions)})
            ORDER BY training_quality_score DESC, title ASC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(rows)} ISBNs needing market data enrichment")
        return [row[0] for row in rows]

    def extract_ebay_urls(self, search_results: List[Dict[str, str]]) -> List[str]:
        """Extract eBay listing URLs from Serper search results."""
        urls = []
        for result in search_results:
            url = result.get('link') or result.get('url')
            if url and 'ebay.com/itm/' in url:
                # Extract clean URL without tracking parameters
                match = re.search(r'(https?://www\.ebay\.com/itm/[^?]+)', url)
                if match:
                    urls.append(match.group(1))
        return urls

    async def scrape_price(self, url: str) -> Optional[tuple[float, bool]]:
        """
        Scrape price from eBay listing using Decodo.

        Returns:
            Tuple of (price, is_sold) or None if no price found
            - is_sold=True for completed/sold listings
            - is_sold=False for active "Buy It Now" listings
        """
        try:
            # Run Decodo scrape in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.decodo.scrape_url,
                url
            )

            if response.status_code != 200:
                logger.debug(f"Decodo fetch failed for {url}: status {response.status_code}")
                return None

            html = response.body

            # Determine if this is a sold or active listing
            is_sold_listing = ('This listing was ended' in html or
                              'listing was ended' in html.lower() or
                              'item is no longer available' in html.lower() or
                              '"itemStatus":"SOLDOUT"' in html)

            is_active_listing = ('Buy It Now' in html or
                                'Add to cart' in html or
                                'Add to watchlist' in html or
                                '"itemStatus":"ACTIVE"' in html)

            # Extract price from JSON-LD structured data (works for both sold and active)
            price = None

            # Pattern 1: JSON "price" field (most reliable)
            match = re.search(r'"@type":"Offer"[^}]*"price":"([\d.]+)"', html)
            if not match:
                match = re.search(r'"priceCurrency":"USD"[^}]*"price":"([\d.]+)"', html)
            if not match:
                match = re.search(r'"price":\s*"?([\d.]+)"?', html)

            if match:
                try:
                    price = float(match.group(1))
                except:
                    price = None

            # Pattern 2: Fallback to meta tag
            if not price:
                match = re.search(r'<meta[^>]+property="og:price:amount"[^>]+content="([\d.]+)"', html, re.IGNORECASE)
                if match:
                    try:
                        price = float(match.group(1))
                    except:
                        price = None

            # Pattern 3: Text-based sold price
            if not price and is_sold_listing:
                match = re.search(r'(?:Sold for|Sold\s+for)\s*[:\s]*\$\s*([\d,]+\.?\d*)', html, re.IGNORECASE)
                if match:
                    try:
                        price_str = match.group(1).replace(',', '')
                        price = float(price_str)
                    except:
                        price = None

            # Validate price range
            if price and 0.01 <= price <= 10000:
                # Determine listing type - PRIORITIZE sold indicators
                # (sold pages often have "Buy It Now" in ads/related items)
                is_sold = is_sold_listing  # If any sold indicator found, it's sold
                return (price, is_sold)

            return None

        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None

    def is_lot_listing(self, url: str, html: str = None) -> bool:
        """Check if listing is a lot (multiple books)."""
        # Check URL first
        if re.search(r'\blot\b|\bset\b|\bcollection\b', url, re.IGNORECASE):
            return True

        # Check HTML if available
        if html:
            lot_indicators = [
                r'\blot\s+of\s+\d+',
                r'\d+\s+books?',
                r'\d+\s+(?:volume|vol)s?',
                r'complete\s+set',
                r'series\s+set',
            ]
            for pattern in lot_indicators:
                if re.search(pattern, html, re.IGNORECASE):
                    return True

        return False

    def save_market_data(self, isbn: str, market_data: Dict[str, Any]):
        """Save market data to metadata_cache.db."""
        conn = monitored_connect(str(self.metadata_cache_path))
        cursor = conn.cursor()

        try:
            market_json = json.dumps({
                'sold_comps_count': market_data['sold_comps_count'],
                'sold_comps_min': market_data['sold_comps_min'],
                'sold_comps_median': market_data['sold_comps_median'],
                'sold_comps_max': market_data['sold_comps_max'],
                'source': market_data['sold_comps_source'],
                'fetched_at': market_data['market_fetched_at'],
            })

            cursor.execute("""
                UPDATE cached_books
                SET
                    sold_comps_count = ?,
                    sold_comps_min = ?,
                    sold_comps_median = ?,
                    sold_comps_max = ?,
                    sold_comps_is_estimate = ?,
                    sold_comps_source = ?,
                    market_json = ?,
                    market_fetched_at = ?,
                    last_enrichment_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE isbn = ?
            """, (
                market_data['sold_comps_count'],
                market_data['sold_comps_min'],
                market_data['sold_comps_median'],
                market_data['sold_comps_max'],
                market_data['sold_comps_is_estimate'],
                market_data['sold_comps_source'],
                market_json,
                market_data['market_fetched_at'],
                isbn
            ))

            conn.commit()

            # Recalculate training eligibility
            self._recalculate_training_eligibility(cursor, isbn, market_data)
            conn.commit()

        except Exception as e:
            logger.error(f"Error saving market data for {isbn}: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _recalculate_training_eligibility(self, cursor, isbn: str, market_data: Dict[str, Any]):
        """Recalculate training_quality_score and in_training flag."""
        score = 0.0

        # eBay comp quality (0-70 points)
        sold_comps_count = market_data.get('sold_comps_count', 0)
        if sold_comps_count >= 20:
            score += 0.7
        elif sold_comps_count >= 8:
            score += 0.4

        # Price quality (0-30 points)
        median_price = market_data.get('sold_comps_median', 0)
        if median_price >= 15:
            score += 0.3
        elif median_price >= 5:
            score += 0.15

        # Determine training eligibility
        in_training = 1 if (
            sold_comps_count >= 8 and
            median_price >= 5 and
            score >= 0.6
        ) else 0

        cursor.execute("""
            UPDATE cached_books
            SET training_quality_score = ?, in_training = ?
            WHERE isbn = ?
        """, (score, in_training, isbn))

    async def enrich_isbn(self, isbn: str, search_client: AsyncSerperSearchAPI) -> Dict[str, Any]:
        """Enrich a single ISBN with market data using Serper + Decodo."""
        stats = {
            'isbn': isbn,
            'searched': 0,
            'urls_found': 0,
            'prices_found': 0,
            'saved': False,
            'error': None
        }

        try:
            # Search Google via Serper for eBay sold listings
            # NOTE: Disable cache to avoid stale results from old eBay API implementation
            search_results = await search_client.search(
                isbn=isbn,
                platform='ebay',
                num_results=self.results_per_search,
                use_cache=False  # Fresh searches only for Serper+Decodo approach
            )

            stats['searched'] = len(search_results)

            if not search_results:
                stats['error'] = 'No search results found'
                return stats

            # Extract eBay URLs
            urls = self.extract_ebay_urls(search_results)
            stats['urls_found'] = len(urls)

            logger.info(f"  Extracted {len(urls)} eBay URLs from {len(search_results)} search results")

            # Debug: Log first search result to see structure
            if search_results and not urls:
                first_result = search_results[0]
                logger.debug(f"Sample search result for {isbn}: {first_result}")

            if not urls:
                stats['error'] = 'No eBay URLs found in search results'
                return stats

            # Scrape prices from URLs using Decodo
            sold_prices = []
            active_prices = []
            skipped_lots = 0
            failed_scrapes = 0
            for url in urls[:self.results_per_search]:  # Limit scraping
                # Check if it's a lot listing
                if self.is_lot_listing(url):
                    skipped_lots += 1
                    continue

                result = await self.scrape_price(url)
                if result:
                    price, is_sold = result
                    if is_sold:
                        sold_prices.append(price)
                    else:
                        active_prices.append(price)
                else:
                    failed_scrapes += 1

            # Combine sold and active prices (prioritize sold for statistics)
            all_prices = sold_prices + active_prices
            stats['prices_found'] = len(all_prices)
            stats['sold_count'] = len(sold_prices)
            stats['active_count'] = len(active_prices)

            logger.info(f"  Scraped {len(all_prices)} prices from {len(urls)} URLs ({len(sold_prices)} sold, {len(active_prices)} active, {skipped_lots} lots, {failed_scrapes} failed)")

            # Need minimum number of prices
            if len(all_prices) < self.min_comps_required:
                stats['error'] = f"Insufficient prices: {len(all_prices)} < {self.min_comps_required}"
                return stats

            # Calculate sold comps statistics
            import statistics
            prices_sorted = sorted(all_prices)

            # Mark as estimate if we have any active listings mixed in
            is_estimate = len(active_prices) > 0

            # Create source string showing mix of sold/active
            if len(active_prices) > 0 and len(sold_prices) > 0:
                source = f'serper_decodo (mixed: {len(sold_prices)} sold, {len(active_prices)} active)'
            elif len(active_prices) > 0:
                source = f'serper_decodo (active only: {len(active_prices)})'
            else:
                source = f'serper_decodo (sold: {len(sold_prices)})'

            market_data = {
                'sold_comps_count': len(all_prices),
                'sold_comps_min': min(all_prices),
                'sold_comps_median': statistics.median(all_prices),
                'sold_comps_max': max(all_prices),
                'sold_comps_is_estimate': 1 if is_estimate else 0,  # 1 if includes active listings
                'sold_comps_source': source,
                'market_fetched_at': datetime.now().isoformat(),
            }

            # Save to database
            self.save_market_data(isbn, market_data)
            stats['saved'] = True

            logger.debug(f"Enriched {isbn}: {len(all_prices)} comps (sold={len(sold_prices)}, active={len(active_prices)}), median=${statistics.median(all_prices):.2f}")

        except Exception as e:
            logger.error(f"Error enriching ISBN {isbn}: {e}")
            stats['error'] = str(e)

        return stats

    async def run_async(self, limit: Optional[int] = None, max_quality: Optional[float] = None, force_reprocess: bool = False):
        """Run bulk enrichment process."""
        print("=" * 80)
        print("METADATA CACHE MARKET DATA ENRICHMENT")
        print("=" * 80)
        print()

        # Get ISBNs needing enrichment
        isbns = self.get_isbns_needing_enrichment(limit, max_quality, force_reprocess)
        total_isbns = len(isbns)

        if total_isbns == 0:
            print("No ISBNs need enrichment")
            return

        print(f"Enriching {total_isbns:,} ISBNs with eBay sold comps data")
        print(f"Concurrency: {self.concurrency} ISBNs at once")
        print(f"Using Serper (Google search) + Decodo (web scraping)")
        print()

        total_stats = {
            'processed': 0,
            'saved': 0,
            'failed': 0,
            'no_data': 0
        }

        start_time = time.time()

        # Initialize async search client
        async with AsyncSerperSearchAPI() as search_client:
            # Process ISBNs in batches with controlled concurrency
            for batch_start in range(0, total_isbns, self.concurrency):
                batch_end = min(batch_start + self.concurrency, total_isbns)
                batch_isbns = isbns[batch_start:batch_end]

                print(f"[{batch_start+1}-{batch_end}/{total_isbns}] Processing batch of {len(batch_isbns)} ISBNs...")

                # Create concurrent tasks for this batch
                tasks = [
                    self.enrich_isbn(isbn, search_client)
                    for isbn in batch_isbns
                ]

                # Execute batch concurrently
                batch_results = await asyncio.gather(*tasks)

                # Aggregate stats
                for result in batch_results:
                    total_stats['processed'] += 1
                    if result['saved']:
                        total_stats['saved'] += 1
                    elif result['error']:
                        if 'No search results' in result['error'] or 'Insufficient prices' in result['error'] or 'No eBay URLs' in result['error']:
                            total_stats['no_data'] += 1
                        else:
                            total_stats['failed'] += 1

                # Progress update
                elapsed = time.time() - start_time
                rate = batch_end / elapsed if elapsed > 0 else 0
                remaining = (total_isbns - batch_end) / rate if rate > 0 else 0

                print(f"  ✓ Batch complete: {sum(1 for r in batch_results if r['saved'])} ISBNs enriched")
                print(f"  Progress: {batch_end}/{total_isbns} ISBNs ({batch_end/total_isbns*100:.1f}%)")
                print(f"  Rate: {rate:.2f} ISBNs/sec")
                print(f"  Estimated time remaining: {remaining/60:.1f} minutes")
                print(f"  Total enriched: {total_stats['saved']:,} ISBNs")
                print()

        # Final summary
        elapsed = time.time() - start_time

        print()
        print("=" * 80)
        print("ENRICHMENT COMPLETE")
        print("=" * 80)
        print(f"ISBNs processed: {total_stats['processed']:,}")
        print(f"Successfully enriched: {total_stats['saved']:,} ({total_stats['saved']/total_stats['processed']*100:.1f}%)")
        print(f"No data available: {total_stats['no_data']:,}")
        print(f"Failed: {total_stats['failed']:,}")
        print(f"Total time: {elapsed/60:.1f} minutes")
        print(f"Average rate: {total_stats['processed']/elapsed:.2f} ISBNs/sec")
        print()

        # Check updated training stats
        conn = monitored_connect(str(self.metadata_cache_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cached_books WHERE in_training=1")
        training_count = cursor.fetchone()[0]
        cursor.execute("SELECT AVG(training_quality_score) FROM cached_books WHERE in_training=1")
        avg_quality = cursor.fetchone()[0] or 0.0
        conn.close()

        print("UPDATED TRAINING STATS:")
        print(f"Training-eligible books: {training_count:,}")
        print(f"Average training quality: {avg_quality:.3f}")
        print()

    def run(self, limit: Optional[int] = None, max_quality: Optional[float] = None, force_reprocess: bool = False):
        """Synchronous wrapper for async run."""
        asyncio.run(self.run_async(limit, max_quality, force_reprocess))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Bulk enrich metadata_cache.db with eBay sold comps via Serper + Decodo'
    )

    parser.add_argument('--limit', type=int, help='Maximum number of ISBNs to process')
    parser.add_argument('--concurrency', type=int, default=20, help='Number of ISBNs to process concurrently (default: 20)')
    parser.add_argument('--results', type=int, default=10, help='Number of search results per ISBN (default: 10)')
    parser.add_argument('--min-comps', type=int, default=5, help='Minimum number of sold comps required (default: 5)')
    parser.add_argument('--max-quality', type=float, help='Only enrich ISBNs with training_quality_score <= this value')
    parser.add_argument('--force-reprocess', action='store_true', help='Re-process ALL ISBNs that already have market data (to capture missed sold listings)')

    args = parser.parse_args()

    # Initialize enricher
    enricher = MarketDataEnricher(
        concurrency=args.concurrency,
        results_per_search=args.results,
        min_comps_required=args.min_comps
    )

    # Run enrichment
    enricher.run(limit=args.limit, max_quality=args.max_quality, force_reprocess=args.force_reprocess)

    return 0


if __name__ == '__main__':
    sys.exit(main())
