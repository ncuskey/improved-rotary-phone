#!/usr/bin/env python3
"""
Check for books with missing or broken cover images.

This script:
1. Scans all books in the database
2. Checks if cover URLs are valid (metadata)
3. Verifies if cover images actually exist/load
4. Downloads missing covers from fallback sources
5. Updates database with working cover URLs

Usage:
    python scripts/check_missing_covers.py --check-only
    python scripts/check_missing_covers.py --fix
    python scripts/check_missing_covers.py --fix --force-redownload
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import requests

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.database import DatabaseManager
from shared.utils import normalise_isbn
from isbn_lot_optimizer.metadata import OPENLIB_COVER_TMPL, OPENLIB_COVER_BY_ID


# Cover URL templates from various sources
COVER_SOURCES = [
    "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg",
    "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
    "https://books.google.com/books/content?id={google_id}&printsec=frontcover&img=1&zoom=1",
]

# Known placeholder images that indicate "no cover available"
PLACEHOLDER_INDICATORS = [
    b"data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==",  # 1x1 transparent
    b"<!DOCTYPE html>",  # HTML error page
    b"<html",  # HTML error page
]


class CoverChecker:
    """Check and fix missing book covers."""

    def __init__(self, db_path: Path, cache_dir: Optional[Path] = None):
        self.db = DatabaseManager(db_path)
        self.cache_dir = cache_dir or Path.home() / ".isbn_lot_optimizer" / "covers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def check_cover_url(self, url: str, timeout: float = 5.0) -> Tuple[bool, Optional[int]]:
        """
        Check if a cover URL returns a valid image.

        Returns:
            (is_valid, content_length) tuple
        """
        if not url or not url.startswith("http"):
            return False, None

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                # Use GET instead of HEAD for better compatibility with Open Library
                # Open Library returns 302 redirects that need to be followed
                response = await client.get(url)

                # Check HTTP status
                if response.status_code != 200:
                    return False, None

                # Check content type
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    return False, None

                # Check content length from actual content
                content_length = len(response.content)
                if content_length < 1000:
                    return False, content_length

                return True, content_length

        except Exception as e:
            return False, None

    async def download_cover(self, url: str, timeout: float = 10.0) -> Optional[bytes]:
        """
        Download cover image and verify it's not a placeholder.

        Returns:
            Image bytes if valid, None otherwise
        """
        if not url or not url.startswith("http"):
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    return None

                content = response.content

                # Check if it's a placeholder
                for indicator in PLACEHOLDER_INDICATORS:
                    if indicator in content[:500]:  # Check first 500 bytes
                        return None

                # Must be at least 1KB
                if len(content) < 1000:
                    return None

                return content

        except Exception as e:
            return None

    async def find_working_cover(self, isbn: str, isbn_10: Optional[str] = None) -> Optional[str]:
        """
        Try multiple sources to find a working cover URL.

        Returns:
            Working cover URL or None
        """
        candidates = []

        # Try ISBN-13
        if isbn:
            candidates.append(f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg")
            candidates.append(f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg")

        # Try ISBN-10
        if isbn_10:
            candidates.append(f"https://covers.openlibrary.org/b/isbn/{isbn_10}-L.jpg")
            candidates.append(f"https://covers.openlibrary.org/b/isbn/{isbn_10}-M.jpg")

        # Test each candidate
        for url in candidates:
            is_valid, size = await self.check_cover_url(url)
            if is_valid:
                return url

        return None

    async def check_all_books(self, fix: bool = False, force_redownload: bool = False) -> Dict[str, Any]:
        """
        Check all books for missing covers.

        Args:
            fix: If True, attempt to download missing covers
            force_redownload: If True, re-check and re-download all covers

        Returns:
            Statistics dict
        """
        rows = self.db.fetch_all_books()
        total = len(rows)

        stats = {
            "total": total,
            "checked": 0,
            "valid": 0,
            "missing": 0,
            "broken": 0,
            "fixed": 0,
            "failed": 0,
        }

        missing_covers: List[Dict[str, Any]] = []
        broken_covers: List[Dict[str, Any]] = []

        print(f"Checking {total} books for cover images...")
        print("-" * 60)

        for idx, row in enumerate(rows):
            isbn = row["isbn"]
            title = row["title"] or isbn

            # Extract cover URL from metadata_json
            import json
            metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else None
            if metadata_json:
                try:
                    metadata = json.loads(metadata_json)
                    cover_url = metadata.get("cover_url") or metadata.get("thumbnail")
                except Exception:
                    cover_url = None
            else:
                cover_url = None

            stats["checked"] += 1

            # Progress indicator
            if (idx + 1) % 10 == 0:
                print(f"Progress: {idx + 1}/{total} ({stats['valid']} valid, {stats['missing']} missing, {stats['broken']} broken)")

            # Case 1: No cover URL in metadata
            if not cover_url:
                stats["missing"] += 1
                missing_covers.append({
                    "isbn": isbn,
                    "title": title,
                    "reason": "no_url",
                })

                if fix:
                    # Try to find a working cover
                    new_url = await self.find_working_cover(isbn)
                    if new_url:
                        # Update database
                        self._update_cover_url(isbn, new_url)
                        stats["fixed"] += 1
                        print(f"  ✅ Fixed: {title[:50]} -> {new_url}")
                    else:
                        stats["failed"] += 1
                        print(f"  ❌ No cover found: {title[:50]}")

                continue

            # Case 2: Cover URL exists, check if valid (or force recheck)
            if force_redownload or True:  # Always check in this mode
                is_valid, size = await self.check_cover_url(cover_url)

                if is_valid:
                    stats["valid"] += 1
                else:
                    stats["broken"] += 1
                    broken_covers.append({
                        "isbn": isbn,
                        "title": title,
                        "url": cover_url,
                        "reason": "broken_link",
                    })

                    if fix:
                        # Try to find a replacement
                        new_url = await self.find_working_cover(isbn)
                        if new_url and new_url != cover_url:
                            self._update_cover_url(isbn, new_url)
                            stats["fixed"] += 1
                            print(f"  ✅ Fixed: {title[:50]} -> {new_url}")
                        else:
                            stats["failed"] += 1
                            print(f"  ❌ Could not fix: {title[:50]}")

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total books:      {stats['total']}")
        print(f"Checked:          {stats['checked']}")
        print(f"Valid covers:     {stats['valid']} ({stats['valid']/total*100:.1f}%)")
        print(f"Missing covers:   {stats['missing']} ({stats['missing']/total*100:.1f}%)")
        print(f"Broken covers:    {stats['broken']} ({stats['broken']/total*100:.1f}%)")

        if fix:
            print(f"\nFixed:            {stats['fixed']}")
            print(f"Failed to fix:    {stats['failed']}")

        return stats

    def _update_cover_url(self, isbn: str, new_url: str) -> None:
        """Update the cover_url in metadata_json for a book."""
        import json

        row = self.db.fetch_book(isbn)
        if not row:
            return

        metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except Exception:
                metadata = {}
        else:
            metadata = {}

        metadata["cover_url"] = new_url
        metadata["thumbnail"] = new_url  # Update both fields

        # Use upsert_book to update the metadata
        self.db.upsert_book({
            "isbn": isbn,
            "metadata_json": metadata,
            # Include existing fields to avoid overwriting
            "title": row["title"] if "title" in row.keys() else None,
            "authors": row["authors"] if "authors" in row.keys() else None,
            "publication_year": row["publication_year"] if "publication_year" in row.keys() else None,
            "condition": row["condition"] if "condition" in row.keys() else "Good",
            "estimated_price": row["estimated_price"] if "estimated_price" in row.keys() else 0.0,
            "probability_label": row["probability_label"] if "probability_label" in row.keys() else "Unknown",
            "probability_score": row["probability_score"] if "probability_score" in row.keys() else 0.0,
            "probability_reasons": row["probability_reasons"] if "probability_reasons" in row.keys() else "",
            "sell_through": row["sell_through"] if "sell_through" in row.keys() else None,
            "ebay_active_count": row["ebay_active_count"] if "ebay_active_count" in row.keys() else None,
            "ebay_sold_count": row["ebay_sold_count"] if "ebay_sold_count" in row.keys() else None,
            "ebay_currency": row["ebay_currency"] if "ebay_currency" in row.keys() else None,
            "market_json": row["market_json"] if "market_json" in row.keys() else None,
            "booksrun_json": row["booksrun_json"] if "booksrun_json" in row.keys() else None,
            "bookscouter_json": row["bookscouter_json"] if "bookscouter_json" in row.keys() else None,
            "source_json": row["source_json"] if "source_json" in row.keys() else None,
        })


async def main():
    parser = argparse.ArgumentParser(description="Check and fix missing book covers")

    # Try to find the database automatically
    default_locations = [
        Path.home() / ".isbn_lot_optimizer" / "catalog.db",
        Path.home() / ".isbn_lot_optimizer" / "books.db",
        Path.cwd() / "catalog.db",
        Path.cwd() / "books.db",
    ]

    default_db = None
    for location in default_locations:
        if location.exists():
            default_db = str(location)
            break

    if not default_db:
        default_db = str(Path.home() / ".isbn_lot_optimizer" / "catalog.db")

    parser.add_argument(
        "--db",
        default=default_db,
        help="Path to database file (default: auto-detected or ~/.isbn_lot_optimizer/catalog.db)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for missing covers, don't fix",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to download and fix missing covers",
    )
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        help="Re-check all covers, even if they seem valid",
    )

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    checker = CoverChecker(db_path)

    # Determine mode
    fix = args.fix
    if not args.check_only and not args.fix:
        # Default to check-only mode
        fix = False

    # Run the check
    stats = await checker.check_all_books(
        fix=fix,
        force_redownload=args.force_redownload,
    )

    # Exit code based on results
    if stats["missing"] > 0 or stats["broken"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
