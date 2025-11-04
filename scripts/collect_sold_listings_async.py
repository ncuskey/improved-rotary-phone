#!/usr/bin/env python3
"""
Async sold listing collector - high-throughput collection with 50 req/sec.

Workflow:
1. Search for sold listings using Serper.dev (eBay, Mercari, Amazon)
2. Extract data from search titles and snippets (NO HTML scraping)
3. Parse features using feature_detector
4. Save to sold_listings table
5. Process multiple ISBNs concurrently

Usage:
    python scripts/collect_sold_listings_async.py --limit 10
    python scripts/collect_sold_listings_async.py --isbn 9780307387899
    python scripts/collect_sold_listings_async.py --source catalog  # All catalog books
    python scripts/collect_sold_listings_async.py --concurrency 20  # Process 20 ISBNs at once
"""

import sys
import time
import re
import argparse
import sqlite3
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

from shared.search_api_async import AsyncSerperSearchAPI
from shared.feature_detector import parse_all_features
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AsyncSoldListingCollector:
    """Async orchestrator for high-throughput sold listing collection."""

    # Supported platforms for search
    SUPPORTED_PLATFORMS = ['ebay', 'mercari', 'amazon']

    def __init__(
        self,
        db_path: Path = None,
        platforms: List[str] = None,
        results_per_platform: int = 5,
        concurrency: int = 20
    ):
        """
        Initialize async collector.

        Args:
            db_path: Path to catalog.db
            platforms: List of platforms to search (default: all supported)
            results_per_platform: Number of search results to fetch per platform
            concurrency: Number of ISBNs to process concurrently
        """
        self.db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.platforms = platforms or self.SUPPORTED_PLATFORMS
        self.results_per_platform = results_per_platform
        self.concurrency = concurrency

        logger.info(f"Initialized async collector for platforms: {', '.join(self.platforms)}")
        logger.info(f"Results per platform: {self.results_per_platform}")
        logger.info(f"Concurrency: {self.concurrency} ISBNs")
        logger.info("Using Serper.dev search results only (no HTML scraping)")
        logger.info(f"Target throughput: ~{len(self.platforms) * self.concurrency} req/sec (limit: 50 req/sec)")

    def get_isbns_to_process(
        self,
        source: str = 'catalog',
        limit: Optional[int] = None,
        single_isbn: Optional[str] = None
    ) -> List[str]:
        """
        Get list of ISBNs to process.

        Args:
            source: 'catalog' or 'metadata_cache'
            limit: Maximum number of ISBNs to process
            single_isbn: Process single ISBN only

        Returns:
            List of ISBNs
        """
        if single_isbn:
            return [single_isbn]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if source == 'catalog':
            query = "SELECT DISTINCT isbn FROM books WHERE isbn IS NOT NULL"
        else:  # metadata_cache
            cache_db = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
            if not cache_db.exists():
                logger.error(f"Metadata cache DB not found: {cache_db}")
                return []
            conn_cache = sqlite3.connect(cache_db)
            cursor_cache = conn_cache.cursor()
            cursor_cache.execute("SELECT DISTINCT isbn FROM cached_books WHERE isbn IS NOT NULL")
            isbns = [row[0] for row in cursor_cache.fetchall()]
            conn_cache.close()
            if limit:
                isbns = isbns[:limit]
            return isbns

        cursor.execute(query)
        isbns = [row[0] for row in cursor.fetchall()]
        conn.close()

        if limit:
            isbns = isbns[:limit]

        return isbns

    def extract_from_search_result(
        self,
        result: Dict[str, str],
        platform: str
    ) -> Optional[Dict[str, Any]]:
        """Extract listing data directly from Serper search result."""
        try:
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            url = result.get('url', '')

            if not title or not url:
                return None

            # Extract price from title or snippet
            price = self._extract_price(title, snippet)

            # Extract condition from title or snippet
            condition = self._extract_condition(title, snippet)

            # Extract sold date from snippet (if available)
            sold_date = self._extract_sold_date(snippet)

            # Detect if it's a lot
            is_lot = self._is_lot(title, snippet)

            # Extract listing ID from URL
            listing_id = self._extract_listing_id(url, platform)

            return {
                'success': True,
                'platform': platform,
                'url': url,
                'listing_id': listing_id,
                'title': title,
                'snippet': snippet,
                'price': price,
                'condition': condition,
                'sold_date': sold_date,
                'is_lot': is_lot
            }

        except Exception as e:
            logger.error(f"  Error extracting from search result: {e}")
            return None

    def _extract_price(self, title: str, snippet: str) -> Optional[float]:
        """Extract price from title or snippet with validation."""
        text = f"{title} {snippet}"

        # Enhanced patterns with better context
        patterns = [
            # Standard: $XX.XX or $XX (allow 1-2 decimal places)
            (r'\$\s*(\d{1,5}(?:\.\d{1,2})?)', 1),
            # USD format: USD $XX.XX or USD XX.XX
            (r'(?:USD|US)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)', 1),
            # Suffix format: XX.XX USD/dollars
            (r'(\d{1,5}\.\d{1,2})\s*(?:USD|dollars?)', 1),
            # Price: format
            (r'(?:price|sold|cost)[:\s]+\$?\s*(\d{1,5}(?:\.\d{1,2})?)', 1),
        ]

        for pattern, group_idx in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    price = float(match.group(group_idx))

                    # Validate price range (reasonable book prices)
                    if 0.01 <= price <= 10000:
                        # Additional validation: check it's not an ISBN
                        matched_text = match.group(0)

                        # Skip if the number looks like an ISBN (10+ digits)
                        if len(match.group(group_idx).replace('.', '')) >= 10:
                            continue

                        # Skip if near "ISBN" text
                        start = max(0, match.start() - 20)
                        end = min(len(text), match.end() + 20)
                        context = text[start:end].lower()
                        if 'isbn' in context or 'ean' in context:
                            continue

                        return price

                except (ValueError, IndexError):
                    continue

        return None

    def _extract_condition(self, title: str, snippet: str) -> Optional[str]:
        """Extract condition from title or snippet."""
        text = f"{title} {snippet}".lower()
        conditions = [
            'new', 'like new', 'very good', 'good', 'acceptable',
            'brand new', 'mint', 'fine', 'fair', 'poor',
            'used - like new', 'used - very good', 'used - good',
            'used - acceptable', 'used'
        ]

        for condition in conditions:
            if condition in text:
                return condition.title()
        return None

    def _extract_sold_date(self, snippet: str) -> Optional[str]:
        """Extract sold date from snippet."""
        patterns = [
            # Explicit "sold on [date]" patterns
            r'sold\s+(?:on\s+)?([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'sold\s+(?:on\s+)?(\d{1,2}/\d{1,2}/\d{4})',
            # Standalone dates (common in eBay snippets)
            r'\b([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})\b',  # Jan 15, 2024 or Jan 15 2024
            r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',  # 1/15/2024 or 01/15/24
            # Common review date pattern: "by [user]. [Date]."
            r'by\s+\w+\.\s+([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, snippet)
            if match:
                date_str = match.group(1)
                # Validate it's not a year alone or other false positive
                if len(date_str) > 4:  # Longer than just a year
                    return date_str
        return None

    def _is_lot(self, title: str, snippet: str) -> bool:
        """Detect if listing is a lot (multiple books)."""
        text = f"{title} {snippet}".lower()
        lot_indicators = [
            r'\blot\s+of\s+\d+',
            r'\d+\s+books?',
            r'\d+\s+(?:volume|vol)s?',
            r'complete\s+set',
            r'series\s+set',
            r'collection\s+of',
        ]

        for pattern in lot_indicators:
            if re.search(pattern, text):
                return True
        return False

    def _extract_listing_id(self, url: str, platform: str) -> Optional[str]:
        """Extract listing ID from URL."""
        if platform == 'ebay':
            match = re.search(r'/itm/(\d+)', url)
            if match:
                return match.group(1)
        elif platform == 'mercari':
            match = re.search(r'/item/(m\d+)', url)
            if match:
                return match.group(1)
        elif platform == 'amazon':
            match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]+)', url)
            if match:
                return match.group(1)
        return None

    def save_sold_listing(self, listing: Dict[str, Any], isbn: str):
        """Save sold listing to database with extracted features (sync operation)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Extract features from title
            title = listing.get('title', '')
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

            cursor.execute("""
                INSERT OR REPLACE INTO sold_listings
                (isbn, platform, url, listing_id, title, price, condition,
                 sold_date, is_lot, snippet, signed, edition, printing,
                 cover_type, dust_jacket, features_json, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                isbn,
                listing['platform'],
                listing['url'],
                listing.get('listing_id'),
                title,
                listing.get('price'),
                listing.get('condition'),
                listing.get('sold_date'),
                1 if listing.get('is_lot') else 0,
                listing.get('snippet', ''),
                signed,
                edition,
                None,  # printing - not supported by feature_detector
                cover_type,
                dust_jacket,
                json.dumps(features_dict) if features_dict else None
            ))

            conn.commit()

        except Exception as e:
            logger.error(f"  Database error saving listing: {e}")

        finally:
            conn.close()

    async def collect_for_isbn(self, isbn: str, search_client: AsyncSerperSearchAPI) -> Dict[str, int]:
        """
        Collect sold listings for a single ISBN (async).

        Args:
            isbn: ISBN to process
            search_client: Async search API client

        Returns:
            Dict with collection stats
        """
        stats = {
            'searched': 0,
            'extracted': 0,
            'saved': 0
        }

        try:
            # Search for sold listings across all platforms (concurrent)
            search_results = await search_client.search_multiple_platforms(
                isbn,
                platforms=self.platforms,
                num_results=self.results_per_platform,
                use_cache=True
            )

            for platform, results in search_results.items():
                stats['searched'] += len(results)

                for result in results:
                    # Extract data from search result
                    listing = self.extract_from_search_result(result, platform)

                    if listing:
                        stats['extracted'] += 1

                        # Save to database (sync operation)
                        self.save_sold_listing(listing, isbn)
                        stats['saved'] += 1

        except Exception as e:
            logger.error(f"Error processing ISBN {isbn}: {e}")

        return stats

    async def run_async(
        self,
        source: str = 'catalog',
        limit: Optional[int] = None,
        single_isbn: Optional[str] = None
    ):
        """
        Run async collection process.

        Args:
            source: 'catalog' or 'metadata_cache'
            limit: Maximum number of ISBNs to process
            single_isbn: Process single ISBN only
        """
        print("=" * 80)
        print("ASYNC SOLD LISTING COLLECTOR (HIGH-THROUGHPUT)")
        print("=" * 80)
        print()

        # Get ISBNs to process
        isbns = self.get_isbns_to_process(source, limit, single_isbn)
        total_isbns = len(isbns)

        if total_isbns == 0:
            print("No ISBNs to process")
            return

        print(f"Processing {total_isbns} ISBNs")
        print(f"Platforms: {', '.join(self.platforms)}")
        print(f"Results per platform: {self.results_per_platform}")
        print(f"Concurrency: {self.concurrency} ISBNs at once")
        print()

        # Initialize async search client
        async with AsyncSerperSearchAPI() as search_client:
            total_stats = {
                'searched': 0,
                'extracted': 0,
                'saved': 0
            }

            start_time = time.time()

            # Process ISBNs in batches with controlled concurrency
            for batch_start in range(0, total_isbns, self.concurrency):
                batch_end = min(batch_start + self.concurrency, total_isbns)
                batch_isbns = isbns[batch_start:batch_end]

                print(f"[{batch_start+1}-{batch_end}/{total_isbns}] Processing batch of {len(batch_isbns)} ISBNs...")

                # Create concurrent tasks for this batch
                tasks = [
                    self.collect_for_isbn(isbn, search_client)
                    for isbn in batch_isbns
                ]

                # Execute batch concurrently
                batch_stats_list = await asyncio.gather(*tasks)

                # Aggregate stats
                for stats in batch_stats_list:
                    total_stats['searched'] += stats['searched']
                    total_stats['extracted'] += stats['extracted']
                    total_stats['saved'] += stats['saved']

                # Progress update
                elapsed = time.time() - start_time
                rate = batch_end / elapsed if elapsed > 0 else 0
                remaining = (total_isbns - batch_end) / rate if rate > 0 else 0

                print(f"  ✓ Batch complete: {sum(s['saved'] for s in batch_stats_list)} listings saved")
                print(f"  Progress: {batch_end}/{total_isbns} ISBNs ({batch_end/total_isbns*100:.1f}%)")
                print(f"  Rate: {rate:.2f} ISBNs/sec")
                print(f"  Estimated time remaining: {remaining/60:.1f} minutes")
                print(f"  Total saved: {total_stats['saved']} listings")
                print()

            # Final summary
            elapsed = time.time() - start_time

            print()
            print("=" * 80)
            print("COLLECTION COMPLETE")
            print("=" * 80)
            print(f"ISBNs processed: {total_isbns}")
            print(f"Search results found: {total_stats['searched']}")
            print(f"Successfully extracted: {total_stats['extracted']}")
            print(f"Listings saved: {total_stats['saved']}")
            print(f"Success rate: {total_stats['saved']/total_stats['searched']*100:.1f}%" if total_stats['searched'] > 0 else "N/A")
            print(f"Total time: {elapsed/60:.1f} minutes")
            print(f"Average rate: {total_isbns/elapsed:.2f} ISBNs/sec")
            print()

    def run(self, source: str = 'catalog', limit: Optional[int] = None, single_isbn: Optional[str] = None):
        """Synchronous wrapper for async run."""
        asyncio.run(self.run_async(source, limit, single_isbn))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Collect sold book listings (async/high-throughput)')

    parser.add_argument(
        '--source',
        choices=['catalog', 'metadata_cache'],
        default='catalog',
        help='Source of ISBNs to process'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of ISBNs to process'
    )

    parser.add_argument(
        '--isbn',
        type=str,
        help='Process single ISBN'
    )

    parser.add_argument(
        '--platforms',
        type=str,
        nargs='+',
        help='Platforms to search (default: all)'
    )

    parser.add_argument(
        '--results',
        type=int,
        default=5,
        help='Number of results per platform (default: 5)'
    )

    parser.add_argument(
        '--concurrency',
        type=int,
        default=20,
        help='Number of ISBNs to process concurrently (default: 20)'
    )

    args = parser.parse_args()

    # Initialize collector
    collector = AsyncSoldListingCollector(
        platforms=args.platforms,
        results_per_platform=args.results,
        concurrency=args.concurrency
    )

    # Run collection
    collector.run(
        source=args.source,
        limit=args.limit,
        single_isbn=args.isbn
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())
