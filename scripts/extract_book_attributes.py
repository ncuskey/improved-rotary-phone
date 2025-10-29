"""
Extract book attributes from metadata and update database.

Extracts:
- cover_type: Hardcover, Paperback, Mass Market, etc.
- signed: Detected from title/edition
- printing: 1st printing/edition detection
- edition: Normalized edition info
"""

import json
import re
import sqlite3
import sys
from pathlib import Path


def detect_cover_type(metadata: dict) -> str:
    """
    Detect cover type from metadata.

    Returns: "Hardcover", "Paperback", "Mass Market", or None
    """
    if not metadata:
        return None

    binding = metadata.get("raw", {}).get("Binding", "")
    if not binding:
        return None

    binding_lower = binding.lower()

    if "hardcover" in binding_lower or "hardback" in binding_lower:
        return "Hardcover"
    elif "mass market" in binding_lower:
        return "Mass Market"
    elif "paperback" in binding_lower or "softcover" in binding_lower:
        return "Paperback"
    elif "spiral" in binding_lower:
        return "Spiral"
    elif "board" in binding_lower:
        return "Board Book"

    return None


def detect_signed(title: str, edition: str) -> bool:
    """
    Detect if book is signed from title or edition.

    Returns: True if signed/autographed detected
    """
    if not title and not edition:
        return False

    text = f"{title or ''} {edition or ''}".lower()

    signed_keywords = [
        "signed",
        "autographed",
        "inscribed",
        "signature",
    ]

    return any(keyword in text for keyword in signed_keywords)


def detect_first_edition(edition: str) -> bool:
    """
    Detect if book is first edition/printing.

    Returns: True if 1st edition/printing detected
    """
    if not edition:
        return False

    edition_lower = edition.lower()

    first_edition_patterns = [
        r"\b1st\s+(edition|printing|ed\.?)\b",
        r"\bfirst\s+(edition|printing|ed\.?)\b",
        r"\b1/1\b",  # First edition, first printing
    ]

    return any(re.search(pattern, edition_lower) for pattern in first_edition_patterns)


def normalize_edition(edition: str) -> str:
    """
    Normalize edition string.

    Returns: Cleaned edition string or None
    """
    if not edition:
        return None

    edition = edition.strip()

    # Remove common noise
    edition = re.sub(r"\s+", " ", edition)

    return edition if edition else None


def extract_attributes(db_path: Path) -> tuple[int, int]:
    """
    Extract book attributes from metadata and update database.

    Returns: (updated_count, skipped_count)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all books with metadata
    cursor.execute("""
        SELECT isbn, title, metadata_json, edition
        FROM books
        WHERE metadata_json IS NOT NULL
    """)

    updated = 0
    skipped = 0

    stats = {
        "hardcover": 0,
        "paperback": 0,
        "mass_market": 0,
        "signed": 0,
        "first_edition": 0,
    }

    for row in cursor.fetchall():
        isbn, title, metadata_json, existing_edition = row

        try:
            metadata = json.loads(metadata_json)

            # Extract attributes
            cover_type = detect_cover_type(metadata)
            edition_from_meta = metadata.get("raw", {}).get("Edition")
            edition = normalize_edition(edition_from_meta or existing_edition)
            signed = detect_signed(title, edition_from_meta or "")
            printing = "1st" if detect_first_edition(edition_from_meta or "") else None

            # Update database
            cursor.execute("""
                UPDATE books
                SET cover_type = ?,
                    signed = ?,
                    printing = ?,
                    edition = ?
                WHERE isbn = ?
            """, (cover_type, 1 if signed else 0, printing, edition, isbn))

            updated += 1

            # Stats
            if cover_type == "Hardcover":
                stats["hardcover"] += 1
            elif cover_type == "Paperback":
                stats["paperback"] += 1
            elif cover_type == "Mass Market":
                stats["mass_market"] += 1

            if signed:
                stats["signed"] += 1
            if printing == "1st":
                stats["first_edition"] += 1

        except Exception as e:
            print(f"  Error processing {isbn}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    return updated, skipped, stats


def main():
    """Main entry point."""
    db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print("=" * 70)
    print("Extract Book Attributes")
    print("=" * 70)

    print("\nExtracting book attributes from metadata...")
    updated, skipped, stats = extract_attributes(db_path)

    print(f"\n✓ Updated {updated} books")
    print(f"  Skipped {skipped} books (errors)")

    print(f"\nAttribute Distribution:")
    print(f"  Hardcover:      {stats['hardcover']:4d} ({stats['hardcover']/updated*100:5.1f}%)")
    print(f"  Paperback:      {stats['paperback']:4d} ({stats['paperback']/updated*100:5.1f}%)")
    print(f"  Mass Market:    {stats['mass_market']:4d} ({stats['mass_market']/updated*100:5.1f}%)")
    print(f"  Signed:         {stats['signed']:4d} ({stats['signed']/updated*100:5.1f}%)")
    print(f"  1st Edition:    {stats['first_edition']:4d} ({stats['first_edition']/updated*100:5.1f}%)")

    print(f"\n✓ Ready to add features to ML model")

    return 0


if __name__ == "__main__":
    sys.exit(main())
