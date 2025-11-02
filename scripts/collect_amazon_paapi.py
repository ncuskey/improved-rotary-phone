"""
Bulk Amazon data collection using FREE Amazon PA-API.

Replaces expensive Decodo scraping with free official API.

Usage:
    # Single ISBN test
    python3 scripts/collect_amazon_paapi.py --isbn 9780553381702

    # Collect for 100 books from database
    python3 scripts/collect_amazon_paapi.py --limit 100

    # From ISBN file
    python3 scripts/collect_amazon_paapi.py --isbn-file isbns.txt

    # Resume from previous run
    python3 scripts/collect_amazon_paapi.py --limit 1000 --resume
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

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

from shared.amazon_paapi import fetch_amazon_data, AmazonPAAPIClient


def load_isbns_from_database(limit: int = None) -> List[str]:
    """Load ISBNs from available databases."""
    import sqlite3

    db_paths = [
        Path(__file__).parent.parent / 'isbn_lot_optimizer' / 'catalog.db',
        Path(__file__).parent.parent / 'training_data.db',
        Path.home() / '.isbn_lot_optimizer' / 'training_data.db',
    ]

    for db_path in db_paths:
        if not db_path.exists():
            continue

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Find tables with ISBNs
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            for table in ['books', 'training_books', 'catalog']:
                if table not in tables:
                    continue

                try:
                    # Find ISBN column
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [row[1] for row in cursor.fetchall()]

                    isbn_col = 'isbn_13' if 'isbn_13' in columns else ('isbn' if 'isbn' in columns else None)

                    if not isbn_col:
                        continue

                    query = f"SELECT DISTINCT {isbn_col} FROM {table} WHERE {isbn_col} IS NOT NULL"
                    if limit:
                        query += f" LIMIT {limit}"

                    cursor.execute(query)
                    isbns = [row[0] for row in cursor.fetchall()]

                    if isbns:
                        print(f"✓ Loaded {len(isbns)} ISBNs from {db_path.name}/{table}")
                        conn.close()
                        return isbns

                except Exception:
                    continue

            conn.close()

        except Exception:
            continue

    print("❌ No ISBNs found in databases")
    return []


def load_isbns_from_file(file_path: Path) -> List[str]:
    """Load ISBNs from text file."""
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return []

    isbns = []
    with open(file_path) as f:
        for line in f:
            isbn = line.strip().replace("-", "").split()[0]  # Take first part (ignore scores)
            if isbn and isbn.isdigit() and len(isbn) in (10, 13):
                isbns.append(isbn)

    print(f"✓ Loaded {len(isbns)} ISBNs from {file_path.name}")
    return isbns


def save_results(results: Dict[str, Dict[str, Any]], output_file: Path):
    """Save results to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✓ Results saved to: {output_file}")


def load_existing_results(output_file: Path) -> Dict[str, Dict[str, Any]]:
    """Load existing results for resume."""
    if not output_file.exists():
        return {}

    try:
        with open(output_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load existing results: {e}")
        return {}


def collect_single_isbn(isbn: str):
    """Collect and display data for a single ISBN."""
    print(f"Looking up ISBN: {isbn}")
    print("=" * 80)

    try:
        data = fetch_amazon_data(isbn)

        if "error" in data and not data.get("title"):
            print(f"❌ Error: {data['error']}")
            return 1

        print("✓ Success!")
        print()
        print("Book Information:")
        print(f"  Title: {data.get('title', 'N/A')}")
        print(f"  Authors: {data.get('authors', 'N/A')}")
        print(f"  ASIN: {data.get('asin', 'N/A')}")
        print(f"  ISBN-10: {data.get('isbn_10', 'N/A')}")
        print(f"  ISBN-13: {data.get('isbn_13', 'N/A')}")
        print(f"  Binding: {data.get('binding', 'N/A')}")
        print(f"  Publisher: {data.get('publisher', 'N/A')}")
        print(f"  Publication: {data.get('publication_date', 'N/A')}")
        print()
        print("Market Data:")
        print(f"  Sales Rank: {data.get('amazon_sales_rank', 'N/A')}")
        print(f"  Price: ${data.get('amazon_lowest_price', 0):.2f}")
        print(f"  Rating: {data.get('amazon_rating', 'N/A')}")
        print(f"  Reviews: {data.get('amazon_ratings_count', 'N/A')}")
        print(f"  Page Count: {data.get('page_count', 'N/A')}")
        print()
        print("ML Features:")
        for key, value in data.get('ml_features', {}).items():
            print(f"  {key}: {value}")
        print()

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def collect_bulk(
    isbns: List[str],
    resume: bool = False,
    output_file: Path = None,
    batch_save_interval: int = 50
):
    """Collect Amazon data for multiple ISBNs."""
    # Setup output file
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(__file__).parent.parent / f"amazon_paapi_results_{timestamp}.json"

    # Load existing results if resuming
    results = {}
    if resume:
        results = load_existing_results(output_file)
        print(f"✓ Resuming: {len(results)} ISBNs already collected")

    # Filter out already-collected ISBNs
    isbns_to_collect = [isbn for isbn in isbns if isbn not in results]

    if not isbns_to_collect:
        print("✓ All ISBNs already collected!")
        return results

    print(f"📚 Collecting Amazon data for {len(isbns_to_collect)} ISBNs")
    print(f"   Output: {output_file}")
    print(f"   Rate: 1 request per second (PA-API free tier)")
    print(f"   Estimated time: {len(isbns_to_collect)/60:.1f} minutes")
    print("-" * 80)

    # Check credentials
    if not all([
        os.getenv("AMAZON_ACCESS_KEY"),
        os.getenv("AMAZON_SECRET_KEY"),
        os.getenv("AMAZON_ASSOCIATE_TAG")
    ]):
        print("❌ Error: Amazon PA-API credentials not found")
        print("Set in .env: AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_ASSOCIATE_TAG")
        return results

    # Create client
    try:
        client = AmazonPAAPIClient()
    except Exception as e:
        print(f"❌ Error creating client: {e}")
        return results

    # Collection stats
    stats = {
        "total": len(isbns_to_collect),
        "success": 0,
        "errors": 0,
        "not_found": 0,
        "start_time": time.time()
    }

    try:
        for i, isbn in enumerate(isbns_to_collect, 1):
            print(f"[{i}/{len(isbns_to_collect)}] {isbn}...", end=" ", flush=True)

            try:
                data = client.lookup_isbn(isbn)

                if not data:
                    print("⚠️  Not found")
                    stats["not_found"] += 1
                    results[isbn] = {
                        "error": "Not found in Amazon catalog",
                        "fetched_at": datetime.now().isoformat()
                    }
                elif "error" in data and not data.get("title"):
                    print(f"❌ {data.get('error', 'Unknown error')}")
                    stats["errors"] += 1
                    results[isbn] = data
                else:
                    # Extract ML features
                    ml_features = {
                        "amazon_sales_rank": data.get("amazon_sales_rank"),
                        "amazon_lowest_price": data.get("amazon_lowest_price"),
                        "amazon_rating": data.get("amazon_rating"),
                        "amazon_ratings_count": data.get("amazon_ratings_count"),
                        "page_count": data.get("page_count"),
                        "published_year": None,
                    }

                    # Extract year
                    if data.get("publication_date"):
                        import re
                        year_match = re.search(r'\b(19|20)\d{2}\b', data["publication_date"])
                        if year_match:
                            ml_features["published_year"] = int(year_match.group(0))

                    data["ml_features"] = ml_features

                    rank = data.get("amazon_sales_rank", "N/A")
                    price = data.get("amazon_lowest_price", 0)
                    print(f"✓ Rank: {rank}, ${price:.2f}")
                    stats["success"] += 1
                    results[isbn] = data

                # Save periodically
                if i % batch_save_interval == 0:
                    save_results(results, output_file)
                    print(f"   💾 Checkpoint: {i}/{len(isbns_to_collect)}")

            except KeyboardInterrupt:
                print("\n⚠️  Interrupted by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                stats["errors"] += 1
                results[isbn] = {
                    "error": str(e),
                    "fetched_at": datetime.now().isoformat()
                }

    finally:
        # Final save
        save_results(results, output_file)

        # Print summary
        elapsed = time.time() - stats["start_time"]
        print()
        print("=" * 80)
        print("COLLECTION SUMMARY")
        print("=" * 80)
        processed = stats["success"] + stats["errors"] + stats["not_found"]
        print(f"Total ISBNs processed: {processed}")
        print(f"  ✓ Success: {stats['success']}")
        print(f"  ⚠️  Not found: {stats['not_found']}")
        print(f"  ❌ Errors: {stats['errors']}")
        print(f"Time elapsed: {elapsed/60:.1f} minutes")
        if processed > 0:
            print(f"Avg time per ISBN: {elapsed/processed:.1f}s")
        print()
        print(f"Results saved to: {output_file}")
        print()
        print("💰 Cost: $0 (FREE with PA-API!)")
        print(f"   Decodo equivalent: ~{processed} credits saved")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Amazon data collection using FREE PA-API"
    )

    # ISBN source
    isbn_group = parser.add_mutually_exclusive_group()
    isbn_group.add_argument(
        "--isbn",
        type=str,
        help="Single ISBN to lookup (for testing)"
    )
    isbn_group.add_argument(
        "--limit",
        type=int,
        help="Collect for N books from database"
    )
    isbn_group.add_argument(
        "--isbn-file",
        type=Path,
        help="Load ISBNs from text file"
    )

    # Options
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file"
    )
    parser.add_argument(
        "--batch-save",
        type=int,
        default=50,
        help="Save every N ISBNs (default: 50)"
    )

    args = parser.parse_args()

    # Single ISBN mode
    if args.isbn:
        return collect_single_isbn(args.isbn)

    # Bulk mode
    if args.isbn_file:
        isbns = load_isbns_from_file(args.isbn_file)
    elif args.limit:
        isbns = load_isbns_from_database(args.limit)
    else:
        parser.print_help()
        return 1

    if not isbns:
        return 1

    collect_bulk(
        isbns=isbns,
        resume=args.resume,
        output_file=args.output,
        batch_save_interval=args.batch_save
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
