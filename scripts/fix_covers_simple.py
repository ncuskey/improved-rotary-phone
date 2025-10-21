#!/usr/bin/env python3
"""
Simple cover fixer - assumes Open Library covers exist, focuses on missing only.

This is faster than the full checker because it:
1. Only fixes books with NO cover URL (truly missing)
2. Doesn't validate existing URLs (assumes they work)
3. Only downloads when actually needed

Usage:
    python scripts/fix_covers_simple.py --check
    python scripts/fix_covers_simple.py --fix
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.database import DatabaseManager


async def check_and_fix_covers(db_path: Path, fix: bool = False):
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
    print("-" * 60)

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for idx, row in enumerate(missing_books):
            isbn = row["isbn"]
            title = row["title"] or isbn

            # Try multiple sources in order
            sources = [
                f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg",
                f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
            ]

            # Try to fetch from Google Books API if we don't have a cover
            try:
                google_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
                google_resp = await client.get(google_url, timeout=5.0)
                if google_resp.status_code == 200:
                    google_data = google_resp.json()
                    items = google_data.get("items", [])
                    if items:
                        volume_info = items[0].get("volumeInfo", {})
                        image_links = volume_info.get("imageLinks", {})
                        google_thumb = image_links.get("thumbnail") or image_links.get("smallThumbnail")
                        if google_thumb:
                            # Upgrade to larger image
                            if "zoom=5" in google_thumb:
                                google_thumb = google_thumb.replace("zoom=5", "zoom=1")
                            elif "zoom=" not in google_thumb:
                                google_thumb = f"{google_thumb}{'&' if '?' in google_thumb else '?'}zoom=1"
                            sources.insert(0, google_thumb)  # Try Google first
            except:
                pass

            url = None
            for source in sources:
                try:
                    response = await client.get(source, timeout=10.0)
                    if response.status_code == 200 and len(response.content) > 1000:
                        url = source
                        break
                except:
                    continue

            if url:
                # Found a working cover!
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
                    source_name = "Google Books" if "books.google" in url else "Open Library"
                    print(f"  ✅ {idx+1}/{stats['missing_url']}: {title[:50]} ({source_name})")
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ {idx+1}/{stats['missing_url']}: {title[:50]} (error: {e})")
            else:
                stats["failed"] += 1
                print(f"  ❌ {idx+1}/{stats['missing_url']}: {title[:50]} (no cover found)")

            # Rate limiting
            await asyncio.sleep(0.5)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Books fixed:         {stats['fixed']}")
    print(f"Failed to fix:       {stats['failed']}")
    print(f"\n✅ Done! {stats['fixed']} covers added to database")

    return stats


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Simple cover fixer")

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

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    fix_mode = args.fix
    if not args.check and not args.fix:
        fix_mode = False  # Default to check mode

    await check_and_fix_covers(db_path, fix=fix_mode)


if __name__ == "__main__":
    asyncio.run(main())
