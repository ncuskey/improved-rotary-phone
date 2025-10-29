"""
Update metadata_json with Amazon data from bookscouter_json.

Merges Amazon data (rating, reviews, page count, publication year)
into the metadata_json field for ML feature extraction.
"""

import json
import sqlite3
import sys
from pathlib import Path

def update_metadata_from_amazon(db_path: Path) -> tuple[int, int]:
    """
    Update metadata_json with Amazon data from bookscouter_json.

    Args:
        db_path: Path to catalog.db

    Returns:
        Tuple of (updated_count, skipped_count)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all books with Amazon data
    cursor.execute("""
        SELECT isbn, metadata_json, bookscouter_json
        FROM books
        WHERE bookscouter_json IS NOT NULL
    """)

    updated = 0
    skipped = 0

    for row in cursor.fetchall():
        isbn, metadata_json, bookscouter_json = row

        try:
            # Parse existing metadata
            metadata = json.loads(metadata_json) if metadata_json else {}
            bookscouter = json.loads(bookscouter_json)

            # Extract Amazon data from raw.data
            amazon_data = bookscouter.get("raw", {}).get("data", {})

            if not amazon_data:
                skipped += 1
                continue

            # Update metadata with Amazon fields (only if not already present)
            if "page_count" in amazon_data and amazon_data["page_count"]:
                if not metadata.get("page_count"):
                    metadata["page_count"] = amazon_data["page_count"]

            if "rating" in amazon_data and amazon_data["rating"]:
                if not metadata.get("average_rating"):
                    metadata["average_rating"] = amazon_data["rating"]

            if "reviews_count" in amazon_data and amazon_data["reviews_count"]:
                if not metadata.get("ratings_count"):
                    metadata["ratings_count"] = amazon_data["reviews_count"]

            if "publication_year" in amazon_data and amazon_data["publication_year"]:
                if not metadata.get("published_year"):
                    metadata["published_year"] = amazon_data["publication_year"]

            # Update database
            cursor.execute(
                "UPDATE books SET metadata_json = ? WHERE isbn = ?",
                (json.dumps(metadata), isbn)
            )
            updated += 1

        except Exception as e:
            print(f"Error updating {isbn}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    return updated, skipped


def main():
    """Main entry point."""
    db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print("=" * 70)
    print("Update Metadata with Amazon Data")
    print("=" * 70)

    print(f"\nUpdating metadata from Amazon data...")
    updated, skipped = update_metadata_from_amazon(db_path)

    print(f"\n✓ Updated {updated} books")
    print(f"  Skipped {skipped} books (no Amazon data or errors)")

    print(f"\n✓ Ready to retrain ML model:")
    print(f"  python3 scripts/train_price_model.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
