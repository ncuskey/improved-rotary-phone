#!/usr/bin/env python3
"""
Enrich series with eBay lot market data using Serper (Google search) + Decodo (web scraping).

This script searches for book lot listings on eBay for each series in catalog.db,
extracts comprehensive data (price, lot size, condition, completeness), and stores
the results in metadata_cache.db for pricing intelligence and market research.

Usage:
    python scripts/enrich_series_lot_market_data.py --concurrency 20 --results 5
    python scripts/enrich_series_lot_market_data.py --limit 10  # Test with 10 series
"""

import asyncio
import logging
import sqlite3
import re
import os
import sys
import argparse
import statistics
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from shared.search_api_async import AsyncSerperSearchAPI
from shared.decodo import DecodoClient
from shared.db_monitor import monitored_connect

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SeriesLotEnricher:
    """Enrich series data with eBay lot market comps via Serper + Decodo."""

    def __init__(
        self,
        concurrency: int = 20,
        results_per_search: int = 5,
        min_lots_required: int = 2
    ):
        self.concurrency = concurrency
        self.results_per_search = results_per_search
        self.min_lots_required = min_lots_required

        # Paths
        self.catalog_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.metadata_cache_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

        # Initialize Decodo
        decodo_user = os.getenv('DECODO_CORE_USERNAME') or os.getenv('DECODO_AUTHENTICATION')
        decodo_pass = os.getenv('DECODO_CORE_PASSWORD') or os.getenv('DECODO_PASSWORD')

        if not decodo_user or not decodo_pass:
            raise ValueError("DECODO_CORE_USERNAME and DECODO_CORE_PASSWORD required in .env")

        self.decodo = DecodoClient(username=decodo_user, password=decodo_pass, rate_limit=30)

        logger.info("Initialized series lot enricher")
        logger.info(f"Catalog database: {self.catalog_path}")
        logger.info(f"Metadata cache database: {self.metadata_cache_path}")
        logger.info(f"Concurrency: {self.concurrency} series")
        logger.info(f"Search results per series: {self.results_per_search}")
        logger.info(f"Minimum lots required: {self.min_lots_required}")
        logger.info(f"Rate limits: Serper 50 req/sec, Decodo 30 req/sec")

    def get_series_for_enrichment(
        self,
        limit: Optional[int] = None,
        force_reprocess: bool = False
    ) -> List[Dict[str, Any]]:
        """Get series from catalog.db that need lot data enrichment."""
        conn = monitored_connect(str(self.catalog_path))
        cursor = conn.cursor()

        # Attach metadata_cache.db to query across both databases
        cursor.execute(f"ATTACH DATABASE '{self.metadata_cache_path}' AS metadata")

        if force_reprocess:
            # Re-process series that already have data
            where_clause = "WHERE s.id IN (SELECT series_id FROM metadata.series_lot_stats)"
        else:
            # Only process series not yet enriched
            where_clause = "WHERE s.id NOT IN (SELECT series_id FROM metadata.series_lot_stats WHERE total_lots_found > 0)"

        query = f"""
            SELECT s.id, s.title, a.name as author_name, s.book_count
            FROM series s
            LEFT JOIN authors a ON s.author_id = a.id
            {where_clause}
            ORDER BY s.book_count DESC, s.title ASC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        series_list = [
            {
                'series_id': row[0],
                'title': row[1],
                'author': row[2],
                'book_count': row[3]
            }
            for row in rows
        ]

        logger.info(f"Found {len(series_list)} series needing lot data enrichment")
        return series_list

    def build_search_queries(self, series: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Build search queries for finding lot listings.

        Returns:
            List of (query_string, query_type) tuples
        """
        queries = []
        title = series['title']
        author = series['author'] or ''

        # Clean title - remove "Series" suffix for cleaner searches
        clean_title = re.sub(r'\s+Series$', '', title, flags=re.IGNORECASE)

        # Query patterns for finding lots (with cleaned title)
        patterns = [
            ('lot', f'site:ebay.com "{clean_title} lot"'),
            ('set', f'site:ebay.com "{clean_title} set"'),
            ('collection', f'site:ebay.com "{clean_title} collection"'),
            ('books', f'site:ebay.com "{clean_title} books"'),
            ('bundle', f'site:ebay.com "{clean_title} bundle"'),
        ]

        # Add author-specific queries if author available
        if author:
            patterns.extend([
                ('author_lot', f'site:ebay.com "{author} {clean_title} lot"'),
                ('author_books', f'site:ebay.com "{author} {clean_title} books"'),
                ('author_bundle', f'site:ebay.com "{author} {clean_title} bundle"'),
                # Broader author search - catches lots listed by author only
                ('author_only', f'site:ebay.com "{author}" lot books'),
            ])

        # Relaxed matching for harder-to-find series (no quotes on keywords)
        patterns.append(
            ('relaxed', f'site:ebay.com "{clean_title}" (lot OR set OR collection OR bundle)')
        )

        return patterns

    def extract_ebay_urls(self, search_results: List[Dict[str, str]]) -> List[str]:
        """Extract eBay listing URLs from Serper search results."""
        urls = []
        for result in search_results:
            url = result.get('link') or result.get('url', '')
            if 'ebay.com/itm/' in url:
                urls.append(url)

        logger.debug(f"  Extracted {len(urls)} eBay URLs from {len(search_results)} search results")
        return urls

    def extract_lot_size(self, text: str) -> Optional[int]:
        """Extract number of books in lot from title/description.

        Patterns:
        - "5 books"
        - "7 book lot"
        - "complete 10 volume set"
        - "books 1-12"
        """
        text_lower = text.lower()

        # Pattern 1: "X books" or "X book"
        match = re.search(r'(\d+)\s+books?(?:\s+lot)?', text_lower)
        if match:
            return int(match.group(1))

        # Pattern 2: "lot of X" or "set of X"
        match = re.search(r'(?:lot|set|collection)\s+of\s+(\d+)', text_lower)
        if match:
            return int(match.group(1))

        # Pattern 3: "X volume set"
        match = re.search(r'(\d+)\s+volumes?(?:\s+set)?', text_lower)
        if match:
            return int(match.group(1))

        # Pattern 4: "books 1-X" or "#1-X"
        match = re.search(r'(?:books?|#)\s*(\d+)\s*[-to]\s*(\d+)', text_lower)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            return end - start + 1

        return None

    def detect_completeness(self, text: str) -> bool:
        """Detect if lot is advertised as complete set."""
        text_lower = text.lower()

        complete_indicators = [
            'complete set',
            'complete series',
            'full set',
            'entire set',
            'whole series',
            'all books',
        ]

        incomplete_indicators = [
            'missing',
            'incomplete',
            'partial',
        ]

        # Check for incomplete indicators first
        for indicator in incomplete_indicators:
            if indicator in text_lower:
                return False

        # Check for complete indicators
        for indicator in complete_indicators:
            if indicator in text_lower:
                return True

        return False

    def extract_condition(self, html: str, title: str) -> Optional[str]:
        """Extract condition from listing."""
        # Try to find eBay's condition field
        condition_patterns = [
            r'"conditionDisplayName":"([^"]+)"',
            r'Condition:\s*</span>\s*<span[^>]*>([^<]+)</span>',
            r'itemCondition":\s*"([^"]+)"',
        ]

        for pattern in condition_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                condition = match.group(1).strip()
                if condition and condition not in ['', 'null', 'None']:
                    return condition

        # Fallback: check title for condition keywords
        title_lower = title.lower()
        if 'new' in title_lower:
            return 'New'
        elif 'like new' in title_lower:
            return 'Like New'
        elif 'very good' in title_lower:
            return 'Very Good'
        elif 'good' in title_lower:
            return 'Good'
        elif 'acceptable' in title_lower or 'fair' in title_lower:
            return 'Acceptable'

        return None

    async def scrape_lot_listing(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape lot listing data from eBay page using Decodo.

        Returns:
            Dict with: price, is_sold, title, lot_size, is_complete, condition
        """
        try:
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

            # Determine if sold or active listing
            is_sold_listing = ('This listing was ended' in html or
                              'listing was ended' in html.lower() or
                              'item is no longer available' in html.lower() or
                              '"itemStatus":"SOLDOUT"' in html)

            # Extract price from JSON-LD structured data
            price = None
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

            # Validate price range
            if not price or price < 1.0 or price > 5000:
                return None

            # Extract title with multiple fallback patterns
            title = ''

            # Pattern 1: og:title meta tag (most reliable for eBay)
            title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.IGNORECASE)
            if title_match:
                title = title_match.group(1)

            # Pattern 2: <title> tag (fallback)
            if not title:
                title_match = re.search(r'<title>([^<|]+)', html, re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()

            # Pattern 3: JSON-LD Product name
            if not title:
                title_match = re.search(r'"@type":"Product"[^}]*"name":"([^"]+)"', html)
                if title_match:
                    title = title_match.group(1)

            # Pattern 4: Generic "name" field (last resort)
            if not title:
                title_match = re.search(r'"name":"([^"]+)"', html)
                if title_match:
                    title = title_match.group(1)

            # Extract lot size from title and description
            lot_size = self.extract_lot_size(title)
            if not lot_size:
                # Try to extract from full HTML
                lot_size = self.extract_lot_size(html[:5000])  # First 5KB

            # Detect completeness
            is_complete = self.detect_completeness(title) or self.detect_completeness(html[:5000])

            # Extract condition
            condition = self.extract_condition(html, title)

            return {
                'price': price,
                'is_sold': is_sold_listing,
                'title': title,
                'lot_size': lot_size,
                'is_complete': is_complete,
                'condition': condition,
                'url': url
            }

        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None

    async def enrich_series(self, series: Dict[str, Any], search_client: AsyncSerperSearchAPI) -> Dict[str, Any]:
        """Enrich a single series with lot data."""
        series_id = series['series_id']
        title = series['title']
        author = series['author']

        stats = {
            'series_id': series_id,
            'series_title': title,
            'author_name': author,
            'lots_found': 0,
            'error': None
        }

        try:
            # Build and execute search queries
            queries = self.build_search_queries(series)
            all_urls = []

            for query_type, query_string in queries:
                logger.info(f"Searching for '{title}' lots ({query_type})")

                # Search with Serper
                search_results = await search_client.search(
                    isbn=query_string,  # Reuse ISBN param for custom query
                    platform='ebay',
                    num_results=self.results_per_search,
                    use_cache=False  # Always fresh for lot searches
                )

                urls = self.extract_ebay_urls(search_results)
                logger.info(f"  Found {len(urls)} eBay URLs from {query_type} search")
                all_urls.extend([(url, query_string) for url in urls])

            if not all_urls:
                stats['error'] = 'No eBay URLs found'
                return stats

            # Scrape lot listings
            lot_data = []
            for url, query in all_urls[:self.results_per_search * 3]:  # Limit total scraping
                data = await self.scrape_lot_listing(url)
                if data:
                    data['search_query'] = query
                    lot_data.append(data)

            logger.info(f"  Scraped {len(lot_data)} lot listings for '{title}'")

            stats['lots_found'] = len(lot_data)

            # Save lot data to database
            if lot_data:
                self.save_lot_data(series, lot_data)
                self.update_series_stats(series, lot_data)

        except Exception as e:
            logger.error(f"Error enriching series '{title}': {e}")
            stats['error'] = str(e)

        return stats

    def save_lot_data(self, series: Dict[str, Any], lot_data: List[Dict[str, Any]]):
        """Save lot data to series_lot_comps table."""
        conn = monitored_connect(str(self.metadata_cache_path))
        cursor = conn.cursor()

        for lot in lot_data:
            try:
                # Calculate price per book if lot size known
                price_per_book = None
                if lot['lot_size'] and lot['lot_size'] > 0:
                    price_per_book = lot['price'] / lot['lot_size']

                cursor.execute("""
                    INSERT OR REPLACE INTO series_lot_comps (
                        series_id, series_title, author_name,
                        ebay_url, listing_title, lot_size, is_complete_set, condition,
                        price, is_sold, price_per_book, search_query, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    series['series_id'],
                    series['title'],
                    series['author'],
                    lot['url'],
                    lot['title'],
                    lot['lot_size'],
                    1 if lot['is_complete'] else 0,
                    lot['condition'],
                    lot['price'],
                    1 if lot['is_sold'] else 0,
                    price_per_book,
                    lot['search_query'],
                    datetime.now().isoformat()
                ))
            except sqlite3.IntegrityError:
                # URL already exists, skip
                pass

        conn.commit()
        conn.close()

    def update_series_stats(self, series: Dict[str, Any], lot_data: List[Dict[str, Any]]):
        """Calculate and save series-level statistics."""
        series_id = series['series_id']

        # Separate sold and active lots
        sold_lots = [lot for lot in lot_data if lot['is_sold']]
        active_lots = [lot for lot in lot_data if not lot['is_sold']]

        # Extract lot sizes and prices
        lot_sizes = [lot['lot_size'] for lot in lot_data if lot['lot_size']]
        sold_prices = [lot['price'] for lot in sold_lots]
        active_prices = [lot['price'] for lot in active_lots]
        price_per_books = [lot['price'] / lot['lot_size']
                          for lot in lot_data
                          if lot['lot_size'] and lot['lot_size'] > 0]

        # Calculate statistics
        stats = {
            'series_id': series_id,
            'series_title': series['title'],
            'author_name': series['author'],
            'total_lots_found': len(lot_data),
            'sold_lots_count': len(sold_lots),
            'active_lots_count': len(active_lots),
            'has_complete_sets': any(lot['is_complete'] for lot in lot_data)
        }

        # Lot size stats
        if lot_sizes:
            stats['min_lot_size'] = min(lot_sizes)
            stats['max_lot_size'] = max(lot_sizes)
            stats['median_lot_size'] = int(statistics.median(lot_sizes))
            # Most common lot size
            from collections import Counter
            stats['most_common_lot_size'] = Counter(lot_sizes).most_common(1)[0][0]

        # Sold price stats
        if sold_prices:
            stats['min_sold_price'] = min(sold_prices)
            stats['median_sold_price'] = statistics.median(sold_prices)
            stats['max_sold_price'] = max(sold_prices)

        # Active price stats
        if active_prices:
            stats['min_active_price'] = min(active_prices)
            stats['median_active_price'] = statistics.median(active_prices)
            stats['max_active_price'] = max(active_prices)

        # Price per book stats
        if price_per_books:
            stats['median_price_per_book'] = statistics.median(price_per_books)

        # Quality score (based on number and variety of comps)
        quality_score = min(len(lot_data) / 10.0, 1.0)  # Max 1.0 at 10+ lots
        stats['enrichment_quality_score'] = quality_score

        # Save to database
        conn = monitored_connect(str(self.metadata_cache_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO series_lot_stats (
                series_id, series_title, author_name,
                total_lots_found, sold_lots_count, active_lots_count,
                min_lot_size, max_lot_size, median_lot_size, most_common_lot_size,
                min_sold_price, median_sold_price, max_sold_price,
                min_active_price, median_active_price, max_active_price,
                median_price_per_book, has_complete_sets, enrichment_quality_score,
                enriched_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stats['series_id'], stats['series_title'], stats['author_name'],
            stats['total_lots_found'], stats['sold_lots_count'], stats['active_lots_count'],
            stats.get('min_lot_size'), stats.get('max_lot_size'),
            stats.get('median_lot_size'), stats.get('most_common_lot_size'),
            stats.get('min_sold_price'), stats.get('median_sold_price'), stats.get('max_sold_price'),
            stats.get('min_active_price'), stats.get('median_active_price'), stats.get('max_active_price'),
            stats.get('median_price_per_book'), 1 if stats['has_complete_sets'] else 0,
            stats['enrichment_quality_score'],
            datetime.now().isoformat(), datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

    async def run_async(
        self,
        limit: Optional[int] = None,
        force_reprocess: bool = False
    ):
        """Run bulk series lot enrichment process."""
        print("=" * 80)
        print("SERIES LOT MARKET DATA ENRICHMENT")
        print("=" * 80)
        print()

        # Get series needing enrichment
        series_list = self.get_series_for_enrichment(limit, force_reprocess)
        total_series = len(series_list)

        if total_series == 0:
            print("No series need enrichment")
            return

        print(f"Enriching {total_series:,} series with eBay lot data")
        print(f"Concurrency: {self.concurrency} series at once")
        print(f"Using Serper (Google search) + Decodo (web scraping)")
        print()

        # Initialize async search client
        async with AsyncSerperSearchAPI() as search_client:
            # Process in batches
            enriched_count = 0
            start_time = datetime.now()

            for batch_start in range(0, total_series, self.concurrency):
                batch_end = min(batch_start + self.concurrency, total_series)
                batch = series_list[batch_start:batch_end]

                print(f"[{batch_start + 1}-{batch_end}/{total_series}] Processing batch of {len(batch)} series...")

                # Enrich batch concurrently
                tasks = [self.enrich_series(series, search_client) for series in batch]
                results = await asyncio.gather(*tasks)

                # Count successes
                batch_enriched = sum(1 for r in results if r['lots_found'] >= self.min_lots_required)
                enriched_count += batch_enriched

                # Calculate progress
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = batch_end / elapsed if elapsed > 0 else 0
                remaining = total_series - batch_end
                eta_minutes = (remaining / rate / 60) if rate > 0 else 0

                print(f"  ✓ Batch complete: {batch_enriched} series enriched")
                print(f"  Progress: {batch_end}/{total_series} series ({batch_end/total_series*100:.1f}%)")
                print(f"  Rate: {rate:.2f} series/sec")
                print(f"  Estimated time remaining: {eta_minutes:.1f} minutes")
                print(f"  Total enriched: {enriched_count} series")
                print()

            # Final summary
            elapsed_minutes = (datetime.now() - start_time).total_seconds() / 60

            print()
            print("=" * 80)
            print("ENRICHMENT COMPLETE")
            print("=" * 80)
            print(f"Series processed: {total_series:,}")
            print(f"Successfully enriched: {enriched_count} ({enriched_count/total_series*100:.1f}%)")
            print(f"No data available: {total_series - enriched_count}")
            print(f"Total time: {elapsed_minutes:.1f} minutes")
            print(f"Average rate: {total_series/elapsed_minutes*60:.2f} series/sec")
            print()

    def run(self, limit: Optional[int] = None, force_reprocess: bool = False):
        """Synchronous wrapper for async run."""
        asyncio.run(self.run_async(limit, force_reprocess))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Bulk enrich series with eBay lot comps via Serper + Decodo'
    )

    parser.add_argument('--limit', type=int, help='Maximum number of series to process')
    parser.add_argument('--concurrency', type=int, default=20, help='Number of series to process concurrently (default: 20)')
    parser.add_argument('--results', type=int, default=5, help='Number of search results per query (default: 5)')
    parser.add_argument('--min-lots', type=int, default=2, help='Minimum number of lots required (default: 2)')
    parser.add_argument('--force-reprocess', action='store_true', help='Re-process series that already have data')

    args = parser.parse_args()

    # Initialize enricher
    enricher = SeriesLotEnricher(
        concurrency=args.concurrency,
        results_per_search=args.results,
        min_lots_required=args.min_lots
    )

    # Run enrichment
    enricher.run(limit=args.limit, force_reprocess=args.force_reprocess)

    return 0


if __name__ == '__main__':
    sys.exit(main())
