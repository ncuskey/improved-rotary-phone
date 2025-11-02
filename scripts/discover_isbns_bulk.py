#!/usr/bin/env python3
"""
Bulk ISBN discovery for Week 3 scale-up.

Discovers ISBNs from multiple sources to build a large metadata cache:
- Major publisher ISBN ranges
- ISBN-13 prefix patterns for US publishers
- Sequential ISBN generation with validation

Target: 5,000-10,000 ISBNs for metadata collection
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import List, Set


class BulkISBNDiscovery:
    """
    Discover ISBNs at scale using publisher prefixes and ISBN patterns.

    Strategy:
    1. Major US Publisher Ranges (978-0 and 978-1 prefixes)
    2. Generate sequential ISBNs within known valid ranges
    3. Randomize to avoid API rate limit patterns
    """

    # Major US publisher ISBN-13 prefixes (978-0-XXX and 978-1-XXX)
    PUBLISHER_PREFIXES = {
        # Penguin Random House family
        "penguin_random_house": [
            "978037",  # Knopf, Pantheon, Random House
            "97803994",  # Berkley, Putnam, Penguin
            "97803995",  # Dutton, Viking, Plume
            "9780307",  # Vintage, Anchor, Broadway
            "9780385",  # Doubleday, Delacorte
            "9780345",  # Ballantine, Del Rey
        ],

        # HarperCollins
        "harpercollins": [
            "978006",  # HarperCollins main
            "9780061",  # Harper Perennial
            "9780062",  # HarperOne, Ecco
            "9780063",  # Harper Paperbacks
        ],

        # Simon & Schuster
        "simon_schuster": [
            "9780743",  # Simon & Schuster
            "9781416",  # Atria, Gallery
            "9781439",  # Pocket Books
            "9781501",  # Scribner
            "9781982",  # Simon & Schuster main
        ],

        # Hachette Book Group
        "hachette": [
            "9780316",  # Little, Brown
            "9780446",  # Grand Central
            "9781538",  # Grand Central Publishing
            "9781455",  # FaithWords, Forever
        ],

        # Macmillan Publishers
        "macmillan": [
            "9780312",  # St. Martin's Press
            "9780765",  # Tor, Forge
            "9781250",  # Macmillan main
        ],

        # Scholastic
        "scholastic": [
            "9780545",  # Scholastic main
            "9780590",  # Scholastic Press
            "9781338",  # Graphix, Orchard
        ],

        # Houghton Mifflin Harcourt
        "hmh": [
            "9780544",  # HMH Books
            "9780547",  # Mariner Books
            "9780618",  # Houghton Mifflin
        ],

        # Academic & Technical
        "academic": [
            "9780393",  # W. W. Norton
            "9780262",  # MIT Press
            "9780199",  # Oxford University Press
            "9780226",  # University of Chicago Press
        ],

        # Independent & Small Press
        "independent": [
            "9781609",  # Berrett-Koehler
            "9781603",  # Chelsea Green
            "9781632",  # Melville House
        ],
    }

    def __init__(self, target_count: int = 10000):
        """
        Initialize bulk ISBN discovery.

        Args:
            target_count: Target number of ISBNs to discover
        """
        self.target_count = target_count
        self.discovered_isbns: Set[str] = set()

    def calculate_isbn13_checksum(self, isbn12: str) -> str:
        """
        Calculate ISBN-13 check digit.

        Args:
            isbn12: First 12 digits of ISBN-13

        Returns:
            Complete 13-digit ISBN
        """
        if len(isbn12) != 12:
            raise ValueError("ISBN-12 must be exactly 12 digits")

        # ISBN-13 checksum: sum of (digit * weight) where weights alternate 1,3,1,3...
        total = sum(int(digit) * (1 if i % 2 == 0 else 3)
                   for i, digit in enumerate(isbn12))

        check_digit = (10 - (total % 10)) % 10
        return isbn12 + str(check_digit)

    def generate_isbns_for_prefix(self, prefix: str, count: int) -> List[str]:
        """
        Generate valid ISBNs for a given prefix.

        Args:
            prefix: ISBN prefix (7-10 digits)
            count: Number of ISBNs to generate

        Returns:
            List of valid ISBN-13s
        """
        isbns = []
        prefix_len = len(prefix)
        remaining_digits = 12 - prefix_len  # 12 digits before checksum

        # Generate sequential numbers for remaining digits
        max_value = 10 ** remaining_digits

        # Use random sampling to avoid sequential patterns
        samples = random.sample(range(max_value), min(count, max_value))

        for num in samples:
            # Pad to correct length
            suffix = str(num).zfill(remaining_digits)
            isbn12 = prefix + suffix

            # Calculate checksum
            isbn13 = self.calculate_isbn13_checksum(isbn12)
            isbns.append(isbn13)

        return isbns

    def discover_bulk_isbns(self) -> List[str]:
        """
        Discover ISBNs across all publisher categories.

        Returns:
            List of discovered ISBN-13s
        """
        print(f"Starting bulk ISBN discovery...")
        print(f"Target: {self.target_count:,} ISBNs")
        print()

        # Calculate ISBNs per prefix
        total_prefixes = sum(len(prefixes) for prefixes in self.PUBLISHER_PREFIXES.values())
        isbns_per_prefix = max(1, self.target_count // total_prefixes)

        # Generate ISBNs for each publisher category
        for category, prefixes in self.PUBLISHER_PREFIXES.items():
            print(f"Discovering ISBNs for {category}...")

            for prefix in prefixes:
                batch = self.generate_isbns_for_prefix(prefix, isbns_per_prefix)
                self.discovered_isbns.update(batch)
                print(f"  {prefix}: Generated {len(batch)} ISBNs")

        # Convert to sorted list
        isbn_list = sorted(list(self.discovered_isbns))

        print()
        print(f"✓ Discovered {len(isbn_list):,} unique ISBNs")
        print()

        # Statistics by publisher
        print("Distribution by publisher:")
        for category, prefixes in self.PUBLISHER_PREFIXES.items():
            category_count = sum(1 for isbn in isbn_list
                                if any(isbn.startswith(p) for p in prefixes))
            print(f"  {category}: {category_count:,} ISBNs")

        return isbn_list

    def save_to_file(self, isbn_list: List[str], output_file: Path):
        """Save ISBN list to file."""
        with open(output_file, 'w') as f:
            for isbn in isbn_list:
                f.write(f"{isbn}\n")

        print()
        print(f"✓ Saved {len(isbn_list):,} ISBNs to {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Discover ISBNs at scale for bulk metadata collection'
    )
    parser.add_argument('--count', type=int, default=10000,
                       help='Target number of ISBNs to discover (default: 10000)')
    parser.add_argument('--output', type=Path, default=Path('/tmp/bulk_isbns.txt'),
                       help='Output file path')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Create multiple batch files of this size')

    args = parser.parse_args()

    # Discover ISBNs
    discoverer = BulkISBNDiscovery(target_count=args.count)
    isbn_list = discoverer.discover_bulk_isbns()

    # Save to file(s)
    if args.batch_size and args.batch_size < len(isbn_list):
        # Create multiple batch files
        num_batches = (len(isbn_list) + args.batch_size - 1) // args.batch_size

        print()
        print(f"Creating {num_batches} batch files of ~{args.batch_size} ISBNs each...")

        for i in range(num_batches):
            start_idx = i * args.batch_size
            end_idx = min((i + 1) * args.batch_size, len(isbn_list))
            batch = isbn_list[start_idx:end_idx]

            batch_file = args.output.parent / f"{args.output.stem}_batch{i+1}.txt"
            discoverer.save_to_file(batch, batch_file)
    else:
        # Save as single file
        discoverer.save_to_file(isbn_list, args.output)

    print()
    print("=" * 70)
    print("BULK ISBN DISCOVERY COMPLETE")
    print("=" * 70)
    print(f"Total ISBNs: {len(isbn_list):,}")
    print(f"Ready for metadata collection")
    print()


if __name__ == '__main__':
    main()
