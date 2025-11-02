#!/usr/bin/env python3
"""
Harvest real ISBNs from OpenLibrary.org

OpenLibrary has 20M+ book records with ISBNs. This script harvests
real, verified ISBNs that we know exist in their database.

Strategy:
- Query OpenLibrary's Search API by subject, author, publisher
- Extract ISBNs from search results
- Much higher success rate than random ISBN generation

API Documentation: https://openlibrary.org/dev/docs/api/search
Rate Limit: Be respectful, ~1 req/sec recommended
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List, Set

import requests


class OpenLibraryISBNHarvester:
    """
    Harvest ISBNs from OpenLibrary's free API.

    OpenLibrary has 20M+ books with ISBNs. We can search by:
    - Subject (fiction, science, history, etc.)
    - Publisher (Penguin, HarperCollins, etc.)
    - Author
    - Publication year
    """

    BASE_URL = "https://openlibrary.org/search.json"

    # High-volume subjects with many books
    SUBJECTS = [
        "fiction", "science_fiction", "fantasy", "mystery", "thriller",
        "romance", "history", "biography", "science", "philosophy",
        "psychology", "business", "self_help", "cooking", "art",
        "poetry", "drama", "humor", "travel", "religion",
        "children", "young_adult", "education", "technology", "medicine"
    ]

    # Major publishers
    PUBLISHERS = [
        "Penguin", "Random House", "HarperCollins", "Simon & Schuster",
        "Macmillan", "Hachette", "Scholastic", "Wiley", "McGraw-Hill",
        "Oxford University Press", "Cambridge University Press",
        "Vintage", "Knopf", "Doubleday", "Little Brown"
    ]

    def __init__(self, rate_limit: float = 1.0):
        """
        Initialize harvester.

        Args:
            rate_limit: Seconds between requests (default: 1.0)
        """
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ISBNLotOptimizer/1.0 (Educational metadata collection)'
        })
        self.harvested_isbns: Set[str] = set()

    def search_by_subject(self, subject: str, limit: int = 100) -> List[str]:
        """
        Search OpenLibrary by subject and extract ISBNs.

        Args:
            subject: Subject keyword
            limit: Maximum results (max 100 per page)

        Returns:
            List of ISBN-13s found
        """
        isbns = []

        try:
            params = {
                'subject': subject,
                'has_fulltext': 'false',  # Don't need full text
                'limit': min(limit, 100),
                'fields': 'isbn',  # Only get ISBNs to minimize data transfer
            }

            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Extract ISBNs from results
            for doc in data.get('docs', []):
                isbn_list = doc.get('isbn', [])
                for isbn in isbn_list:
                    # Clean and validate
                    isbn = isbn.replace('-', '').replace(' ', '')
                    if len(isbn) == 13 and isbn.startswith('978'):
                        isbns.append(isbn)
                        self.harvested_isbns.add(isbn)

            time.sleep(self.rate_limit)

        except Exception as e:
            print(f"Error searching subject '{subject}': {e}")

        return isbns

    def search_by_publisher(self, publisher: str, limit: int = 100) -> List[str]:
        """
        Search OpenLibrary by publisher and extract ISBNs.

        Args:
            publisher: Publisher name
            limit: Maximum results

        Returns:
            List of ISBN-13s found
        """
        isbns = []

        try:
            params = {
                'publisher': publisher,
                'limit': min(limit, 100),
                'fields': 'isbn',
            }

            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Extract ISBNs
            for doc in data.get('docs', []):
                isbn_list = doc.get('isbn', [])
                for isbn in isbn_list:
                    isbn = isbn.replace('-', '').replace(' ', '')
                    if len(isbn) == 13 and isbn.startswith('978'):
                        isbns.append(isbn)
                        self.harvested_isbns.add(isbn)

            time.sleep(self.rate_limit)

        except Exception as e:
            print(f"Error searching publisher '{publisher}': {e}")

        return isbns

    def harvest_by_subjects(self, per_subject: int = 100) -> List[str]:
        """
        Harvest ISBNs across all subjects.

        Args:
            per_subject: ISBNs to harvest per subject

        Returns:
            List of all harvested ISBNs
        """
        print("Harvesting ISBNs from OpenLibrary by subject...")
        print(f"Subjects: {len(self.SUBJECTS)}")
        print(f"Target per subject: {per_subject}")
        print()

        for i, subject in enumerate(self.SUBJECTS, 1):
            print(f"[{i}/{len(self.SUBJECTS)}] Searching subject: {subject}")

            isbns = self.search_by_subject(subject, limit=per_subject)
            print(f"  Found {len(isbns)} ISBNs")

            # Progress update every 5 subjects
            if i % 5 == 0:
                print(f"\nProgress: {len(self.harvested_isbns):,} unique ISBNs so far\n")

        return sorted(list(self.harvested_isbns))

    def harvest_by_publishers(self, per_publisher: int = 100) -> List[str]:
        """
        Harvest ISBNs across all publishers.

        Args:
            per_publisher: ISBNs to harvest per publisher

        Returns:
            List of all harvested ISBNs
        """
        print("Harvesting ISBNs from OpenLibrary by publisher...")
        print(f"Publishers: {len(self.PUBLISHERS)}")
        print(f"Target per publisher: {per_publisher}")
        print()

        for i, publisher in enumerate(self.PUBLISHERS, 1):
            print(f"[{i}/{len(self.PUBLISHERS)}] Searching publisher: {publisher}")

            isbns = self.search_by_publisher(publisher, limit=per_publisher)
            print(f"  Found {len(isbns)} ISBNs")

        return sorted(list(self.harvested_isbns))

    def harvest_mixed(self, target_count: int = 10000) -> List[str]:
        """
        Harvest ISBNs using mixed strategy (subjects + publishers).

        Args:
            target_count: Target number of unique ISBNs

        Returns:
            List of harvested ISBNs
        """
        print("=" * 70)
        print("OPENLIBRARY ISBN HARVESTING")
        print("=" * 70)
        print(f"Target: {target_count:,} unique ISBNs")
        print(f"Strategy: Mixed (subjects + publishers)")
        print()

        # Start with subjects (more diverse)
        per_subject = max(50, target_count // len(self.SUBJECTS))
        self.harvest_by_subjects(per_subject=per_subject)

        print()
        print(f"After subjects: {len(self.harvested_isbns):,} unique ISBNs")

        # If we need more, add publishers
        if len(self.harvested_isbns) < target_count:
            remaining = target_count - len(self.harvested_isbns)
            per_publisher = max(50, remaining // len(self.PUBLISHERS))

            print()
            self.harvest_by_publishers(per_publisher=per_publisher)

        print()
        print("=" * 70)
        print("HARVESTING COMPLETE")
        print("=" * 70)
        print(f"Total unique ISBNs: {len(self.harvested_isbns):,}")
        print(f"Success: These are all REAL books from OpenLibrary!")
        print()

        return sorted(list(self.harvested_isbns))

    def save_to_file(self, isbns: List[str], output_file: Path):
        """Save harvested ISBNs to file."""
        with open(output_file, 'w') as f:
            for isbn in isbns:
                f.write(f"{isbn}\n")

        print(f"✓ Saved {len(isbns):,} ISBNs to {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Harvest real ISBNs from OpenLibrary.org'
    )
    parser.add_argument('--count', type=int, default=10000,
                       help='Target number of ISBNs (default: 10000)')
    parser.add_argument('--output', type=Path, default=Path('/tmp/openlibrary_isbns.txt'),
                       help='Output file path')
    parser.add_argument('--rate-limit', type=float, default=1.0,
                       help='Seconds between API requests (default: 1.0)')
    parser.add_argument('--batch-size', type=int,
                       help='Split into batches of this size')

    args = parser.parse_args()

    # Harvest ISBNs
    harvester = OpenLibraryISBNHarvester(rate_limit=args.rate_limit)
    isbns = harvester.harvest_mixed(target_count=args.count)

    # Save results
    if args.batch_size and args.batch_size < len(isbns):
        # Create multiple batch files
        num_batches = (len(isbns) + args.batch_size - 1) // args.batch_size

        print()
        print(f"Creating {num_batches} batch files...")

        for i in range(num_batches):
            start_idx = i * args.batch_size
            end_idx = min((i + 1) * args.batch_size, len(isbns))
            batch = isbns[start_idx:end_idx]

            batch_file = args.output.parent / f"{args.output.stem}_batch{i+1}.txt"
            harvester.save_to_file(batch, batch_file)
    else:
        harvester.save_to_file(isbns, args.output)

    print()
    print("Ready for metadata collection with REAL ISBNs!")
    print("Expected success rate: 80-95% (vs 42.5% with generated ISBNs)")


if __name__ == '__main__':
    main()
