#!/usr/bin/env python3
"""
Advanced cover fixer with multiple fallback sources.

Sources tried in order:
1. Google Books API (best quality, official)
2. BookScouter API (Amazon & ISBNDB images)
3. Open Library (large -L.jpg)
4. Open Library (medium -M.jpg)
5. Internet Archive (archive.org)
6. Goodreads (via ISBN search)

Usage:
    python scripts/fix_covers_advanced.py --check
    python scripts/fix_covers_advanced.py --fix
    python scripts/fix_covers_advanced.py --fix --verbose
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

import httpx

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.database import DatabaseManager


class AdvancedCoverFinder:
    """Find book covers from multiple sources with fallbacks."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.stats = {
            "google_books": 0,
            "bookscouter": 0,
            "openlibrary_large": 0,
            "openlibrary_medium": 0,
            "internet_archive": 0,
            "goodreads": 0,
        }

    async def find_cover(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """
        Try multiple sources to find a cover image.

        Returns:
            (cover_url, source_name) tuple
        """
        # 1. Google Books API (best quality)
        url, source = await self._try_google_books(isbn, client)
        if url:
            return url, source

        # 2. BookScouter API (Amazon & ISBNDB images)
        url, source = await self._try_bookscouter(isbn, client)
        if url:
            return url, source

        # 3. Open Library Large
        url, source = await self._try_openlibrary_large(isbn, client)
        if url:
            return url, source

        # 4. Open Library Medium
        url, source = await self._try_openlibrary_medium(isbn, client)
        if url:
            return url, source

        # 5. Internet Archive
        url, source = await self._try_internet_archive(isbn, client)
        if url:
            return url, source

        # 6. Goodreads
        url, source = await self._try_goodreads(isbn, client)
        if url:
            return url, source

        return None, None

    async def _validate_image(self, url: str, client: httpx.AsyncClient, min_size: int = 1000) -> bool:
        """Check if URL returns a valid image."""
        try:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                content = response.content
                # Check size
                if len(content) < min_size:
                    return False
                # Check for common "no image" indicators
                if b"<!DOCTYPE" in content[:500] or b"<html" in content[:500]:
                    return False
                return True
        except:
            pass
        return False

    async def _try_google_books(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try Google Books API."""
        if self.verbose:
            print(f"    Trying Google Books...")

        try:
            url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
            response = await client.get(url, timeout=5.0)

            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])

                if items:
                    volume_info = items[0].get("volumeInfo", {})
                    image_links = volume_info.get("imageLinks", {})
                    cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")

                    if cover_url:
                        # Upgrade to larger image
                        if "zoom=5" in cover_url:
                            cover_url = cover_url.replace("zoom=5", "zoom=1")
                        elif "zoom=" not in cover_url:
                            cover_url = f"{cover_url}{'&' if '?' in cover_url else '?'}zoom=1"

                        if await self._validate_image(cover_url, client):
                            self.stats["google_books"] += 1
                            return cover_url, "Google Books"
        except:
            pass

        return None, None

    async def _try_bookscouter(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try BookScouter API."""
        if self.verbose:
            print(f"    Trying BookScouter...")

        try:
            # BookScouter API key (from user's config)
            api_key = "0c7cd0b1712cd7da21d1a4d4855667ed"
            url = f"https://api.bookscouter.com/services/v1/books?apiKey={api_key}&isbns[]={isbn}"
            response = await client.get(url, timeout=5.0)

            if response.status_code == 200:
                data = response.json()
                books = data.get("books", {})

                # BookScouter normalizes ISBNs, so we need to check all returned books
                for book_isbn, book_data in books.items():
                    image_url = book_data.get("Image")
                    if image_url:
                        # Upgrade thumbnail to larger size if it's from Amazon
                        if "amazon.com/images" in image_url:
                            # Replace _SL75_ with larger size like _SL500_
                            image_url = image_url.replace("_SL75_", "_SL500_")

                        if await self._validate_image(image_url, client):
                            self.stats["bookscouter"] += 1
                            source = "BookScouter (Amazon)" if "amazon.com" in image_url else "BookScouter (ISBNDB)"
                            return image_url, source
        except:
            pass

        return None, None

    async def _try_openlibrary_large(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try Open Library large size."""
        if self.verbose:
            print(f"    Trying Open Library (Large)...")

        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        if await self._validate_image(url, client):
            self.stats["openlibrary_large"] += 1
            return url, "Open Library (L)"

        return None, None

    async def _try_openlibrary_medium(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try Open Library medium size."""
        if self.verbose:
            print(f"    Trying Open Library (Medium)...")

        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
        if await self._validate_image(url, client):
            self.stats["openlibrary_medium"] += 1
            return url, "Open Library (M)"

        return None, None

    async def _try_internet_archive(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try Internet Archive."""
        if self.verbose:
            print(f"    Trying Internet Archive...")

        try:
            # Search Internet Archive for the book
            search_url = f"https://archive.org/advancedsearch.php?q=isbn:{isbn}&output=json"
            response = await client.get(search_url, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                docs = data.get("response", {}).get("docs", [])

                if docs:
                    identifier = docs[0].get("identifier")
                    if identifier:
                        # Try to get cover from Internet Archive
                        cover_url = f"https://archive.org/services/img/{identifier}"
                        if await self._validate_image(cover_url, client):
                            self.stats["internet_archive"] += 1
                            return cover_url, "Internet Archive"
        except:
            pass

        return None, None

    async def _try_goodreads(self, isbn: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
        """Try Goodreads (via web scraping - use sparingly)."""
        if self.verbose:
            print(f"    Trying Goodreads...")

        try:
            # Search Goodreads for ISBN
            search_url = f"https://www.goodreads.com/search?q={isbn}"
            response = await client.get(search_url, timeout=10.0, follow_redirects=True)

            if response.status_code == 200:
                html = response.text
                # Look for book cover image in HTML
                # Goodreads images are in format: https://i.gr-assets.com/images/...
                match = re.search(r'(https://i\.gr-assets\.com/images/[^"\']+)', html)
                if match:
                    cover_url = match.group(1)
                    # Remove size suffixes to get larger image
                    cover_url = re.sub(r'\._SX\d+_', '', cover_url)
                    cover_url = re.sub(r'\._SY\d+_', '', cover_url)

                    if await self._validate_image(cover_url, client, min_size=5000):
                        self.stats["goodreads"] += 1
                        return cover_url, "Goodreads"
        except:
            pass

        return None, None


async def check_and_fix_covers(db_path: Path, fix: bool = False, verbose: bool = False):
    """Check for missing covers and optionally fix them."""
    db = DatabaseManager(db_path)
    rows = db.fetch_all_books()

    stats = {
        "total": len(rows),
        "has_url": 0,
        "missing_url": 0,
        "fixed": 0,
        "failed": 0,
    }

    print(f"Analyzing {stats['total']} books...")
    print("-" * 60)

    missing_books = []

    for row in rows:
        isbn = row["isbn"]
        metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else None

        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
                has_cover = bool(metadata.get("cover_url") or metadata.get("thumbnail"))
            except:
                has_cover = False
        else:
            has_cover = False

        if has_cover:
            stats["has_url"] += 1
        else:
            stats["missing_url"] += 1
            missing_books.append(row)

    print(f"\n📊 Statistics:")
    print(f"   Total books:         {stats['total']}")
    print(f"   Have cover URLs:     {stats['has_url']} ({stats['has_url']/stats['total']*100:.1f}%)")
    print(f"   Missing cover URLs:  {stats['missing_url']} ({stats['missing_url']/stats['total']*100:.1f}%)")

    if not fix:
        print(f"\n💡 Run with --fix to add cover URLs for the {stats['missing_url']} missing books")
        return stats

    if stats["missing_url"] == 0:
        print("\n✅ All books already have cover URLs!")
        return stats

    print(f"\n🔧 Fixing {stats['missing_url']} books with missing covers...")
    print("   Using advanced multi-source finder (Google Books, Open Library, Internet Archive, Goodreads)")
    print("-" * 60)

    finder = AdvancedCoverFinder(verbose=verbose)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for idx, row in enumerate(missing_books):
            isbn = row["isbn"]
            title = row["title"] or isbn

            if verbose:
                print(f"\n  [{idx+1}/{stats['missing_url']}] {title[:50]}")

            # Try to find cover from multiple sources
            url, source = await finder.find_cover(isbn, client)

            if url:
                # Found a cover!
                metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else None
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except:
                        metadata = {}
                else:
                    metadata = {}

                metadata["cover_url"] = url
                metadata["thumbnail"] = url

                try:
                    # Update database
                    db.upsert_book({
                        "isbn": isbn,
                        "metadata_json": metadata,
                        "title": row["title"] if "title" in row.keys() else None,
                        "authors": row["authors"] if "authors" in row.keys() else None,
                        "publication_year": row["publication_year"] if "publication_year" in row.keys() else None,
                        "edition": row["edition"] if "edition" in row.keys() else None,
                        "condition": row["condition"] if "condition" in row.keys() else "Good",
                        "estimated_price": row["estimated_price"] if "estimated_price" in row.keys() else 0.0,
                        "price_reference": row["price_reference"] if "price_reference" in row.keys() else 0.0,
                        "rarity": row["rarity"] if "rarity" in row.keys() else None,
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
                        "sold_comps_count": row["sold_comps_count"] if "sold_comps_count" in row.keys() else None,
                        "sold_comps_min": row["sold_comps_min"] if "sold_comps_min" in row.keys() else None,
                        "sold_comps_median": row["sold_comps_median"] if "sold_comps_median" in row.keys() else None,
                        "sold_comps_max": row["sold_comps_max"] if "sold_comps_max" in row.keys() else None,
                        "sold_comps_is_estimate": row["sold_comps_is_estimate"] if "sold_comps_is_estimate" in row.keys() else None,
                        "sold_comps_source": row["sold_comps_source"] if "sold_comps_source" in row.keys() else None,
                    })

                    stats["fixed"] += 1
                    if not verbose:
                        print(f"  ✅ {idx+1}/{stats['missing_url']}: {title[:50]} ({source})")
                    else:
                        print(f"  ✅ Found via {source}")
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ {idx+1}/{stats['missing_url']}: {title[:50]} (DB error: {e})")
            else:
                stats["failed"] += 1
                if not verbose:
                    print(f"  ❌ {idx+1}/{stats['missing_url']}: {title[:50]} (no cover found)")
                else:
                    print(f"  ❌ No cover found from any source")

            # Rate limiting (be respectful to APIs)
            await asyncio.sleep(1.0)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Books fixed:         {stats['fixed']}")
    print(f"Failed to fix:       {stats['failed']}")

    print(f"\n📊 Covers found by source:")
    print(f"   Google Books:       {finder.stats['google_books']}")
    print(f"   BookScouter:        {finder.stats['bookscouter']}")
    print(f"   Open Library (L):   {finder.stats['openlibrary_large']}")
    print(f"   Open Library (M):   {finder.stats['openlibrary_medium']}")
    print(f"   Internet Archive:   {finder.stats['internet_archive']}")
    print(f"   Goodreads:          {finder.stats['goodreads']}")

    print(f"\n✅ Done! {stats['fixed']} covers added to database")

    return stats


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Advanced multi-source cover fixer")

    # Auto-detect database
    default_locations = [
        Path.home() / ".isbn_lot_optimizer" / "catalog.db",
        Path.home() / ".isbn_lot_optimizer" / "books.db",
    ]
    default_db = None
    for location in default_locations:
        if location.exists():
            default_db = str(location)
            break
    if not default_db:
        default_db = str(Path.home() / ".isbn_lot_optimizer" / "catalog.db")

    parser.add_argument("--db", default=default_db, help="Database path")
    parser.add_argument("--check", action="store_true", help="Check only (don't fix)")
    parser.add_argument("--fix", action="store_true", help="Fix missing covers")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    fix_mode = args.fix
    if not args.check and not args.fix:
        fix_mode = False  # Default to check mode

    await check_and_fix_covers(db_path, fix=fix_mode, verbose=args.verbose)


if __name__ == "__main__":
    asyncio.run(main())
