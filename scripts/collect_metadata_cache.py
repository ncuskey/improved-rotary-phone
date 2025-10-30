#!/usr/bin/env python3
"""
Metadata-only collector for fast ISBN lookups.

Collects lightweight book metadata from Google Books and OpenLibrary
WITHOUT expensive eBay sold comp data. Stores results in metadata_cache.db.

This collector is 6-10x faster than the training data collector because
it skips eBay API calls.

Usage:
    python3 scripts/collect_metadata_cache.py --isbn-file isbns.txt --limit 1000
    python3 scripts/collect_metadata_cache.py --isbn 9780316769174
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.metadata_cache_db import CachedBook, MetadataCacheDB
from shared import metadata

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetadataCollector:
    """
    Collect lightweight book metadata for cache.

    Fetches metadata from Google Books and OpenLibrary only.
    Does NOT fetch eBay sold comps or market analysis.

    Average collection time: 5-10 seconds per book
    API calls per book: 1-2 (vs 3-6 for training data)
    """

    def __init__(self, skip_existing: bool = True):
        """
        Initialize metadata collector.

        Args:
            skip_existing: If True, skip ISBNs already in cache
        """
        self.cache_db = MetadataCacheDB()
        self.session = metadata.create_http_session()
        self.skip_existing = skip_existing

        # Statistics
        self.collected = 0
        self.skipped = 0
        self.failed = 0
        self.start_time = None

    def collect_from_file(self, isbn_file: Path, limit: Optional[int] = None):
        """
        Collect metadata for ISBNs from file.

        Args:
            isbn_file: Path to file with ISBNs (one per line)
            limit: Maximum number of books to collect
        """
        logger.info("=" * 70)
        logger.info("METADATA CACHE COLLECTION")
        logger.info("=" * 70)
        logger.info(f"ISBN file: {isbn_file}")
        logger.info(f"Limit: {limit or 'unlimited'}")
        logger.info(f"Skip existing: {self.skip_existing}")
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

            # Rate limiting (be nice to APIs)
            time.sleep(0.5)

        # Final report
        self._print_final_report(len(isbns))

    def collect_isbn(self, isbn: str) -> bool:
        """
        Collect metadata for a single ISBN.

        Args:
            isbn: ISBN to collect

        Returns:
            True if successfully collected and stored, False otherwise
        """
        try:
            # Fetch from Google Books using existing shared.metadata module
            book_data = metadata.fetch_google_books(isbn, session=self.session)

            if not book_data:
                return False

            # Convert to CachedBook format
            cached_book = self._convert_to_cached_book(isbn, book_data)

            # Try to get binding from OpenLibrary if not available
            if not cached_book.binding:
                binding = metadata.binding_from_openlibrary(isbn, session=self.session)
                if binding:
                    cached_book.binding = binding

            # Store if we got anything useful
            if cached_book and cached_book.title:
                return self.cache_db.store_book(cached_book)

            return False

        except Exception as e:
            logger.error(f"Error collecting {isbn}: {e}")
            return False

    def _convert_to_cached_book(self, isbn: str, book_data: Dict) -> CachedBook:
        """
        Convert shared.metadata format to CachedBook format.

        Args:
            isbn: ISBN being fetched
            book_data: Data from shared.metadata.fetch_google_books()

        Returns:
            CachedBook instance
        """
        # Extract authors
        authors_list = book_data.get('authors', [])
        if isinstance(authors_list, str):
            authors_list = [authors_list]
        authors = ', '.join(authors_list) if authors_list else None

        # Extract publisher (ensure it's a string)
        publisher = book_data.get('publisher')
        if isinstance(publisher, dict):
            # Sometimes publisher is a dict, extract the name
            publisher = publisher.get('name') if publisher else None
        if isinstance(publisher, list):
            # Or it might be a list
            publisher = publisher[0] if publisher else None
        publisher = str(publisher) if publisher else None

        # Extract binding using the existing helper
        binding = metadata.binding_from_googlebooks(book_data)

        # Get thumbnail (ensure it's a string)
        thumbnail = book_data.get('thumbnail_url') or book_data.get('cover_url')
        if isinstance(thumbnail, dict):
            thumbnail = thumbnail.get('url') if thumbnail else None
        thumbnail = str(thumbnail) if thumbnail else None

        # Get ISBNs
        isbn13 = book_data.get('isbn_13')
        isbn10 = book_data.get('isbn_10')

        # Fallback: if no ISBNs from data, use the input ISBN
        if not isbn13 and not isbn10:
            if len(isbn) == 13:
                isbn13 = isbn
            elif len(isbn) == 10:
                isbn10 = isbn

        # Extract publication year (ensure it's an int)
        pub_year = book_data.get('publication_year')
        if isinstance(pub_year, str):
            try:
                pub_year = int(pub_year)
            except (ValueError, TypeError):
                pub_year = None

        # Extract page count (ensure it's an int)
        page_count = book_data.get('page_count')
        if isinstance(page_count, str):
            try:
                page_count = int(page_count)
            except (ValueError, TypeError):
                page_count = None

        return CachedBook(
            isbn=isbn,
            title=str(book_data.get('title')) if book_data.get('title') else None,
            authors=authors,
            publisher=publisher,
            publication_year=pub_year,
            binding=binding,
            page_count=page_count,
            language=str(book_data.get('language')) if book_data.get('language') else None,
            isbn13=str(isbn13) if isbn13 else None,
            isbn10=str(isbn10) if isbn10 else None,
            thumbnail_url=thumbnail,
            description=str(book_data.get('description')) if book_data.get('description') else None,
            source='google_books'
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
        logger.info("")

    def _print_final_report(self, total: int):
        """Print final collection report."""
        elapsed = time.time() - self.start_time

        logger.info("")
        logger.info("=" * 70)
        logger.info("COLLECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total processed: {total}")
        logger.info(f"Successfully collected: {self.collected}")
        logger.info(f"Skipped (already in cache): {self.skipped}")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds")
        logger.info(f"Average time per book: {elapsed / total:.1f} seconds")
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
        description='Collect lightweight book metadata for cache'
    )
    parser.add_argument('--isbn-file', type=Path,
                       help='File containing ISBNs (one per line)')
    parser.add_argument('--isbn', type=str,
                       help='Single ISBN to collect')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of books to collect')
    parser.add_argument('--include-existing', action='store_true',
                       help='Re-fetch ISBNs already in cache')

    args = parser.parse_args()

    # Validate arguments
    if not args.isbn_file and not args.isbn:
        parser.error("Must provide either --isbn-file or --isbn")

    # Create collector
    collector = MetadataCollector(skip_existing=not args.include_existing)

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
