"""
Bulk AbeBooks data collection script using Decodo Core plan.

Collects pricing and market depth data from AbeBooks for multiple ISBNs.
Stores results in catalog database for ML training and price prediction.

Usage:
    # Collect for 50 books (test)
    python3 scripts/collect_abebooks_bulk.py --limit 50

    # Collect for all books in catalog
    python3 scripts/collect_abebooks_bulk.py --all

    # Collect for specific ISBNs from file
    python3 scripts/collect_abebooks_bulk.py --isbn-file isbns.txt

    # Resume from previous run (skip already collected)
    python3 scripts/collect_abebooks_bulk.py --limit 100 --resume
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

from shared.abebooks_scraper import fetch_abebooks_data
from shared.decodo import DecodoClient


def load_isbns_from_catalog(limit: int = None) -> List[str]:
    """
    Load ISBNs from catalog database.

    Args:
        limit: Maximum number of ISBNs to return

    Returns:
        List of ISBN-13 strings
    """
    import sqlite3

    # Try different database locations
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
                break
            except Exception:
                continue

    if not conn:
        print("❌ Error: Could not find catalog database")
        return []

    try:
        cursor = conn.cursor()

        # Try to find ISBN column in available tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        isbns = []

        # Try common table names
        for table in ['books', 'books_extended', 'catalog', 'training_samples']:
            if table in tables:
                try:
                    query = f"SELECT DISTINCT isbn_13 FROM {table} WHERE isbn_13 IS NOT NULL"
                    if limit:
                        query += f" LIMIT {limit}"
                    cursor.execute(query)
                    isbns = [row[0] for row in cursor.fetchall()]
                    if isbns:
                        print(f"✓ Loaded {len(isbns)} ISBNs from table: {table}")
                        break
                except Exception:
                    continue

        return isbns

    finally:
        conn.close()


def load_isbns_from_file(file_path: Path) -> List[str]:
    """
    Load ISBNs from a text file (one per line).

    Args:
        file_path: Path to ISBN file

    Returns:
        List of ISBNs
    """
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return []

    isbns = []
    with open(file_path) as f:
        for line in f:
            isbn = line.strip().replace("-", "")
            if isbn and isbn.isdigit() and len(isbn) in (10, 13):
                isbns.append(isbn)

    print(f"✓ Loaded {len(isbns)} ISBNs from file: {file_path.name}")
    return isbns


def save_results(results: Dict[str, Dict[str, Any]], output_file: Path):
    """
    Save collection results to JSON file.

    Args:
        results: Dict mapping ISBN -> abebooks data
        output_file: Path to output JSON file
    """
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"✓ Results saved to: {output_file}")


def load_existing_results(output_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load existing results from JSON file (for resume).

    Args:
        output_file: Path to output JSON file

    Returns:
        Dict mapping ISBN -> abebooks data
    """
    if not output_file.exists():
        return {}

    try:
        with open(output_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load existing results: {e}")
        return {}


def collect_abebooks_bulk(
    isbns: List[str],
    resume: bool = False,
    output_file: Path = None,
    batch_save_interval: int = 50
):
    """
    Collect AbeBooks data for multiple ISBNs.

    Args:
        isbns: List of ISBNs to collect
        resume: Skip ISBNs that already have results
        output_file: Path to save results (default: abebooks_results_TIMESTAMP.json)
        batch_save_interval: Save results every N ISBNs
    """
    # Setup output file
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(__file__).parent.parent / f"abebooks_results_{timestamp}.json"

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

    print(f"📚 Collecting AbeBooks data for {len(isbns_to_collect)} ISBNs")
    print(f"   Output: {output_file}")
    print("-" * 80)

    # Check credentials
    username = os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_PASSWORD")

    if not username or not password:
        print("❌ Error: DECODO_AUTHENTICATION and DECODO_PASSWORD environment variables required")
        print("Set them in your .env file")
        return results

    # Create Decodo client
    client = DecodoClient(username=username, password=password)

    # Collection stats
    stats = {
        "total": len(isbns_to_collect),
        "success": 0,
        "errors": 0,
        "no_results": 0,
        "start_time": time.time()
    }

    try:
        for i, isbn in enumerate(isbns_to_collect, 1):
            print(f"[{i}/{len(isbns_to_collect)}] {isbn}...", end=" ", flush=True)

            try:
                data = fetch_abebooks_data(isbn, client)

                if data.get("error") and data["stats"]["count"] == 0:
                    print(f"❌ {data['error']}")
                    stats["errors"] += 1
                elif data["stats"]["count"] == 0:
                    print("⚠️  No results")
                    stats["no_results"] += 1
                else:
                    count = data["stats"]["count"]
                    min_price = data["stats"]["min_price"]
                    avg_price = data["stats"]["avg_price"]
                    print(f"✓ {count} offers, ${min_price:.2f}-${avg_price:.2f} avg")
                    stats["success"] += 1

                results[isbn] = data

                # Save periodically
                if i % batch_save_interval == 0:
                    save_results(results, output_file)
                    print(f"   💾 Checkpoint saved ({i}/{len(isbns_to_collect)})")

                # Rate limiting (be gentle)
                time.sleep(0.5)  # 2 requests per second max

            except KeyboardInterrupt:
                print("\n⚠️  Interrupted by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                stats["errors"] += 1
                results[isbn] = {
                    "error": str(e),
                    "stats": {"count": 0},
                    "fetched_at": datetime.now().isoformat()
                }

    finally:
        client.close()

        # Final save
        save_results(results, output_file)

        # Print summary
        elapsed = time.time() - stats["start_time"]
        print()
        print("=" * 80)
        print("COLLECTION SUMMARY")
        print("=" * 80)
        print(f"Total ISBNs processed: {stats['success'] + stats['errors'] + stats['no_results']}")
        print(f"  ✓ Success: {stats['success']}")
        print(f"  ⚠️  No results: {stats['no_results']}")
        print(f"  ❌ Errors: {stats['errors']}")
        print(f"Time elapsed: {elapsed/60:.1f} minutes")
        print(f"Avg time per ISBN: {elapsed/(stats['success'] + stats['errors'] + stats['no_results']):.1f}s")
        print()
        print(f"Results saved to: {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Bulk AbeBooks data collection using Decodo Core plan"
    )

    # ISBN source options
    isbn_group = parser.add_mutually_exclusive_group(required=True)
    isbn_group.add_argument(
        "--limit",
        type=int,
        help="Collect for N books from catalog database"
    )
    isbn_group.add_argument(
        "--all",
        action="store_true",
        help="Collect for all books in catalog database"
    )
    isbn_group.add_argument(
        "--isbn-file",
        type=Path,
        help="Load ISBNs from text file (one per line)"
    )

    # Collection options
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run (skip already collected ISBNs)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file path (default: abebooks_results_TIMESTAMP.json)"
    )
    parser.add_argument(
        "--batch-save",
        type=int,
        default=50,
        help="Save results every N ISBNs (default: 50)"
    )

    args = parser.parse_args()

    # Load ISBNs
    if args.isbn_file:
        isbns = load_isbns_from_file(args.isbn_file)
    elif args.all:
        isbns = load_isbns_from_catalog(limit=None)
    else:
        isbns = load_isbns_from_catalog(limit=args.limit)

    if not isbns:
        print("❌ Error: No ISBNs to collect")
        return 1

    # Run collection
    collect_abebooks_bulk(
        isbns=isbns,
        resume=args.resume,
        output_file=args.output,
        batch_save_interval=args.batch_save
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
