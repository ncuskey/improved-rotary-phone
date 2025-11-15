"""
Collect metadata for ISBNs that have BookFinder edition data but no metadata yet.

This enables training the edition premium calibration model on the full dataset of 500+ ISBNs.
"""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient
from shared.models import BookMetadata


async def collect_metadata_for_isbn(api: DecodoClient, isbn: str) -> tuple[str, BookMetadata | None]:
    """
    Collect metadata for a single ISBN using Decodo Core API.

    Args:
        api: Decodo API client
        isbn: ISBN to collect

    Returns:
        Tuple of (isbn, metadata or None if failed)
    """
    try:
        metadata = await api.get_book_metadata(isbn)
        return (isbn, metadata)
    except Exception as e:
        print(f"  Failed to collect {isbn}: {e}")
        return (isbn, None)


async def collect_metadata_batch(isbns: list[str], concurrency: int = 10) -> dict[str, BookMetadata]:
    """
    Collect metadata for a batch of ISBNs with controlled concurrency.

    Args:
        isbns: List of ISBNs to collect
        concurrency: Maximum concurrent requests

    Returns:
        Dict mapping ISBN to BookMetadata (only successful collections)
    """
    # Load credentials from environment
    username = os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_PASSWORD")

    if not username or not password:
        raise ValueError("DECODO_AUTHENTICATION and DECODO_PASSWORD environment variables required")

    api = DecodoClient(username=username, password=password)

    results = {}
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_with_semaphore(isbn: str):
        async with semaphore:
            return await collect_metadata_for_isbn(api, isbn)

    # Process in batches
    total = len(isbns)
    for i in range(0, total, 50):
        batch = isbns[i:i+50]
        print(f"\nProcessing batch {i//50 + 1} ({i+1}-{min(i+50, total)} of {total})...")

        tasks = [fetch_with_semaphore(isbn) for isbn in batch]
        batch_results = await asyncio.gather(*tasks)

        for isbn, metadata in batch_results:
            if metadata:
                results[isbn] = metadata

        success_count = sum(1 for _, m in batch_results if m is not None)
        print(f"  Collected: {success_count}/{len(batch)}")

    return results


def save_to_metadata_cache(results: dict[str, BookMetadata], db_path: Path):
    """
    Save collected metadata to metadata_cache.db.

    Args:
        results: Dict mapping ISBN to BookMetadata
        db_path: Path to metadata_cache.db
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure cached_books table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cached_books (
            isbn TEXT PRIMARY KEY,
            title TEXT,
            authors TEXT,
            publisher TEXT,
            publication_year INTEGER,
            page_count INTEGER,
            binding TEXT,
            categories TEXT,
            description TEXT,
            thumbnail TEXT,
            info_link TEXT,
            canonical_author TEXT,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    inserted = 0
    updated = 0

    for isbn, metadata in results.items():
        # Check if ISBN already exists
        cursor.execute("SELECT isbn FROM cached_books WHERE isbn = ?", (isbn,))
        exists = cursor.fetchone() is not None

        # Prepare data
        authors_str = ", ".join(metadata.authors) if metadata.authors else metadata.canonical_author or ""
        categories_str = ", ".join(metadata.categories) if metadata.categories else ""

        if exists:
            cursor.execute("""
                UPDATE cached_books
                SET title = ?,
                    authors = ?,
                    publisher = ?,
                    publication_year = ?,
                    page_count = ?,
                    binding = ?,
                    categories = ?,
                    description = ?,
                    thumbnail = ?,
                    info_link = ?,
                    canonical_author = ?,
                    cached_at = CURRENT_TIMESTAMP
                WHERE isbn = ?
            """, (
                metadata.title,
                authors_str,
                metadata.publisher,
                metadata.published_year,
                metadata.page_count,
                metadata.binding,
                categories_str,
                metadata.description,
                metadata.thumbnail,
                metadata.info_link,
                metadata.canonical_author,
                isbn
            ))
            updated += 1
        else:
            cursor.execute("""
                INSERT INTO cached_books (
                    isbn, title, authors, publisher, publication_year,
                    page_count, binding, categories, description,
                    thumbnail, info_link, canonical_author
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                isbn,
                metadata.title,
                authors_str,
                metadata.publisher,
                metadata.published_year,
                metadata.page_count,
                metadata.binding,
                categories_str,
                metadata.description,
                metadata.thumbnail,
                metadata.info_link,
                metadata.canonical_author
            ))
            inserted += 1

    conn.commit()
    conn.close()

    print(f"\nSaved to metadata_cache.db:")
    print(f"  Inserted: {inserted}")
    print(f"  Updated: {updated}")


async def main():
    """Main collection pipeline."""
    print("=" * 70)
    print("BookFinder ISBN Metadata Enrichment")
    print("=" * 70)

    # Load ISBNs from file
    isbn_file = Path("/tmp/bookfinder_isbns_needing_metadata.txt")

    if not isbn_file.exists():
        print(f"\nERROR: ISBN file not found: {isbn_file}")
        print("\nPlease run this query first to generate the file:")
        print("  sqlite3 ~/.isbn_lot_optimizer/catalog.db \"...")
        sys.exit(1)

    with open(isbn_file) as f:
        isbns = [line.strip() for line in f if line.strip()]

    print(f"\nLoaded {len(isbns)} ISBNs needing metadata enrichment")

    # Collect metadata
    print("\nCollecting metadata from Decodo Core API...")
    print("(This may take 10-15 minutes for 500+ ISBNs)")

    results = await collect_metadata_batch(isbns, concurrency=5)

    print(f"\n\nCollection complete!")
    print(f"  Success: {len(results)}/{len(isbns)} ({len(results)/len(isbns)*100:.1f}%)")
    print(f"  Failed: {len(isbns) - len(results)}")

    if not results:
        print("\nNo metadata collected. Exiting.")
        sys.exit(1)

    # Save to database
    print("\nSaving to metadata_cache.db...")
    cache_db = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
    save_to_metadata_cache(results, cache_db)

    print("\n" + "=" * 70)
    print("Enrichment Complete!")
    print("=" * 70)
    print(f"\nNext step: Retrain edition premium model")
    print(f"  python scripts/train_edition_premium_model.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
