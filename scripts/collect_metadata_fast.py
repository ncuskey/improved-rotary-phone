#!/usr/bin/env python3
"""
Fast metadata collector using Decodo Amazon scraper.

Much faster than Google Books approach:
- Decodo: configurable rate limit (30+ req/s with advanced credits)
- Direct Amazon data: title, author, binding, sales rank, price
- No need for secondary OpenLibrary calls

Usage:
    python3 scripts/collect_metadata_fast.py --isbn-file isbns.txt --rate-limit 100
    python3 scripts/collect_metadata_fast.py --isbn 9780316769174
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.metadata_cache_db import CachedBook, MetadataCacheDB
from shared.decodo import DecodoClient
from shared.amazon_parser import parse_amazon_html

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FastMetadataCollector:
    """
    Fast metadata collector using Decodo Amazon scraper.

    Optimizations:
    - Direct Amazon data (no slow Google Books API)
    - Configurable rate limit (100+ req/s with advanced credits)
    - Single API call per book (vs 2-3 with old approach)

    Expected speed: 1-3 seconds per book (vs 10-12 seconds)
    """

    def __init__(
        self,
        decodo_username: str,
        decodo_password: str,
        rate_limit: int = 30,
        skip_existing: bool = True
    ):
        """
        Initialize fast metadata collector.

        Args:
            decodo_username: Decodo API username
            decodo_password: Decodo API password
            rate_limit: Max requests per second (30 for Core, 100+ for Advanced)
            skip_existing: If True, skip ISBNs already in cache
        """
        self.cache_db = MetadataCacheDB()
        self.decodo = DecodoClient(
            username=decodo_username,
            password=decodo_password,
            rate_limit=rate_limit
        )
        self.skip_existing = skip_existing

        # Statistics
        self.collected = 0
        self.skipped = 0
        self.failed = 0
        self.start_time = None

        logger.info(f"Initialized with rate limit: {rate_limit} req/s")

    def collect_from_file(self, isbn_file: Path, limit: Optional[int] = None):
        """
        Collect metadata for ISBNs from file.

        Args:
            isbn_file: Path to file with ISBNs (one per line)
            limit: Maximum number of books to collect
        """
        logger.info("=" * 70)
        logger.info("FAST METADATA COLLECTION (Decodo/Amazon)")
        logger.info("=" * 70)
        logger.info(f"ISBN file: {isbn_file}")
        logger.info(f"Limit: {limit or 'unlimited'}")
        logger.info(f"Skip existing: {self.skip_existing}")
        logger.info(f"Rate limit: {self.decodo.rate_limit} req/s")
        logger.info("")

        # Load ISBNs
        isbns = self._load_isbns_from_file(isbn_file)
        logger.info(f"Loaded {len(isbns)} ISBNs from file")

        if limit:
            isbns = isbns[:limit]

        logger.info(f"Processing {len(isbns)} ISBNs")
        logger.info("")

        # Collect metadata
        self.start_time = time.time()

        for i, isbn in enumerate(isbns, 1):
            logger.info(f"[{i}/{len(isbns)}] Processing {isbn}")

            # Check if already in cache
            if self.skip_existing and self.cache_db.has_isbn(isbn):
                logger.info(f"  {isbn}: Already in cache, skipping")
                self.skipped += 1
                continue

            # Collect metadata
            success = self.collect_isbn(isbn)

            if success:
                self.collected += 1
                logger.info(f"  {isbn}: ✓ Stored in cache")
            else:
                self.failed += 1
                logger.warning(f"  {isbn}: Failed to collect metadata")

            # Progress update every 50 books
            if i % 50 == 0:
                self._print_progress(i, len(isbns))

        # Final report
        self._print_final_report(len(isbns))

    def collect_isbn(self, isbn: str) -> bool:
        """
        Collect metadata for a single ISBN from Amazon via Decodo.

        Args:
            isbn: ISBN to collect

        Returns:
            True if successfully collected and stored, False otherwise
        """
        try:
            # Convert ISBN-13 to ISBN-10 (ASIN) for Amazon
            query_isbn = isbn
            if len(isbn) == 13 and isbn.startswith('978'):
                # Convert ISBN-13 to ISBN-10
                isbn10_base = isbn[3:12]  # Remove 978 prefix and check digit

                # Calculate ISBN-10 check digit
                check_sum = 0
                for i, digit in enumerate(isbn10_base):
                    check_sum += int(digit) * (10 - i)
                check_digit = (11 - (check_sum % 11)) % 11
                check_char = 'X' if check_digit == 10 else str(check_digit)

                query_isbn = isbn10_base + check_char
                logger.debug(f"Converted ISBN-13 {isbn} to ISBN-10 {query_isbn}")

            # Fetch via Decodo using amazon_product API
            response = self.decodo.scrape_realtime(
                query=query_isbn,
                target="amazon_product",
                domain="com",
                parse=True
            )

            if response.status_code != 200 or not response.body:
                logger.debug(f"Decodo returned status {response.status_code}")
                return False

            # Response body is JSON string - parse it
            import json
            try:
                response_data = json.loads(response.body)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response for {isbn}: {e}")
                logger.warning(f"  Raw response body: {response.body[:500]}")
                return False

            # DEBUG: Log the full response structure
            logger.debug(f"  Response data: {str(response_data)[:500]}")

            # Extract parsed data from Decodo response structure
            # With parse=True, Decodo returns {"results": [{...}]}
            if isinstance(response_data, dict) and 'results' in response_data:
                results_list = response_data['results']

                # Results is a list - get first element
                if isinstance(results_list, list) and len(results_list) > 0:
                    result = results_list[0]

                    # Check HTTP status code
                    if result.get('status_code') != 200:
                        logger.debug(f"Amazon returned status {result.get('status_code')} for {isbn}")
                        return False

                    # Extract content.results (the actual parsed product data)
                    content = result.get('content', {})
                    amazon_data = content.get('results')

                    if not amazon_data:
                        logger.debug(f"No product data in Decodo response for {isbn}")
                        return False
                else:
                    logger.debug(f"Empty results list for {isbn}")
                    return False
            else:
                logger.debug(f"Unexpected response structure for {isbn}")
                return False

            # DEBUG: Log the amazon data
            logger.debug(f"  Product data keys: {list(amazon_data.keys()) if isinstance(amazon_data, dict) else 'N/A'}")

            # Extract title from parsed data
            title = None
            if isinstance(amazon_data, dict):
                title = amazon_data.get('name') or amazon_data.get('title')

            if not title:
                logger.warning(f"No title found in Amazon data for {isbn}")
                logger.warning(f"  Available keys: {list(amazon_data.keys()) if isinstance(amazon_data, dict) else 'N/A'}")
                return False

            # Convert to CachedBook format
            cached_book = self._convert_to_cached_book_from_parsed(isbn, amazon_data)

            # Store in cache
            if cached_book and cached_book.title:
                return self.cache_db.store_book(cached_book)

            return False

        except Exception as e:
            logger.error(f"Error collecting {isbn}: {e}")
            return False

    def _convert_to_cached_book(self, isbn: str, amazon_data: Dict) -> CachedBook:
        """
        Convert Amazon data to CachedBook format.

        Args:
            isbn: ISBN being fetched
            amazon_data: Data from parse_amazon_html()

        Returns:
            CachedBook instance
        """
        # Extract authors
        authors = amazon_data.get('authors')
        if isinstance(authors, list):
            authors = ', '.join(authors)

        # Extract publication year
        pub_year = amazon_data.get('publication_year')
        if isinstance(pub_year, str):
            try:
                pub_year = int(pub_year)
            except (ValueError, TypeError):
                pub_year = None

        # Extract page count
        page_count = amazon_data.get('page_count')
        if isinstance(page_count, str):
            try:
                page_count = int(page_count)
            except (ValueError, TypeError):
                page_count = None

        return CachedBook(
            isbn=isbn,
            title=amazon_data.get('title'),
            authors=authors,
            publisher=amazon_data.get('publisher'),
            publication_year=pub_year,
            binding=amazon_data.get('binding'),
            page_count=page_count,
            language=amazon_data.get('language'),
            isbn13=amazon_data.get('isbn13') or (isbn if len(isbn) == 13 else None),
            isbn10=amazon_data.get('isbn10') or (isbn if len(isbn) == 10 else None),
            thumbnail_url=amazon_data.get('cover_url'),
            description=amazon_data.get('description'),
            source='amazon_decodo'
        )

    def _convert_to_cached_book_from_parsed(self, isbn: str, parsed_data: Dict) -> CachedBook:
        """
        Convert parsed Decodo Amazon data to CachedBook format.

        Args:
            isbn: ISBN being fetched
            parsed_data: Parsed JSON from Decodo's amazon_product API

        Returns:
            CachedBook instance
        """
        # Extract title
        title = parsed_data.get('name') or parsed_data.get('title')

        # Extract authors - Decodo typically uses 'by_line' or 'authors'
        authors = None
        if 'by_line' in parsed_data:
            authors = parsed_data['by_line']
        elif 'authors' in parsed_data:
            authors_list = parsed_data['authors']
            if isinstance(authors_list, list):
                authors = ', '.join(authors_list)
            else:
                authors = authors_list

        # Extract binding/format
        binding = parsed_data.get('format') or parsed_data.get('binding')

        # Extract publisher
        publisher = parsed_data.get('publisher')

        # Extract publication year from publication_date
        pub_year = None
        pub_date = parsed_data.get('publication_date')
        if pub_date:
            # Try to extract year from date string
            import re
            year_match = re.search(r'\b(19|20)\d{2}\b', str(pub_date))
            if year_match:
                try:
                    pub_year = int(year_match.group(0))
                except (ValueError, TypeError):
                    pass

        # Extract page count
        page_count = None
        if 'number_of_pages' in parsed_data:
            try:
                page_count = int(parsed_data['number_of_pages'])
            except (ValueError, TypeError):
                pass
        elif 'page_count' in parsed_data:
            try:
                page_count = int(parsed_data['page_count'])
            except (ValueError, TypeError):
                pass

        # Extract language
        language = parsed_data.get('language')

        # Extract cover image URL
        cover_url = None
        if 'images' in parsed_data and isinstance(parsed_data['images'], list):
            if len(parsed_data['images']) > 0:
                cover_url = parsed_data['images'][0]
        elif 'image' in parsed_data:
            cover_url = parsed_data['image']
        elif 'main_image' in parsed_data:
            cover_url = parsed_data['main_image']

        # Extract description
        description = parsed_data.get('description')

        # Extract ISBNs
        isbn13 = parsed_data.get('isbn13') or parsed_data.get('isbn_13')
        isbn10 = parsed_data.get('isbn10') or parsed_data.get('isbn_10')

        # Fall back to the input ISBN if not found in data
        if not isbn13 and len(isbn) == 13:
            isbn13 = isbn
        if not isbn10 and len(isbn) == 10:
            isbn10 = isbn

        return CachedBook(
            isbn=isbn,
            title=title,
            authors=authors,
            publisher=publisher,
            publication_year=pub_year,
            binding=binding,
            page_count=page_count,
            language=language,
            isbn13=isbn13,
            isbn10=isbn10,
            thumbnail_url=cover_url,
            description=description,
            source='amazon_decodo'
        )

    def _load_isbns_from_file(self, isbn_file: Path) -> List[str]:
        """Load ISBNs from file, one per line."""
        isbns = []

        with open(isbn_file, 'r') as f:
            for line in f:
                isbn = line.strip()
                if isbn and not isbn.startswith('#'):
                    isbns.append(isbn)

        return isbns

    def _print_progress(self, current: int, total: int):
        """Print progress update."""
        elapsed = time.time() - self.start_time
        rate = current / elapsed if elapsed > 0 else 0

        logger.info("")
        logger.info(f"Progress: {current}/{total} books processed")
        logger.info(f"  Collected: {self.collected}")
        logger.info(f"  Skipped: {self.skipped}")
        logger.info(f"  Failed: {self.failed}")
        logger.info(f"  Rate: {rate:.1f} books/sec")
        logger.info(f"  Estimated time remaining: {(total - current) / rate / 60:.1f} minutes" if rate > 0 else "")
        logger.info("")

    def _print_final_report(self, total: int):
        """Print final collection report."""
        elapsed = time.time() - self.start_time
        rate = total / elapsed if elapsed > 0 else 0

        logger.info("")
        logger.info("=" * 70)
        logger.info("COLLECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total processed: {total}")
        logger.info(f"Successfully collected: {self.collected}")
        logger.info(f"Skipped (already in cache): {self.skipped}")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)")
        logger.info(f"Average time per book: {elapsed / total:.2f} seconds")
        logger.info(f"Average rate: {rate:.1f} books/sec")
        logger.info("")

        # Cache statistics
        stats = self.cache_db.get_stats()
        logger.info(f"Cache now has {stats['total_books']} books")

        if 'by_source' in stats:
            logger.info("  By source:")
            for source, count in stats['by_source'].items():
                logger.info(f"    {source}: {count}")

        logger.info("")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Fast metadata collection using Decodo/Amazon'
    )
    parser.add_argument('--isbn-file', type=Path,
                       help='File containing ISBNs (one per line)')
    parser.add_argument('--isbn', type=str,
                       help='Single ISBN to collect')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of books to collect')
    parser.add_argument('--rate-limit', type=int, default=30,
                       help='Max requests per second (default: 30, use 100+ for advanced credits)')
    parser.add_argument('--include-existing', action='store_true',
                       help='Re-fetch ISBNs already in cache')

    args = parser.parse_args()

    # Validate arguments
    if not args.isbn_file and not args.isbn:
        parser.error("Must provide either --isbn-file or --isbn")

    # Get Decodo credentials from environment
    decodo_username = os.environ.get('DECODO_AUTHENTICATION')
    decodo_password = os.environ.get('DECODO_PASSWORD')

    if not decodo_username or not decodo_password:
        logger.error("Missing Decodo credentials!")
        logger.error("Set DECODO_AUTHENTICATION and DECODO_PASSWORD environment variables")
        sys.exit(1)

    # Create collector
    collector = FastMetadataCollector(
        decodo_username=decodo_username,
        decodo_password=decodo_password,
        rate_limit=args.rate_limit,
        skip_existing=not args.include_existing
    )

    try:
        if args.isbn:
            # Single ISBN
            logger.info(f"Collecting metadata for ISBN: {args.isbn}")
            success = collector.collect_isbn(args.isbn)

            if success:
                logger.info(f"✓ Successfully collected {args.isbn}")
                book = collector.cache_db.get_book(args.isbn)
                if book:
                    logger.info(f"  Title: {book.title}")
                    logger.info(f"  Authors: {book.authors}")
                    logger.info(f"  Year: {book.publication_year}")
                    logger.info(f"  Binding: {book.binding}")
                    logger.info(f"  Source: {book.source}")
            else:
                logger.error(f"✗ Failed to collect {args.isbn}")
                sys.exit(1)

        else:
            # File of ISBNs
            if not args.isbn_file.exists():
                logger.error(f"ISBN file not found: {args.isbn_file}")
                sys.exit(1)

            collector.collect_from_file(args.isbn_file, args.limit)

    except KeyboardInterrupt:
        logger.info("\n\nCollection interrupted by user")
        collector._print_final_report(collector.collected + collector.skipped + collector.failed)
        sys.exit(1)

    except Exception as e:
        logger.error(f"Collection failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
