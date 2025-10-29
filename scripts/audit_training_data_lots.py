"""
Audit training data for lot listing contamination.

Scans book titles in training databases to identify potential lot listings
that could contaminate ML model training.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.lot_detector import is_lot, get_lot_detection_reason, get_lot_stats


def audit_catalog_db(db_path: Path) -> Dict:
    """
    Audit catalog.db for lot contamination.

    Args:
        db_path: Path to catalog.db

    Returns:
        Dict with audit results
    """
    if not db_path.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if books table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
    if not cursor.fetchone():
        conn.close()
        return {"error": "No 'books' table found in database"}

    # Query all books with metadata
    query = """
        SELECT isbn, metadata_json, market_json
        FROM books
        WHERE metadata_json IS NOT NULL
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"total_books": 0, "lot_contamination": []}

    # Scan for lots
    lot_books = []
    all_titles = []

    for isbn, metadata_json, market_json in rows:
        metadata = json.loads(metadata_json) if metadata_json else {}
        title = metadata.get('title', '')

        if title:
            all_titles.append(title)

            if is_lot(title):
                reason = get_lot_detection_reason(title)
                lot_books.append({
                    "isbn": isbn,
                    "title": title,
                    "reason": reason
                })

    stats = get_lot_stats(all_titles)

    return {
        "database": str(db_path),
        "total_books": len(rows),
        "lot_count": stats['lot_count'],
        "lot_percentage": stats['lot_percentage'],
        "lot_books": lot_books,
        "stats": stats
    }


def audit_training_db(db_path: Path) -> Dict:
    """
    Audit training_data.db for lot contamination.

    Args:
        db_path: Path to training_data.db

    Returns:
        Dict with audit results
    """
    if not db_path.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if training_books table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='training_books'")
    if not cursor.fetchone():
        conn.close()
        return {"error": "No 'training_books' table found in database"}

    # Query all training books with metadata
    query = """
        SELECT isbn, metadata_json
        FROM training_books
        WHERE metadata_json IS NOT NULL
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"total_books": 0, "lot_contamination": []}

    # Scan for lots
    lot_books = []
    all_titles = []

    for isbn, metadata_json in rows:
        metadata = json.loads(metadata_json) if metadata_json else {}
        title = metadata.get('title', '')

        if title:
            all_titles.append(title)

            if is_lot(title):
                reason = get_lot_detection_reason(title)
                lot_books.append({
                    "isbn": isbn,
                    "title": title,
                    "reason": reason
                })

    stats = get_lot_stats(all_titles)

    return {
        "database": str(db_path),
        "total_books": len(rows),
        "lot_count": stats['lot_count'],
        "lot_percentage": stats['lot_percentage'],
        "lot_books": lot_books,
        "stats": stats
    }


def print_audit_report(results: Dict):
    """Print formatted audit report."""
    print()
    print("=" * 80)
    print("LOT CONTAMINATION AUDIT REPORT")
    print("=" * 80)
    print()

    if "error" in results:
        print(f"❌ Error: {results['error']}")
        return

    print(f"Database: {results['database']}")
    print(f"Total books scanned: {results['total_books']}")
    print()

    if results['lot_count'] == 0:
        print("✅ No lot listings detected - data is clean!")
        return

    # Summary
    print(f"⚠️  LOT CONTAMINATION DETECTED")
    print(f"  Lot listings found: {results['lot_count']}")
    print(f"  Contamination rate: {results['lot_percentage']:.2f}%")
    print()

    # Breakdown by reason
    if results['lot_books']:
        reasons = {}
        for book in results['lot_books']:
            reason = book['reason']
            if reason not in reasons:
                reasons[reason] = []
            reasons[reason].append(book)

        print("Breakdown by detection reason:")
        for reason, books in sorted(reasons.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  {reason}: {len(books)} books")
        print()

        # Show first 10 examples
        print("Sample lot listings (first 10):")
        for i, book in enumerate(results['lot_books'][:10], 1):
            print(f"  {i}. ISBN: {book['isbn']}")
            print(f"     Title: {book['title']}")
            print(f"     Reason: {book['reason']}")
            print()

        if len(results['lot_books']) > 10:
            print(f"  ... and {len(results['lot_books']) - 10} more")
            print()

    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()

    if results['lot_percentage'] < 1.0:
        print("✓ Low contamination rate (<1%) - acceptable noise level")
    elif results['lot_percentage'] < 5.0:
        print("⚠️  Moderate contamination (1-5%) - consider cleaning")
    else:
        print("❌ High contamination (>5%) - cleaning recommended!")

    print()
    print("Actions:")
    print("1. Re-run data collection with updated lot filtering")
    print("2. Remove contaminated records from database:")
    print(f"   DELETE FROM books WHERE isbn IN ({', '.join(repr(b['isbn']) for b in results['lot_books'][:5])}, ...)")
    print("3. Retrain ML model with cleaned data")
    print()


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent

    print("Starting lot contamination audit...")
    print()

    # Audit catalog.db
    catalog_path = project_root / "catalog.db"
    print(f"Auditing {catalog_path}...")
    catalog_results = audit_catalog_db(catalog_path)
    print_audit_report(catalog_results)

    print()
    print()

    # Audit training_data.db
    training_path = project_root / "training_data.db"
    print(f"Auditing {training_path}...")
    training_results = audit_training_db(training_path)
    print_audit_report(training_results)

    print()
    print("Audit complete!")
