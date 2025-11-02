"""
ISBN Prioritization for AbeBooks Collection

Creates a prioritized list of ISBNs to collect AbeBooks data for,
based on strategic value and likelihood of good training data.

Prioritization Criteria:
1. Books with existing Amazon data (for correlation analysis)
2. Books with high Amazon sales rank (popular = more market data)
3. Books with ratings/reviews (validated quality)
4. Books frequently encountered in lots (practical value)
5. Books in target categories (first editions, signed, etc.)

Usage:
    # Generate top 10K ISBNs from all sources
    python3 scripts/prioritize_isbns_for_collection.py --output top_10k.txt --limit 10000

    # From specific database
    python3 scripts/prioritize_isbns_for_collection.py --db training_data.db --limit 5000

    # From ISBN file (add priority scores)
    python3 scripts/prioritize_isbns_for_collection.py --input isbns.txt --output prioritized.txt
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class ISBNPrioritizer:
    """
    Prioritize ISBNs for AbeBooks data collection based on strategic value.
    """

    def __init__(self):
        self.isbn_scores = {}  # ISBN -> priority score

    def load_from_training_db(self, limit: Optional[int] = None) -> List[Tuple[str, float]]:
        """
        Load ISBNs from training_data.db with priority scoring.

        Args:
            limit: Maximum ISBNs to return

        Returns:
            List of (isbn, score) tuples, sorted by score descending
        """
        db_paths = [
            Path.home() / '.isbn_lot_optimizer' / 'training_data.db',
            Path(__file__).parent.parent / 'training_data.db',
            Path(__file__).parent.parent / 'isbn_lot_optimizer' / 'training.db',
        ]

        conn = None
        for db_path in db_paths:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path))
                    break
                except Exception:
                    continue

        if not conn:
            print("⚠️  Training database not found")
            return []

        try:
            cursor = conn.cursor()

            # Try to find ISBN and metadata in training_books table
            try:
                query = """
                    SELECT
                        isbn,
                        sold_count,
                        collection_priority,
                        comp_quality_score,
                        bookscouter_json
                    FROM training_books
                    WHERE isbn IS NOT NULL
                """
                cursor.execute(query)

                rows = cursor.fetchall()

                for row in rows:
                    isbn, sold_count, priority, quality, bookscouter_json = row

                    score = 0.0

                    # Factor 1: Sold count (indicates market activity)
                    if sold_count:
                        score += min(sold_count / 10.0, 50.0)  # Max 50 points

                    # Factor 2: Collection priority
                    if priority:
                        score += priority * 10.0

                    # Factor 3: Comp quality score
                    if quality:
                        score += quality * 20.0

                    # Factor 4: Has Amazon data
                    if bookscouter_json:
                        try:
                            data = json.loads(bookscouter_json)
                            if data.get('amazon_sales_rank'):
                                # Higher rank = more popular = higher score
                                rank = data['amazon_sales_rank']
                                if rank < 1000:
                                    score += 100.0
                                elif rank < 10000:
                                    score += 75.0
                                elif rank < 100000:
                                    score += 50.0
                                else:
                                    score += 25.0

                            if data.get('amazon_ratings_count'):
                                # More ratings = validated quality
                                score += min(data['amazon_ratings_count'] / 100.0, 30.0)
                        except:
                            pass

                    self.isbn_scores[isbn] = score

                print(f"✓ Loaded {len(self.isbn_scores)} ISBNs from training database")

            except sqlite3.OperationalError:
                print("⚠️  Training database has different schema")

        finally:
            conn.close()

        # Sort by score and return top N
        sorted_isbns = sorted(self.isbn_scores.items(), key=lambda x: x[1], reverse=True)

        if limit:
            sorted_isbns = sorted_isbns[:limit]

        return sorted_isbns

    def load_from_catalog_db(self, limit: Optional[int] = None) -> List[Tuple[str, float]]:
        """
        Load ISBNs from catalog.db with priority scoring.

        Args:
            limit: Maximum ISBNs to return

        Returns:
            List of (isbn, score) tuples
        """
        db_paths = [
            Path(__file__).parent.parent / 'isbn_lot_optimizer' / 'catalog.db',
            Path(__file__).parent.parent / 'catalog.db',
            Path(__file__).parent.parent / 'isbn_optimizer.db',
        ]

        conn = None
        for db_path in db_paths:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path))
                    # Try to query it
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    if tables:
                        break
                except Exception:
                    if conn:
                        conn.close()
                    continue

        if not conn:
            print("⚠️  Catalog database not found or empty")
            return []

        try:
            cursor = conn.cursor()

            # Find table with ISBNs
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            for table in ['books', 'books_extended', 'catalog']:
                if table in tables:
                    try:
                        # Get column names
                        cursor.execute(f"PRAGMA table_info({table})")
                        columns = [row[1] for row in cursor.fetchall()]

                        isbn_col = None
                        data_col = None

                        if 'isbn_13' in columns:
                            isbn_col = 'isbn_13'
                        elif 'isbn' in columns:
                            isbn_col = 'isbn'

                        if 'bookscouter_data' in columns:
                            data_col = 'bookscouter_data'

                        if not isbn_col:
                            continue

                        # Query ISBNs
                        query = f"SELECT {isbn_col}"
                        if data_col:
                            query += f", {data_col}"
                        query += f" FROM {table} WHERE {isbn_col} IS NOT NULL"

                        cursor.execute(query)
                        rows = cursor.fetchall()

                        for row in rows:
                            isbn = row[0]
                            score = 50.0  # Base score

                            # If we have Amazon data, boost score
                            if len(row) > 1 and row[1]:
                                try:
                                    data = json.loads(row[1])

                                    # Amazon rank scoring
                                    if data.get('amazon_sales_rank'):
                                        rank = data['amazon_sales_rank']
                                        if rank < 1000:
                                            score += 100.0
                                        elif rank < 10000:
                                            score += 75.0
                                        elif rank < 100000:
                                            score += 50.0
                                        else:
                                            score += 25.0

                                    # Ratings scoring
                                    if data.get('amazon_ratings_count'):
                                        score += min(data['amazon_ratings_count'] / 100.0, 30.0)

                                    # Has reviews = validated
                                    if data.get('amazon_rating'):
                                        score += 20.0

                                except:
                                    pass

                            self.isbn_scores[isbn] = score

                        print(f"✓ Loaded {len(self.isbn_scores)} ISBNs from {table}")
                        break

                    except Exception as e:
                        print(f"⚠️  Could not query {table}: {e}")
                        continue

        finally:
            conn.close()

        # Sort by score
        sorted_isbns = sorted(self.isbn_scores.items(), key=lambda x: x[1], reverse=True)

        if limit:
            sorted_isbns = sorted_isbns[:limit]

        return sorted_isbns

    def load_from_file(self, file_path: Path) -> List[Tuple[str, float]]:
        """
        Load ISBNs from text file (one per line).
        Assign default score of 50.0 to each.

        Args:
            file_path: Path to ISBN file

        Returns:
            List of (isbn, score) tuples
        """
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            return []

        isbns = []
        with open(file_path) as f:
            for line in f:
                isbn = line.strip().replace("-", "")
                if isbn and isbn.isdigit() and len(isbn) in (10, 13):
                    isbns.append((isbn, 50.0))  # Default score

        print(f"✓ Loaded {len(isbns)} ISBNs from file")
        return isbns

    def generate_category_priorities(self) -> Dict[str, float]:
        """
        Generate priority scores for different book categories.

        Returns:
            Dict mapping category -> score multiplier
        """
        return {
            "signed_hardcover": 2.0,  # Highest value
            "first_edition_hardcover": 1.8,
            "collectible": 1.5,
            "academic_textbook": 1.3,
            "popular_fiction": 1.2,
            "reference": 1.0,
            "mass_market": 0.8,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Prioritize ISBNs for AbeBooks data collection"
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--db",
        type=Path,
        help="Load from specific database file"
    )
    input_group.add_argument(
        "--input",
        type=Path,
        help="Load from text file (one ISBN per line)"
    )
    input_group.add_argument(
        "--training",
        action="store_true",
        help="Load from training_data.db (default)"
    )
    input_group.add_argument(
        "--catalog",
        action="store_true",
        help="Load from catalog.db"
    )
    input_group.add_argument(
        "--all",
        action="store_true",
        help="Load from all available sources"
    )

    # Output options
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file path for prioritized ISBN list"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum number of ISBNs to output (default: 10000)"
    )
    parser.add_argument(
        "--with-scores",
        action="store_true",
        help="Include priority scores in output"
    )

    args = parser.parse_args()

    prioritizer = ISBNPrioritizer()

    print("=" * 80)
    print("ISBN PRIORITIZATION FOR ABEBOOKS COLLECTION")
    print("=" * 80)
    print()

    # Load ISBNs
    all_isbns = []

    if args.input:
        all_isbns = prioritizer.load_from_file(args.input)
    elif args.catalog:
        all_isbns = prioritizer.load_from_catalog_db(args.limit)
    elif args.training:
        all_isbns = prioritizer.load_from_training_db(args.limit)
    elif args.all:
        # Load from all sources and combine
        training = prioritizer.load_from_training_db()
        catalog = prioritizer.load_from_catalog_db()

        # Combine scores (take max if ISBN appears in both)
        combined = {}
        for isbn, score in training + catalog:
            combined[isbn] = max(combined.get(isbn, 0), score)

        all_isbns = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        print(f"✓ Combined {len(all_isbns)} unique ISBNs from all sources")
    else:
        # Default: try training first, then catalog
        all_isbns = prioritizer.load_from_training_db(args.limit)
        if not all_isbns:
            all_isbns = prioritizer.load_from_catalog_db(args.limit)

    if not all_isbns:
        print("❌ No ISBNs found from any source")
        print()
        print("Alternatives:")
        print("  1. Create a text file with ISBNs (one per line)")
        print("  2. Use --input flag to specify the file")
        print("  3. Ensure training_data.db or catalog.db exists and has data")
        return 1

    # Limit to requested count
    if len(all_isbns) > args.limit:
        all_isbns = all_isbns[:args.limit]

    # Write to output
    print()
    print(f"Writing {len(all_isbns)} prioritized ISBNs to: {args.output}")

    with open(args.output, 'w') as f:
        if args.with_scores:
            f.write("# ISBN | Priority Score\n")
            for isbn, score in all_isbns:
                f.write(f"{isbn}\t{score:.1f}\n")
        else:
            for isbn, score in all_isbns:
                f.write(f"{isbn}\n")

    print(f"✓ Prioritized ISBN list saved")
    print()

    # Print statistics
    scores = [score for isbn, score in all_isbns]
    print("Priority Score Distribution:")
    print(f"  Highest: {max(scores):.1f}")
    print(f"  Lowest: {min(scores):.1f}")
    print(f"  Average: {sum(scores)/len(scores):.1f}")
    print()

    # Print top 10
    print("Top 10 Priority ISBNs:")
    for i, (isbn, score) in enumerate(all_isbns[:10], 1):
        print(f"  {i}. {isbn} (score: {score:.1f})")
    print()

    print("Next steps:")
    print(f"  1. Review {args.output}")
    print("  2. Run: python3 scripts/collect_abebooks_bulk.py --isbn-file {args.output}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
