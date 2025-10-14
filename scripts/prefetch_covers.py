#!/usr/bin/env python3
"""Pre-fetch cover images for all books in the database."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from isbn_lot_optimizer.service import BookService
from isbn_web.services.cover_cache import cover_cache
from isbn_web.config import settings


async def prefetch_all_covers():
    """Fetch cover images for all books in the database."""
    # Initialize book service
    service = BookService(database_path=settings.DATABASE_PATH)

    # Get all books
    print("Loading books from database...")
    books = service.get_all_books()
    total = len(books)
    print(f"Found {total} books in database\n")

    # Track statistics
    cached = 0
    downloaded = 0
    failed = 0

    # Fetch covers with progress
    for i, book in enumerate(books, 1):
        isbn = book.isbn

        # Check if already cached
        cache_path = cover_cache._get_cache_path(isbn, "M")
        if cache_path.exists():
            print(f"[{i}/{total}] ✓ {isbn} (cached)")
            cached += 1
            continue

        # Download cover
        print(f"[{i}/{total}] ⬇ {isbn} (downloading)...", end=" ")
        cover_bytes = await cover_cache.get_cover(isbn, "M")

        if cover_bytes:
            print("✓")
            downloaded += 1
        else:
            print("✗ (not available)")
            failed += 1

        # Small delay to avoid overwhelming the API
        await asyncio.sleep(0.2)

    # Print summary
    print(f"\n{'='*50}")
    print(f"Pre-fetch complete!")
    print(f"  Already cached: {cached}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Not available: {failed}")
    print(f"  Total: {total}")
    print(f"{'='*50}")

    service.close()


if __name__ == "__main__":
    asyncio.run(prefetch_all_covers())
