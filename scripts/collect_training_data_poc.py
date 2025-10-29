"""
Phase 1 POC: Strategic Training Data Collection

Simplified proof-of-concept that collects 50-100 books from ONE category
to validate the approach before scaling to 2000+ books.

Usage:
    python3 scripts/collect_training_data_poc.py --category first_edition_hardcover --limit 100
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value.strip('"').strip("'")

from isbn_lot_optimizer.collection_strategies import CollectionStrategyManager
from isbn_lot_optimizer.training_db import TrainingDataManager
from shared.bookscouter import fetch_offers
from shared.ebay_sold_comps import get_sold_comps
from shared.metadata import fetch_metadata, create_http_session
from shared.utils import normalise_isbn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrainingDataCollectorPOC:
    """
    Phase 1 POC training data collector.

    Simplified collector that focuses on proving the concept:
    - Pick ONE category
    - Find candidate ISBNs on eBay
    - Collect multi-source data (eBay + Amazon/Decodo + Metadata)
    - Store in training_data.db
    - Limit to 50-100 books
    """

    def __init__(self, category: str, limit: int = 100):
        """
        Initialize POC collector.

        Args:
            category: Collection category to target
            limit: Maximum number of books to collect
        """
        self.category = category
        self.limit = limit

        self.strategy_mgr = CollectionStrategyManager()
        self.db = TrainingDataManager()

        self.target = self.strategy_mgr.get_target(category)
        if not self.target:
            raise ValueError(f"Unknown category: {category}")

        self.session = create_http_session()

        # Stats
        self.stats = {
            'searched': 0,
            'candidates_found': 0,
            'blacklisted': 0,
            'insufficient_comps': 0,
            'data_collection_failed': 0,
            'collected': 0
        }

    def find_candidate_isbns_simple(self) -> List[str]:
        """
        Find candidate ISBNs using simple eBay sold listings search.

        For POC, we'll use a simpler approach:
        1. Search eBay sold listings for the category keywords
        2. Extract ISBNs from titles/descriptions
        3. Filter by having good sold history

        Returns:
            List of ISBNs to collect
        """
        logger.info(f"Searching eBay for candidate books in category: {self.category}")

        # For POC, manually curated ISBNs for testing
        # In production, this would use eBay Browse API search

        # TODO: Implement eBay search
        # For now, return empty list and document that this needs eBay integration
        logger.warning("eBay ISBN discovery not implemented in POC - please provide ISBNs manually")
        return []

    def find_candidate_isbns_from_file(self, filepath: Path) -> List[str]:
        """
        Load candidate ISBNs from a file (one per line).

        For POC testing, you can create a file with ISBNs to collect.

        Args:
            filepath: Path to file with ISBNs (one per line)

        Returns:
            List of ISBNs
        """
        if not filepath.exists():
            logger.warning(f"ISBN file not found: {filepath}")
            return []

        isbns = []
        with open(filepath, 'r') as f:
            for line in f:
                isbn = normalise_isbn(line.strip())
                if isbn:
                    isbns.append(isbn)

        logger.info(f"Loaded {len(isbns)} ISBNs from {filepath}")
        return isbns

    def check_sold_comps(self, isbn: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if book has sufficient sold comps.

        Args:
            isbn: ISBN to check

        Returns:
            Tuple of (meets_threshold, market_data_dict)
        """
        try:
            # Fetch sold comps from eBay
            # Returns dict with keys: count, median, min, max, samples, is_estimate, source
            market_stats = get_sold_comps(isbn)

            if not market_stats or not market_stats.get('count'):
                return False, None

            sold_count = market_stats['count']
            meets_threshold = sold_count >= self.target.min_comps

            # Convert to dict for storage (normalize field names)
            market_dict = {
                'sold_count': sold_count,
                'sold_avg_price': market_stats.get('median', 0),  # Use median as avg
                'sold_median_price': market_stats.get('median', 0),
                'sold_min_price': market_stats.get('min', 0),
                'sold_max_price': market_stats.get('max', 0),
                'active_count': 0,  # Not available from get_sold_comps
                'active_median_price': None,
                'sell_through_rate': None,
                'source': market_stats.get('source', 'unknown'),
                'is_estimate': market_stats.get('is_estimate', True),
            }

            return meets_threshold, market_dict

        except Exception as e:
            logger.error(f"Failed to check comps for {isbn}: {e}")
            return False, None

    def collect_book_data(self, isbn: str) -> Optional[Dict]:
        """
        Collect all data for a book from multiple sources.

        Args:
            isbn: ISBN to collect

        Returns:
            Dict with all collected data, or None if collection failed
        """
        logger.info(f"Collecting data for {isbn}")

        try:
            # 1. eBay sold comps (ground truth for price)
            meets_threshold, market_data = self.check_sold_comps(isbn)

            if not meets_threshold:
                logger.warning(f"  {isbn}: Insufficient sold comps")
                self.stats['insufficient_comps'] += 1
                return None

            logger.info(f"  {isbn}: {market_data['sold_count']} sold comps found")

            # 2. Metadata (Google Books, OpenLibrary)
            metadata = fetch_metadata(isbn, self.session)
            if not metadata:
                logger.warning(f"  {isbn}: No metadata found")

            # 3. BookScouter data (Amazon rank, offers) - optional
            bookscouter_data = None
            try:
                # Check if API key is available
                api_key = os.environ.get('BOOKSCOUTER_API_KEY')
                if api_key:
                    bookscouter_result = fetch_offers(isbn, api_key=api_key)
                    if bookscouter_result:
                        bookscouter_data = {
                            'amazon_sales_rank': bookscouter_result.amazon_sales_rank,
                            'amazon_count': bookscouter_result.amazon_count,
                            'amazon_lowest_price': bookscouter_result.amazon_lowest_price,
                        }
                        logger.info(f"  {isbn}: Amazon rank {bookscouter_result.amazon_sales_rank or 'N/A'}")
                else:
                    logger.debug(f"  {isbn}: Skipping BookScouter (no API key)")
            except Exception as e:
                logger.warning(f"  {isbn}: BookScouter data failed: {e}")

            # Build complete record
            book_data = {
                'isbn': isbn,
                'metadata': metadata,
                'market': market_data,
                'bookscouter': bookscouter_data,
                'sold_avg_price': market_data['sold_avg_price'],
                'sold_count': market_data['sold_count'],
            }

            return book_data

        except Exception as e:
            logger.error(f"  {isbn}: Data collection failed: {e}")
            self.stats['data_collection_failed'] += 1
            return None

    def extract_physical_attributes(self, metadata: Optional[Dict]) -> tuple:
        """
        Extract physical attributes (cover_type, signed, printing) from metadata.

        Uses multiple sources:
        1. Collection category (primary)
        2. Title parsing for keywords
        3. Google Books binding field

        Args:
            metadata: Book metadata dict

        Returns:
            Tuple of (cover_type, signed, printing)
        """
        import re

        # Start with category inference (most reliable)
        cover_type = None
        signed = 0
        printing = None

        category_lower = self.category.lower()

        if 'hardcover' in category_lower:
            cover_type = 'Hardcover'
        elif 'mass_market' in category_lower:
            cover_type = 'Mass Market'
        elif 'paperback' in category_lower:
            cover_type = 'Paperback'

        if 'signed' in category_lower:
            signed = 1

        if 'first_edition' in category_lower:
            printing = '1st'

        # Parse metadata for additional hints
        if metadata:
            # Parse title for keywords
            title = metadata.get('title', '').lower()
            if title:
                # Cover type hints
                if not cover_type:
                    if re.search(r'\b(hardcover|hardback|hc)\b', title):
                        cover_type = 'Hardcover'
                    elif re.search(r'\bmass market\b', title):
                        cover_type = 'Mass Market'
                    elif re.search(r'\b(paperback|pb)\b', title):
                        cover_type = 'Paperback'

                # Signed hints
                if not signed and re.search(r'\b(signed|autographed)\b', title):
                    signed = 1

                # Edition hints
                if not printing:
                    if re.search(r'\b(first edition|1st edition|first printing)\b', title):
                        printing = '1st'

            # Check binding field (Google Books)
            binding = metadata.get('binding') or metadata.get('format')
            if not cover_type and binding:
                binding_lower = binding.lower()
                if 'hardcover' in binding_lower or 'hardback' in binding_lower:
                    cover_type = 'Hardcover'
                elif 'mass market' in binding_lower:
                    cover_type = 'Mass Market'
                elif 'paperback' in binding_lower:
                    cover_type = 'Paperback'

        return cover_type, signed, printing

    def store_book(self, book_data: Dict) -> bool:
        """
        Store collected book in training database.

        Args:
            book_data: Collected book data

        Returns:
            True if stored successfully
        """
        try:
            isbn = book_data['isbn']

            # Serialize JSON blobs
            metadata_json = json.dumps(book_data['metadata'] if book_data['metadata'] else {})
            market_json = json.dumps(book_data['market'])
            bookscouter_json = json.dumps(book_data['bookscouter']) if book_data['bookscouter'] else None

            # Extract physical attributes
            cover_type, signed, printing = self.extract_physical_attributes(book_data['metadata'])

            # Add to training database
            self.db.add_training_book(
                isbn=isbn,
                category=self.category,
                sold_avg_price=book_data['sold_avg_price'],
                sold_count=book_data['sold_count'],
                sold_median_price=book_data['market'].get('sold_median_price'),
                metadata_json=metadata_json,
                market_json=market_json,
                bookscouter_json=bookscouter_json,
                cover_type=cover_type,
                signed=signed,
                printing=printing
            )

            logger.info(f"  {isbn}: ✓ Stored in training database")
            return True

        except Exception as e:
            logger.error(f"  {isbn}: Failed to store: {e}")
            return False

    def run_collection(self, isbn_list: Optional[List[str]] = None, isbn_file: Optional[Path] = None) -> None:
        """
        Run the collection process.

        Args:
            isbn_list: Optional list of ISBNs to collect (for testing)
            isbn_file: Optional path to file with ISBNs
        """
        logger.info("=" * 70)
        logger.info("STRATEGIC TRAINING DATA COLLECTION - PHASE 1 POC")
        logger.info("=" * 70)
        logger.info(f"Category: {self.target.description}")
        logger.info(f"Target count: {self.limit} books")
        logger.info(f"Minimum comps: {self.target.min_comps}")
        logger.info("")

        # Get candidate ISBNs
        if isbn_list:
            candidates = isbn_list
        elif isbn_file:
            candidates = self.find_candidate_isbns_from_file(isbn_file)
        else:
            candidates = self.find_candidate_isbns_simple()

        if not candidates:
            logger.error("No candidate ISBNs found. Provide ISBNs via --isbn-list or --isbn-file")
            return

        logger.info(f"Found {len(candidates)} candidate ISBNs")
        logger.info("")

        # Process each candidate
        collected_count = 0

        for i, isbn in enumerate(candidates[:self.limit * 3], 1):  # Try 3x limit to account for failures
            if collected_count >= self.limit:
                break

            logger.info(f"[{i}/{len(candidates)}] Processing {isbn}")

            # Check blacklist
            if self.db.is_blacklisted(isbn):
                logger.info(f"  {isbn}: Skipping (blacklisted)")
                self.stats['blacklisted'] += 1
                continue

            # Collect data
            book_data = self.collect_book_data(isbn)

            if not book_data:
                # Blacklist failed ISBNs
                self.db.add_to_blacklist(isbn, 'collection_failed')
                continue

            # Store in database
            if self.store_book(book_data):
                collected_count += 1
                self.stats['collected'] += 1

                # Update target count
                self.db.update_target_count(self.category)

            # Rate limiting: 1 second between books
            time.sleep(1.0)

            # Progress update every 10 books
            if collected_count % 10 == 0:
                logger.info("")
                logger.info(f"Progress: {collected_count}/{self.limit} books collected")
                logger.info("")

        # Final statistics
        logger.info("")
        logger.info("=" * 70)
        logger.info("COLLECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Successfully collected: {self.stats['collected']} books")
        logger.info(f"Insufficient comps: {self.stats['insufficient_comps']}")
        logger.info(f"Data collection failed: {self.stats['data_collection_failed']}")
        logger.info(f"Blacklisted: {self.stats['blacklisted']}")
        logger.info("")

        # Database stats
        db_stats = self.db.get_stats()
        logger.info(f"Training database now has {db_stats['total_books']} books")
        logger.info(f"  - Signed books: {db_stats.get('signed_books', 0)}")
        logger.info(f"  - First editions: {db_stats.get('first_editions', 0)}")
        logger.info("")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Collect strategic training data (Phase 1 POC)')

    parser.add_argument(
        '--category',
        type=str,
        required=True,
        help='Collection category (e.g., first_edition_hardcover, signed_hardcover)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum number of books to collect (default: 100)'
    )

    parser.add_argument(
        '--isbn-file',
        type=str,
        help='Path to file with ISBNs to collect (one per line)'
    )

    parser.add_argument(
        '--isbn-list',
        type=str,
        nargs='+',
        help='List of ISBNs to collect (space-separated)'
    )

    args = parser.parse_args()

    # Create collector
    collector = TrainingDataCollectorPOC(
        category=args.category,
        limit=args.limit
    )

    # Run collection
    isbn_file = Path(args.isbn_file) if args.isbn_file else None
    collector.run_collection(
        isbn_list=args.isbn_list,
        isbn_file=isbn_file
    )


if __name__ == '__main__':
    main()
