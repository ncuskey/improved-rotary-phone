"""
Enrich book categories using Google Books API.

Fills missing category information (fiction vs non-fiction, textbooks).
Zero cost - uses free Google Books API.
"""

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Set
import urllib.request
import urllib.parse


class CategoryEnricher:
    """Enrich book categories via Google Books API."""

    def __init__(self, db_path: Path):
        """
        Initialize category enricher.

        Args:
            db_path: Path to catalog.db
        """
        self.db_path = db_path
        self.stats = {
            'total': 0,
            'enriched': 0,
            'failed': 0,
        }

    def _query_google_books(self, isbn: str) -> Optional[Dict]:
        """
        Query Google Books API for book metadata.

        Args:
            isbn: ISBN-13 string

        Returns:
            Dict with volume info or None
        """
        try:
            # Query by ISBN
            url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"

            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())

                if data.get('totalItems', 0) > 0:
                    items = data.get('items', [])
                    if items:
                        return items[0].get('volumeInfo', {})

            return None

        except Exception as e:
            print(f"  Error querying Google Books: {e}")
            return None

    def _extract_categories(self, volume_info: Dict) -> Set[str]:
        """
        Extract normalized categories from volume info.

        Args:
            volume_info: Google Books volumeInfo dict

        Returns:
            Set of normalized category strings
        """
        categories = set()

        # Get categories from Google Books
        raw_categories = volume_info.get('categories', [])

        for cat in raw_categories:
            # Normalize: lowercase and split on "/"
            parts = cat.lower().split('/')
            for part in parts:
                part = part.strip()
                if part:
                    categories.add(part)

        return categories

    def _is_fiction(self, categories: Set[str]) -> bool:
        """
        Determine if book is fiction based on categories.

        Args:
            categories: Set of normalized category strings

        Returns:
            True if fiction, False otherwise
        """
        fiction_keywords = {
            'fiction', 'novel', 'novels', 'mystery', 'thriller',
            'romance', 'fantasy', 'science fiction', 'horror',
            'literary fiction', 'historical fiction', 'crime'
        }

        nonfiction_keywords = {
            'non-fiction', 'nonfiction', 'biography', 'history',
            'science', 'business', 'self-help', 'reference',
            'textbook', 'education', 'medical', 'technology',
            'philosophy', 'psychology', 'religion'
        }

        # Check for explicit fiction markers
        for cat in categories:
            if any(keyword in cat for keyword in fiction_keywords):
                return True
            # Check for explicit non-fiction markers
            if any(keyword in cat for keyword in nonfiction_keywords):
                return False

        return False  # Default to non-fiction if ambiguous

    def _is_textbook(self, categories: Set[str], volume_info: Dict) -> bool:
        """
        Determine if book is a textbook.

        Args:
            categories: Set of normalized category strings
            volume_info: Full volume info dict

        Returns:
            True if textbook, False otherwise
        """
        textbook_keywords = {
            'textbook', 'textbooks', 'education', 'study guide',
            'course', 'classroom', 'academic'
        }

        # Check categories
        for cat in categories:
            if any(keyword in cat for keyword in textbook_keywords):
                return True

        # Check title for textbook indicators
        title = volume_info.get('title', '').lower()
        if any(keyword in title for keyword in textbook_keywords):
            return True

        # Check subtitle
        subtitle = volume_info.get('subtitle', '').lower()
        if subtitle and any(keyword in subtitle for keyword in textbook_keywords):
            return True

        return False

    def enrich_book(self, isbn: str, title: str) -> Optional[Dict]:
        """
        Enrich a single book with categories.

        Args:
            isbn: ISBN-13 string
            title: Book title for display

        Returns:
            Dict with enrichment data or None
        """
        self.stats['total'] += 1

        print(f"[{self.stats['total']}] {isbn}: {title[:50]}...")

        # Query Google Books
        volume_info = self._query_google_books(isbn)

        if not volume_info:
            print(f"  ✗ No data from Google Books")
            self.stats['failed'] += 1
            return None

        # Extract categories
        categories = self._extract_categories(volume_info)

        if not categories:
            print(f"  ✗ No categories found")
            self.stats['failed'] += 1
            return None

        # Determine fiction/textbook status
        is_fiction = self._is_fiction(categories)
        is_textbook = self._is_textbook(categories, volume_info)

        print(f"  ✓ Categories: {', '.join(sorted(categories)[:5])}")
        print(f"    Fiction: {is_fiction}, Textbook: {is_textbook}")

        self.stats['enriched'] += 1

        return {
            'categories': list(categories),
            'is_fiction': is_fiction,
            'is_textbook': is_textbook,
        }

    def enrich_catalog(self, dry_run: bool = False):
        """
        Enrich all books in catalog missing categories.

        Args:
            dry_run: If True, don't write changes
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        print("=" * 70)
        print("CATEGORY ENRICHMENT")
        print("=" * 70)
        print()

        # Get books with missing categories
        query = """
            SELECT isbn, title, metadata_json
            FROM books
            WHERE metadata_json IS NULL
               OR json_extract(metadata_json, '$.categories') IS NULL
               OR json_extract(metadata_json, '$.categories') = '[]'
            ORDER BY updated_at DESC
        """

        cursor.execute(query)
        books = cursor.fetchall()

        print(f"Found {len(books)} books needing category enrichment")
        print()

        if not books:
            print("No books need enrichment!")
            conn.close()
            return

        updates = []

        for isbn, title, metadata_json in books:
            # Enrich from Google Books
            enrichment = self.enrich_book(isbn, title)

            if enrichment:
                # Parse existing metadata
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except json.JSONDecodeError:
                        metadata = {}
                else:
                    metadata = {}

                # Update with enrichment
                metadata['categories'] = enrichment['categories']

                updates.append((json.dumps(metadata), isbn))

            # Rate limit (be nice to Google Books API)
            time.sleep(0.1)

        print()
        print("=" * 70)
        print("ENRICHMENT RESULTS")
        print("=" * 70)
        print(f"Total books processed: {self.stats['total']}")
        print(f"Successfully enriched: {self.stats['enriched']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Success rate: {(self.stats['enriched']/self.stats['total']*100):.1f}%")
        print()

        if dry_run:
            print("DRY RUN - No changes made")
        else:
            # Apply updates
            print(f"Applying {len(updates)} updates...")

            cursor.executemany("""
                UPDATE books
                SET metadata_json = ?
                WHERE isbn = ?
            """, updates)

            conn.commit()
            print(f"✓ Updated {len(updates)} books")

        # Show updated stats
        print()
        print("Database Stats:")
        print("-" * 70)

        cursor.execute("""
            SELECT COUNT(*) FROM books
            WHERE metadata_json IS NOT NULL
              AND json_extract(metadata_json, '$.categories') IS NOT NULL
              AND json_extract(metadata_json, '$.categories') != '[]'
        """)
        with_categories = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM books")
        total = cursor.fetchone()[0]

        print(f"  Books with categories: {with_categories}/{total} ({with_categories/total*100:.1f}%)")

        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Enrich book categories from Google Books")
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write changes, just show what would be done"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    enricher = CategoryEnricher(db_path)
    enricher.enrich_catalog(dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
