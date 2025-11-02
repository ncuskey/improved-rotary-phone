"""
Discover ISBNs that have both signed and unsigned eBay sold comps.

This script validates that books have BOTH signed and unsigned versions available
on eBay before adding them to the collection list. This prevents the issue where
we collect signed books but can't find unsigned counterparts.

Usage:
    # Search by author
    python3 scripts/discover_signable_isbns.py --author "Lee Child" --limit 50

    # Search by ISBN list
    python3 scripts/discover_signable_isbns.py --isbn-file /tmp/candidate_isbns.txt

    # Search popular books
    python3 scripts/discover_signable_isbns.py --popular --limit 100
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

from shared.ebay_sold_comps import EbaySoldComps
from shared.metadata import fetch_metadata, create_http_session
from shared.utils import normalise_isbn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Popular authors known to have signing tours and signed editions
POPULAR_AUTHORS = [
    # Thriller/Mystery
    "Lee Child", "James Patterson", "Michael Connelly", "Harlan Coben",
    "David Baldacci", "John Grisham", "Karin Slaughter", "Tana French",

    # Literary Fiction
    "Margaret Atwood", "Colson Whitehead", "Jennifer Egan", "Jonathan Franzen",
    "Celeste Ng", "Sally Rooney", "Ann Patchett", "Jesmyn Ward",

    # Fantasy/Sci-Fi
    "Brandon Sanderson", "Patrick Rothfuss", "N.K. Jemisin", "Andy Weir",
    "Blake Crouch", "Pierce Brown", "V.E. Schwab", "Leigh Bardugo",

    # Horror
    "Stephen King", "Joe Hill", "Paul Tremblay", "Josh Malerman",
    "Riley Sager", "Grady Hendrix",

    # Historical
    "Ken Follett", "Hilary Mantel", "Anthony Doerr", "Kristin Hannah",
    "Erik Larson", "Paula McLain",

    # Non-Fiction/Memoir
    "Malcolm Gladwell", "Michelle Obama", "Trevor Noah", "Tara Westover",
    "Matthew McConaughey", "Prince Harry",
]


class SignableISBNDiscoverer:
    """
    Discovers ISBNs that have both signed and unsigned eBay sold comps.

    This ensures we only collect books where A/B comparison is possible.
    """

    def __init__(
        self,
        min_signed_comps: int = 5,
        min_unsigned_comps: int = 5,
        min_total_comps: int = 15
    ):
        """
        Initialize ISBN discoverer.

        Args:
            min_signed_comps: Minimum signed sold comps required
            min_unsigned_comps: Minimum unsigned sold comps required
            min_total_comps: Minimum total volume (helps ensure data quality)
        """
        self.ebay = EbaySoldComps()
        self.session = create_http_session()

        self.min_signed_comps = min_signed_comps
        self.min_unsigned_comps = min_unsigned_comps
        self.min_total_comps = min_total_comps

        # Stats
        self.stats = {
            'checked': 0,
            'valid_pairs': 0,
            'insufficient_signed': 0,
            'insufficient_unsigned': 0,
            'insufficient_total': 0,
            'failed': 0
        }

    def check_signed_only(self, isbn: str) -> Optional[Dict]:
        """
        Phase 1: Check if an ISBN has signed sold comps only.

        This is the first phase of the two-phase discovery process.
        We find books with signed copies (indicating popular books),
        then later check which also have unsigned counterparts.

        Args:
            isbn: ISBN to check

        Returns:
            Dict with signed data, or None if insufficient signed comps
        """
        try:
            # Check signed comps only
            signed_result = self.ebay.get_sold_comps(
                gtin=isbn,
                fallback_to_estimate=False,
                max_samples=10,
                include_signed=True  # Include signed copies
            )

            if not signed_result or signed_result['count'] < self.min_signed_comps:
                self.stats['insufficient_signed'] += 1
                return None

            # Valid signed book found!
            self.stats['valid_pairs'] += 1  # Counting signed books found

            # Fetch metadata
            metadata = fetch_metadata(isbn, session=self.session)

            return {
                'isbn': isbn,
                'signed_count': signed_result['count'],
                'signed_median': signed_result['median'],
                'title': metadata.get('title', 'Unknown'),
                'author': metadata.get('author', 'Unknown'),
                'checked_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"  {isbn}: Error checking signed: {e}")
            self.stats['failed'] += 1
            return None

    def check_unsigned_only(self, isbn: str) -> Optional[Dict]:
        """
        Phase 2: Check if a known-signed ISBN also has unsigned comps.

        This is the second phase - we already know this ISBN has signed copies,
        now we check if it also has unsigned counterparts for A/B testing.

        Args:
            isbn: ISBN to check (known to have signed comps)

        Returns:
            Dict with unsigned data, or None if insufficient unsigned comps
        """
        try:
            # Check unsigned comps only
            unsigned_result = self.ebay.get_sold_comps(
                gtin=isbn,
                fallback_to_estimate=False,
                max_samples=10,
                include_signed=False  # Exclude signed copies
            )

            if not unsigned_result or unsigned_result['count'] < self.min_unsigned_comps:
                self.stats['insufficient_unsigned'] += 1
                return None

            # Has unsigned counterpart!
            self.stats['valid_pairs'] += 1

            return {
                'isbn': isbn,
                'unsigned_count': unsigned_result['count'],
                'unsigned_median': unsigned_result['median'],
                'checked_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"  {isbn}: Error checking unsigned: {e}")
            self.stats['failed'] += 1
            return None

    def check_isbn_signable(self, isbn: str) -> Optional[Dict]:
        """
        Check if an ISBN has both signed and unsigned sold comps.

        This is the combined check (both phases in one call).
        Use this for small-scale testing or when you have pre-filtered candidates.

        Args:
            isbn: ISBN to check

        Returns:
            Dict with validation results, or None if not signable
        """
        try:
            # Check signed comps
            signed_result = self.ebay.get_sold_comps(
                gtin=isbn,
                fallback_to_estimate=False,
                max_samples=10,
                include_signed=True  # Include signed copies
            )

            # Check unsigned comps
            unsigned_result = self.ebay.get_sold_comps(
                gtin=isbn,
                fallback_to_estimate=False,
                max_samples=10,
                include_signed=False  # Exclude signed copies
            )

            # Validate both exist
            if not signed_result or not unsigned_result:
                if not signed_result:
                    self.stats['insufficient_signed'] += 1
                if not unsigned_result:
                    self.stats['insufficient_unsigned'] += 1
                return None

            signed_count = signed_result['count']
            unsigned_count = unsigned_result['count']
            total_count = signed_count + unsigned_count

            # Check minimums
            if signed_count < self.min_signed_comps:
                self.stats['insufficient_signed'] += 1
                return None

            if unsigned_count < self.min_unsigned_comps:
                self.stats['insufficient_unsigned'] += 1
                return None

            if total_count < self.min_total_comps:
                self.stats['insufficient_total'] += 1
                return None

            # Valid pair!
            self.stats['valid_pairs'] += 1

            # Fetch metadata
            metadata = fetch_metadata(isbn, session=self.session)

            return {
                'isbn': isbn,
                'signed_count': signed_count,
                'unsigned_count': unsigned_count,
                'total_count': total_count,
                'signed_median': signed_result['median'],
                'unsigned_median': unsigned_result['median'],
                'premium_amount': signed_result['median'] - unsigned_result['median'],
                'premium_percent': ((signed_result['median'] - unsigned_result['median']) / unsigned_result['median']) * 100,
                'title': metadata.get('title', 'Unknown'),
                'author': metadata.get('author', 'Unknown'),
                'checked_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"  {isbn}: Error checking: {e}")
            self.stats['failed'] += 1
            return None

    def discover_from_author(
        self,
        author: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Discover signable ISBNs for a specific author.

        This searches eBay for books by the author and validates
        that both signed and unsigned versions exist.

        Args:
            author: Author name to search
            limit: Maximum ISBNs to find

        Returns:
            List of valid ISBN dicts
        """
        logger.info(f"Discovering signable ISBNs for: {author}")
        logger.info(f"  Minimum requirements: {self.min_signed_comps}+ signed, {self.min_unsigned_comps}+ unsigned")
        logger.info("")

        # TODO: Implement eBay product search by author
        # For now, we'll need to provide candidate ISBNs via --isbn-file
        # This would require eBay Product API search functionality

        logger.warning("Author search not yet implemented")
        logger.info("Please use --isbn-file with candidate ISBNs for now")

        return []

    def discover_from_isbn_list(
        self,
        isbn_file: Path,
        limit: Optional[int] = None,
        mode: str = "both"
    ) -> List[Dict]:
        """
        Validate ISBNs from a file.

        Args:
            isbn_file: Path to file with one ISBN per line
            limit: Maximum ISBNs to check
            mode: Check mode - "both" (signed+unsigned), "signed_only" (phase 1), "unsigned_only" (phase 2)

        Returns:
            List of valid ISBN dicts
        """
        # Set mode-specific messaging
        if mode == "signed_only":
            logger.info(f"PHASE 1: Finding ISBNs with signed sold comps")
            logger.info(f"  Minimum requirement: {self.min_signed_comps}+ signed comps")
        elif mode == "unsigned_only":
            logger.info(f"PHASE 2: Validating unsigned comps for known-signed ISBNs")
            logger.info(f"  Minimum requirement: {self.min_unsigned_comps}+ unsigned comps")
        else:
            logger.info(f"Validating ISBNs from: {isbn_file}")
            logger.info(f"  Minimum requirements: {self.min_signed_comps}+ signed, {self.min_unsigned_comps}+ unsigned")
        logger.info("")

        # Read ISBNs
        isbns = []
        with open(isbn_file) as f:
            for line in f:
                isbn = line.strip()
                if isbn and not isbn.startswith('#'):
                    isbns.append(normalise_isbn(isbn))

        if limit:
            isbns = isbns[:limit]

        logger.info(f"Checking {len(isbns)} candidate ISBNs")
        logger.info("")

        # Check each ISBN based on mode
        valid_isbns = []
        for i, isbn in enumerate(isbns, 1):
            logger.info(f"[{i}/{len(isbns)}] Checking {isbn}")
            self.stats['checked'] += 1

            # Select appropriate check method
            if mode == "signed_only":
                result = self.check_signed_only(isbn)
            elif mode == "unsigned_only":
                result = self.check_unsigned_only(isbn)
            else:
                result = self.check_isbn_signable(isbn)

            # Display results based on mode
            if result:
                if mode == "signed_only":
                    logger.info(f"  ✓ HAS SIGNED COMPS")
                    logger.info(f"    Signed: {result['signed_count']} comps (${result['signed_median']:.2f} median)")
                    logger.info(f"    Title: {result['title']} by {result['author']}")
                elif mode == "unsigned_only":
                    logger.info(f"  ✓ HAS UNSIGNED COMPS")
                    logger.info(f"    Unsigned: {result['unsigned_count']} comps (${result['unsigned_median']:.2f} median)")
                else:
                    logger.info(f"  ✓ VALID PAIR")
                    logger.info(f"    Signed: {result['signed_count']} comps (${result['signed_median']:.2f} median)")
                    logger.info(f"    Unsigned: {result['unsigned_count']} comps (${result['unsigned_median']:.2f} median)")
                    logger.info(f"    Premium: ${result['premium_amount']:.2f} ({result['premium_percent']:.1f}%)")
                    logger.info(f"    Title: {result['title']}")
                valid_isbns.append(result)
            else:
                logger.info(f"  ✗ Insufficient comps")

            # Rate limit
            time.sleep(1)

            # Progress update every 10 books
            if i % 10 == 0:
                logger.info("")
                if mode == "signed_only":
                    logger.info(f"Progress: {self.stats['valid_pairs']}/{len(isbns)} with signed comps found")
                elif mode == "unsigned_only":
                    logger.info(f"Progress: {self.stats['valid_pairs']}/{len(isbns)} with unsigned comps found")
                else:
                    logger.info(f"Progress: {self.stats['valid_pairs']}/{len(isbns)} valid pairs found")
                logger.info("")

        return valid_isbns

    def discover_popular_books(self, limit: int = 100) -> List[Dict]:
        """
        Discover signable ISBNs from popular books.

        This cycles through popular authors and checks their books.

        Args:
            limit: Maximum ISBNs to find

        Returns:
            List of valid ISBN dicts
        """
        logger.info("Discovering signable ISBNs from popular authors")
        logger.info(f"  Target: {limit} valid pairs")
        logger.info("")

        # TODO: Implement bestseller/popular book search
        # Would need to:
        # 1. Query NYT Bestseller API or similar
        # 2. Get ISBNs from results
        # 3. Validate each ISBN

        logger.warning("Popular book search not yet implemented")
        logger.info("Please use --isbn-file with candidate ISBNs for now")

        return []

    def save_results(
        self,
        valid_isbns: List[Dict],
        output_file: Path
    ):
        """
        Save valid ISBNs to file.

        Args:
            valid_isbns: List of valid ISBN dicts
            output_file: Path to save results
        """
        # Save as JSON with full details
        json_file = output_file.with_suffix('.json')
        with open(json_file, 'w') as f:
            json.dump(valid_isbns, f, indent=2)
        logger.info(f"Saved detailed results to: {json_file}")

        # Save as simple ISBN list (for collection scripts)
        txt_file = output_file.with_suffix('.txt')
        with open(txt_file, 'w') as f:
            for item in valid_isbns:
                f.write(f"{item['isbn']}\n")
        logger.info(f"Saved ISBN list to: {txt_file}")

    def print_summary(self):
        """Print discovery summary."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("DISCOVERY SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total checked: {self.stats['checked']}")
        logger.info(f"Valid pairs: {self.stats['valid_pairs']}")
        logger.info("")
        logger.info("Rejection reasons:")
        logger.info(f"  Insufficient signed: {self.stats['insufficient_signed']}")
        logger.info(f"  Insufficient unsigned: {self.stats['insufficient_unsigned']}")
        logger.info(f"  Insufficient total volume: {self.stats['insufficient_total']}")
        logger.info(f"  Failed/error: {self.stats['failed']}")
        logger.info("")

        if self.stats['checked'] > 0:
            success_rate = (self.stats['valid_pairs'] / self.stats['checked']) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover ISBNs with both signed and unsigned eBay sold comps"
    )

    # Search methods
    search_group = parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument(
        "--author",
        type=str,
        help="Search for books by specific author"
    )
    search_group.add_argument(
        "--isbn-file",
        type=str,
        help="Validate ISBNs from file (one per line)"
    )
    search_group.add_argument(
        "--popular",
        action="store_true",
        help="Search popular/bestselling books"
    )

    # Options
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of valid ISBNs to find"
    )
    parser.add_argument(
        "--min-signed",
        type=int,
        default=5,
        help="Minimum signed sold comps required (default: 5)"
    )
    parser.add_argument(
        "--min-unsigned",
        type=int,
        default=5,
        help="Minimum unsigned sold comps required (default: 5)"
    )
    parser.add_argument(
        "--min-total",
        type=int,
        default=15,
        help="Minimum total sold comps required (default: 15)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="/tmp/signable_isbns",
        help="Output file path (without extension)"
    )

    # Two-phase workflow options
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--signed-only",
        action="store_true",
        help="Phase 1: Only check for signed comps (find books with signed editions)"
    )
    mode_group.add_argument(
        "--validate-unsigned",
        action="store_true",
        help="Phase 2: Validate unsigned comps for known-signed ISBNs"
    )

    args = parser.parse_args()

    # Initialize discoverer
    discoverer = SignableISBNDiscoverer(
        min_signed_comps=args.min_signed,
        min_unsigned_comps=args.min_unsigned,
        min_total_comps=args.min_total
    )

    # Determine discovery mode
    mode = "both"
    if args.signed_only:
        mode = "signed_only"
    elif args.validate_unsigned:
        mode = "unsigned_only"

    # Run discovery
    logger.info("=" * 70)
    if mode == "signed_only":
        logger.info("SIGNABLE ISBN DISCOVERY - PHASE 1")
    elif mode == "unsigned_only":
        logger.info("SIGNABLE ISBN DISCOVERY - PHASE 2")
    else:
        logger.info("SIGNABLE ISBN DISCOVERY")
    logger.info("=" * 70)
    logger.info("")

    valid_isbns = []

    if args.author:
        valid_isbns = discoverer.discover_from_author(args.author, limit=args.limit)
    elif args.isbn_file:
        valid_isbns = discoverer.discover_from_isbn_list(
            Path(args.isbn_file),
            limit=args.limit,
            mode=mode
        )
    elif args.popular:
        valid_isbns = discoverer.discover_popular_books(limit=args.limit or 100)

    # Save results
    if valid_isbns:
        output_path = Path(args.output)
        discoverer.save_results(valid_isbns, output_path)

    # Print summary
    discoverer.print_summary()

    return 0 if valid_isbns else 1


if __name__ == "__main__":
    sys.exit(main())
