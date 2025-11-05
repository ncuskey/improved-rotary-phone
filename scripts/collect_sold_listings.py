#!/usr/bin/env python3
"""
Sold listing collector - discovers and collects sold listing data across platforms.

Workflow:
1. Search for sold listings using Serper.dev (eBay, Mercari, Amazon)
2. Extract data from search titles and snippets (NO HTML scraping)
3. Parse features using feature_detector
4. Save to sold_listings table
5. Track progress and handle errors

Usage:
    python scripts/collect_sold_listings.py --limit 10
    python scripts/collect_sold_listings.py --isbn 9780307387899
    python scripts/collect_sold_listings.py --source catalog  # All catalog books
    python scripts/collect_sold_listings.py --source metadata_cache  # All metadata cache
"""

import sys
import time
import re
import argparse
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

from shared.search_api import SerperSearchAPI
from shared.feature_detector import parse_all_features
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SoldListingCollector:
    """Orchestrates sold listing discovery and collection."""

    # Supported platforms for search
    SUPPORTED_PLATFORMS = ['ebay', 'mercari', 'amazon']

    def __init__(
        self,
        db_path: Path = None,
        platforms: List[str] = None,
        results_per_platform: int = 5
    ):
        """
        Initialize collector.

        Args:
            db_path: Path to catalog.db
            platforms: List of platforms to search (default: all supported)
            results_per_platform: Number of search results to fetch per platform
        """
        self.db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.platforms = platforms or self.SUPPORTED_PLATFORMS
        self.results_per_platform = results_per_platform

        # Initialize search client (NO HTML scraping - Serper.dev only)
        self.search_client = SerperSearchAPI()

        logger.info(f"Initialized collector for platforms: {', '.join(self.platforms)}")
        logger.info(f"Results per platform: {self.results_per_platform}")
        logger.info("Using Serper.dev search results only (no HTML scraping)")

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

    def search_for_sold_listings(self, isbn: str) -> Dict[str, List[Dict]]:
        """
        Search for sold listings across platforms.

        Args:
            isbn: ISBN to search for

        Returns:
            Dict mapping platform to list of search results:
            {
                'ebay': [{'url': ..., 'title': ..., 'snippet': ...}],
                'mercari': [...],
                ...
            }
        """
        logger.info(f"Searching for sold listings: {isbn}")

        results = self.search_client.search_multiple_platforms(
            isbn,
            platforms=self.platforms,
            num_results=self.results_per_platform,
            use_cache=True
        )

        total_found = sum(len(r) for r in results.values())
        logger.info(f"  Found {total_found} sold listing URLs across {len(self.platforms)} platforms")

        return results

    def extract_from_search_result(
        self,
        result: Dict[str, str],
        platform: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract listing data directly from Serper search result.

        Args:
            result: Search result dict with 'title', 'snippet', 'url'
            platform: Platform name

        Returns:
            Parsed listing dict with extracted data
        """
        try:
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            url = result.get('url', '')

            if not title or not url:
                logger.debug(f"  Skipping result without title or URL")
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
        """Extract price from title or snippet."""
        text = f"{title} {snippet}"

        # Common patterns: $XX.XX, $XX, USD XX.XX
        patterns = [
            r'\$(\d+(?:\.\d{2})?)',  # $24.99 or $24
            r'(?:USD|US)\s*\$?\s*(\d+(?:\.\d{2})?)',  # USD 24.99
            r'(\d+\.\d{2})\s*(?:USD|dollars?)',  # 24.99 USD
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
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
        # Patterns like: "Sold Jan 15, 2025", "Sold on 1/15/2025"
        patterns = [
            r'sold\s+(?:on\s+)?([A-Za-z]+\s+\d{1,2},?\s+\d{4})',  # Jan 15, 2025
            r'sold\s+(?:on\s+)?(\d{1,2}/\d{1,2}/\d{4})',  # 1/15/2025
        ]

        for pattern in patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _is_lot(self, title: str, snippet: str) -> bool:
        """Detect if listing is a lot (multiple books)."""
        text = f"{title} {snippet}".lower()

        lot_indicators = [
            r'\blot\s+of\s+\d+',  # "lot of 5"
            r'\d+\s+books?',  # "5 books"
            r'\d+\s+(?:volume|vol)s?',  # "3 volumes"
            r'complete\s+set',  # "complete set"
            r'series\s+set',  # "series set"
            r'collection\s+of',  # "collection of"
        ]

        for pattern in lot_indicators:
            if re.search(pattern, text):
                return True

        return False

    def _extract_listing_id(self, url: str, platform: str) -> Optional[str]:
        """Extract listing ID from URL."""
        if platform == 'ebay':
            # eBay: /itm/123456789
            match = re.search(r'/itm/(\d+)', url)
            if match:
                return match.group(1)
        elif platform == 'mercari':
            # Mercari: /item/m123456789
            match = re.search(r'/item/(m\d+)', url)
            if match:
                return match.group(1)
        elif platform == 'amazon':
            # Amazon: /dp/B123456789 or /gp/product/B123456789
            match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]+)', url)
            if match:
                return match.group(1)

        return None

    def save_sold_listing(self, listing: Dict[str, Any], isbn: str):
        """
        Save sold listing to database with extracted features.

        Args:
            listing: Parsed listing data
            isbn: ISBN being collected
        """
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

                # Convert to dict for JSON storage
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

            # Log with feature info
            feature_info = []
            if signed:
                feature_info.append("SIGNED")
            if edition:
                feature_info.append(f"{edition}")
            if dust_jacket:
                feature_info.append("DJ")
            if cover_type:
                feature_info.append(cover_type)

            feature_str = f" [{', '.join(feature_info)}]" if feature_info else ""
            logger.debug(f"  Saved: {listing['platform']} - {title[:40]}{feature_str}")

        except Exception as e:
            logger.error(f"  Database error saving listing: {e}")

        finally:
            conn.close()

    def collect_for_isbn(self, isbn: str) -> Dict[str, int]:
        """
        Collect sold listings for a single ISBN.

        Args:
            isbn: ISBN to process

        Returns:
            Dict with collection stats:
            {
                'searched': int,  # URLs found
                'extracted': int, # Successfully extracted
                'saved': int      # Listings saved to database
            }
        """
        stats = {
            'searched': 0,
            'extracted': 0,
            'saved': 0
        }

        # Step 1: Search for sold listings
        search_results = self.search_for_sold_listings(isbn)

        for platform, results in search_results.items():
            stats['searched'] += len(results)

            for result in results:
                # Step 2: Extract data from search result (NO HTML scraping)
                listing = self.extract_from_search_result(result, platform)

                if listing:
                    stats['extracted'] += 1

                    # Step 3: Save to database
                    self.save_sold_listing(listing, isbn)
                    stats['saved'] += 1

        return stats

    def run(
        self,
        source: str = 'catalog',
        limit: Optional[int] = None,
        single_isbn: Optional[str] = None
    ):
        """
        Run collection process.

        Args:
            source: 'catalog' or 'metadata_cache'
            limit: Maximum number of ISBNs to process
            single_isbn: Process single ISBN only
        """
        print("=" * 80)
        print("SOLD LISTING COLLECTOR")
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
        print()

        # Process each ISBN
        total_stats = {
            'searched': 0,
            'extracted': 0,
            'saved': 0
        }

        start_time = time.time()

        for idx, isbn in enumerate(isbns, 1):
            print(f"[{idx}/{total_isbns}] Processing ISBN {isbn}...")

            try:
                stats = self.collect_for_isbn(isbn)

                total_stats['searched'] += stats['searched']
                total_stats['extracted'] += stats['extracted']
                total_stats['saved'] += stats['saved']

                print(f"  ✓ Found {stats['searched']} URLs, saved {stats['saved']} listings")

            except Exception as e:
                logger.error(f"Error processing ISBN {isbn}: {e}")
                print(f"  ✗ Error: {e}")

            # Progress update every 10 ISBNs
            if idx % 10 == 0:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (total_isbns - idx) / rate if rate > 0 else 0

                print()
                print(f"Progress: {idx}/{total_isbns} ISBNs ({idx/total_isbns*100:.1f}%)")
                print(f"Rate: {rate:.2f} ISBNs/sec")
                print(f"Estimated time remaining: {remaining/60:.1f} minutes")
                print(f"Total saved: {total_stats['saved']} listings")
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
        print()

        # Show usage stats
        usage = self.search_client.get_usage_stats()
        print("Serper API Usage:")
        print(f"  Total searches: {usage['total_searches']}")
        print(f"  This session: {usage['session_searches']}")
        print(f"  Remaining credits: {usage['estimated_remaining_credits']}")
        print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Collect sold book listings')

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

    args = parser.parse_args()

    # Initialize collector
    collector = SoldListingCollector(
        platforms=args.platforms,
        results_per_platform=args.results
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
