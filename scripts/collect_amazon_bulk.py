"""
Bulk Amazon data collection using Decodo async batch API.

Collects Amazon product data (sales rank, pricing, ratings) for all books
in the catalog using Decodo's amazon_product target.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient
from shared.amazon_decodo_parser import parse_decodo_batch_results


def isbn13_to_isbn10(isbn13: str) -> str:
    """
    Convert ISBN-13 to ISBN-10.

    Amazon uses ISBN-10 as ASINs for books.
    ISBN-13 format: 978-XXXXXXXXX-C
    ISBN-10 format: XXXXXXXXX-C (with recalculated check digit)
    """
    if not isbn13 or len(isbn13) != 13:
        return isbn13

    if not isbn13.startswith("978"):
        # Can't convert non-978 prefix ISBNs
        return isbn13

    # Extract the middle 9 digits
    base = isbn13[3:12]

    # Calculate ISBN-10 check digit
    check_sum = sum((10 - i) * int(digit) for i, digit in enumerate(base))
    check_digit = (11 - (check_sum % 11)) % 11

    if check_digit == 10:
        check_digit = 'X'
    else:
        check_digit = str(check_digit)

    return base + check_digit


def load_isbns_from_database(db_path: Path, limit: int = None) -> List[Tuple[str, str]]:
    """
    Load ISBNs from database.

    Args:
        db_path: Path to catalog.db
        limit: Maximum number of ISBNs to load

    Returns:
        List of (isbn_10, isbn_13) tuples
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT DISTINCT isbn FROM books ORDER BY updated_at DESC"

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    isbn13_list = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Convert to ISBN-10 for Amazon lookups
    isbn_pairs = []
    for isbn13 in isbn13_list:
        isbn10 = isbn13_to_isbn10(isbn13)
        isbn_pairs.append((isbn10, isbn13))

    return isbn_pairs


def update_database_with_amazon_data(
    db_path: Path,
    parsed_results: Dict[str, Dict]
) -> Tuple[int, int]:
    """
    Update database with Amazon data from Decodo.

    Args:
        db_path: Path to catalog.db
        parsed_results: Dict mapping ISBN-13 to parsed data

    Returns:
        Tuple of (success_count, failed_count)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    success_count = 0
    failed_count = 0

    for isbn13, data in parsed_results.items():
        try:
            # Update bookscouter_json with Amazon data
            bookscouter_json = json.dumps(data)

            cursor.execute(
                """
                UPDATE books
                SET bookscouter_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE isbn = ?
                """,
                (bookscouter_json, isbn13)
            )

            if cursor.rowcount > 0:
                success_count += 1
            else:
                failed_count += 1
                print(f"  Warning: No book found for ISBN {isbn13}")

        except Exception as e:
            failed_count += 1
            print(f"  Error updating {isbn13}: {e}")

    conn.commit()
    conn.close()

    return success_count, failed_count


def main():
    """Main entry point for bulk Amazon data collection."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Bulk collect Amazon data via Decodo API"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of books to collect (default: all)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=60,
        help="Maximum number of poll attempts (default: 60 = 30 min)"
    )
    parser.add_argument(
        "--save-failures",
        type=str,
        default="amazon_failures.txt",
        help="File to save failed ISBNs (default: amazon_failures.txt)"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    # Get Decodo credentials from environment
    username = os.environ.get("DECODO_AUTHENTICATION")
    password = os.environ.get("DECODO_PASSWORD")

    if not username or not password:
        print("Error: Missing Decodo credentials in environment")
        print("Set DECODO_AUTHENTICATION and DECODO_PASSWORD")
        return 1

    print("=" * 70)
    print("Decodo Bulk Amazon Data Collection")
    print("=" * 70)

    # Load ISBNs
    print(f"\n1. Loading ISBNs from database...")
    isbn_pairs = load_isbns_from_database(db_path, limit=args.limit)
    print(f"   Found {len(isbn_pairs)} books to process")

    if not isbn_pairs:
        print("No books found in database")
        return 0

    # Extract ISBN-10s for API query
    isbn10_list = [pair[0] for pair in isbn_pairs]

    # Initialize Decodo client
    print(f"\n2. Initializing Decodo client...")
    client = DecodoClient(username, password, rate_limit=20)  # 20 req/s (Pro plan allows 200)
    print(f"   Using credentials: {username[:10]}...")

    # Collect via real-time API (batch API not working with amazon_product)
    print(f"\n3. Collecting {len(isbn10_list)} ISBNs via real-time API...")
    print(f"   Rate: 20 requests/second (ETA: {len(isbn10_list)/20/60:.1f} minutes)")

    import json as json_module

    all_results = {}
    failed_count = 0

    for idx, (isbn10, isbn13) in enumerate(isbn_pairs, 1):
        try:
            # Progress update every 50 books
            if idx % 50 == 0 or idx == len(isbn_pairs):
                percent = (idx / len(isbn_pairs)) * 100
                print(f"   [{idx}/{len(isbn_pairs)}] {percent:.1f}% complete...")

            # Scrape this ISBN
            response = client.scrape_realtime(
                query=isbn10,
                target="amazon_product",
                domain="com",
                parse=True
            )

            if response.status_code == 200 and response.body:
                # Store raw response for parsing later
                all_results[isbn13] = json_module.loads(response.body)
            else:
                failed_count += 1
                all_results[isbn13] = None

        except Exception as e:
            print(f"   Error collecting {isbn13}: {e}")
            failed_count += 1
            all_results[isbn13] = None

    print(f"\n   ✓ Collected {len(all_results) - failed_count}/{len(isbn_pairs)} successfully")
    print(f"   ✗ Failed: {failed_count}")

    # Parse results
    print(f"\n4. Parsing Decodo responses...")
    isbn_mapping = {isbn13: (isbn10, isbn13) for isbn10, isbn13 in isbn_pairs}
    parsed_results = parse_decodo_batch_results(all_results, isbn_mapping)
    print(f"   ✓ Parsed {len(parsed_results)} results")

    # Count successes/failures
    successful = sum(1 for r in parsed_results.values() if r.get("amazon_sales_rank"))
    failed = len(parsed_results) - successful

    print(f"\n   Success: {successful} books")
    print(f"   Failed:  {failed} books")

    # Update database
    print(f"\n5. Updating database...")
    db_success, db_failed = update_database_with_amazon_data(db_path, parsed_results)
    print(f"   ✓ Updated {db_success} books")
    if db_failed > 0:
        print(f"   ✗ Failed to update {db_failed} books")

    # Save failed ISBNs
    if failed > 0:
        failed_isbns = [
            isbn13 for isbn13, result in parsed_results.items()
            if not result.get("amazon_sales_rank")
        ]

        failures_file = Path(args.save_failures)
        with open(failures_file, "w") as f:
            for isbn in failed_isbns:
                f.write(f"{isbn}\n")

        print(f"\n   Failed ISBNs saved to: {failures_file}")

    # Summary
    print("\n" + "=" * 70)
    print("Collection Complete!")
    print("=" * 70)
    print(f"Total Books: {len(isbn_pairs)}")
    print(f"Success:     {successful} ({successful/len(isbn_pairs)*100:.1f}%)")
    print(f"Failed:      {failed} ({failed/len(isbn_pairs)*100:.1f}%)")
    print(f"\nDatabase updated: {db_success} books")

    if successful > 50:
        print(f"\n✓ Ready to retrain ML model:")
        print(f"  python3 scripts/train_price_model.py")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
