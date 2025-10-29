#!/usr/bin/env python3
"""Test script for ePID discovery and comprehensive Item Specifics.

This script demonstrates the complete eBay listing workflow:
1. Analyze keywords for an ISBN (discovers ePID automatically)
2. Check if ePID was found
3. Show how listing would be created with ePID (auto-populated)
4. Show how listing would be created without ePID (manual aspects)

Usage:
    python3 tests/test_epid_discovery.py [isbn]

Example:
    python3 tests/test_epid_discovery.py 9780553381689
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
env_file = PROJECT_ROOT / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from isbn_lot_optimizer.keyword_analyzer import KeywordAnalyzer
from isbn_lot_optimizer.ebay_product_cache import EbayProductCache
from isbn_lot_optimizer.service import BookService


def test_epid_discovery(isbn: str):
    """Test ePID discovery for an ISBN."""

    print("\n" + "=" * 80)
    print(f"eBay PRODUCT ID (ePID) DISCOVERY TEST")
    print("=" * 80)
    print(f"\nISBN: {isbn}")

    # Initialize services
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    book_service = BookService(db_path)

    # Initialize keyword analyzer with ePID caching enabled
    analyzer = KeywordAnalyzer(db_path=db_path)
    epid_cache = EbayProductCache(db_path)

    # Step 1: Load book from database
    print("\n" + "-" * 80)
    print("[1/5] Loading book from database...")
    print("-" * 80)

    book = book_service.get_book(isbn)
    if not book:
        print(f"✗ Book not found in database: {isbn}")
        print("\nPlease scan this book first or provide a different ISBN.")
        sys.exit(1)

    print(f"✓ Found: {book.metadata.title}")
    if book.metadata.authors:
        print(f"  Author: {', '.join(book.metadata.authors)}")
    if book.metadata.published_year:
        print(f"  Year: {book.metadata.published_year}")

    # Step 2: Check if ePID already cached
    print("\n" + "-" * 80)
    print("[2/5] Checking ePID cache...")
    print("-" * 80)

    existing_epid = epid_cache.get_epid(isbn)
    if existing_epid:
        print(f"✓ ePID already cached: {existing_epid}")
        product = epid_cache.get_product(isbn)
        if product:
            print(f"  Product Title: {product.product_title}")
            print(f"  Product URL: {product.product_url}")
            print(f"  Discovered: {product.discovered_at}")
            print(f"  Times Used: {product.times_used}")
            print(f"  Success Rate: {product.success_count}/{product.times_used}")
    else:
        print("  No ePID cached yet")

    # Step 3: Run keyword analysis (discovers ePID automatically)
    print("\n" + "-" * 80)
    print("[3/5] Analyzing keywords (ePID discovery happens automatically)...")
    print("-" * 80)

    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=100)

    if not keywords:
        print("✗ No keywords found (book may not have eBay listings)")
    else:
        print(f"✓ Found {len(keywords)} keywords")
        print(f"  Top 5 keywords:")
        for i, kw in enumerate(keywords[:5], 1):
            print(f"    {i}. '{kw.word}' (score: {kw.score:.2f}, freq: {kw.frequency})")

    # Step 4: Check if ePID was discovered
    print("\n" + "-" * 80)
    print("[4/5] Checking if ePID was discovered...")
    print("-" * 80)

    epid = analyzer.get_epid(isbn)

    if epid:
        print(f"✓ ePID FOUND: {epid}")
        print(f"  Product URL: https://www.ebay.com/p/{epid}")
        print()
        print("  🎉 This book will use AUTO-POPULATED Item Specifics!")
        print("     eBay will automatically fill in:")
        print("     - Product title, author, publisher")
        print("     - Publication year, pages, ISBN")
        print("     - Genre, format, and other catalog data")
        print()
        print("  iOS wizard will be SIMPLIFIED (5 steps instead of 7)")

        # Show cached product info
        product = epid_cache.get_product(isbn)
        if product:
            print(f"\n  Cached Product Info:")
            print(f"    Title: {product.product_title}")
            print(f"    Category: {product.category_id or 'Unknown'}")
    else:
        print("  ✗ No ePID found")
        print()
        print("  This book will use MANUAL Item Specifics")
        print("  iOS wizard will ask for comprehensive details:")
        print("  - Format (Hardcover, Paperback, etc.)")
        print("  - Publisher, pages, genre")
        print("  - Language, features, special attributes")
        print()
        print("  iOS wizard will be COMPREHENSIVE (7 steps)")

    # Step 5: Show what Item Specifics would be populated
    print("\n" + "-" * 80)
    print("[5/5] Item Specifics Preview...")
    print("-" * 80)

    if epid:
        print("\n✓ WITH ePID (Auto-Populated by eBay):")
        print("  {")
        print(f'    "eBayProductID": "{epid}",')
        print('    "imageUrls": [...]')
        print("  }")
        print()
        print("  eBay will automatically add 20+ Item Specifics from their catalog!")
    else:
        print("\n✓ WITHOUT ePID (Manual Aspects from Metadata + User):")

        # Build preview aspects
        aspects = {}

        # From metadata
        if book.metadata.authors:
            aspects["Author"] = [", ".join(book.metadata.authors)]
        if book.metadata.published_year:
            aspects["Publication Year"] = [str(book.metadata.published_year)]
        if book.metadata.raw and "Publisher" in book.metadata.raw:
            aspects["Publisher"] = [book.metadata.raw["Publisher"]]
        if book.metadata.page_count:
            aspects["Number of Pages"] = [str(book.metadata.page_count)]
        if book.metadata.series_name:
            aspects["Book Series"] = [book.metadata.series_name]

        # Derived
        if book.metadata.categories:
            categories_str = " ".join(book.metadata.categories).lower()
            if "fiction" in categories_str:
                aspects["Narrative Type"] = ["Fiction"]
            elif any(kw in categories_str for kw in ["biography", "history", "science"]):
                aspects["Narrative Type"] = ["Nonfiction"]

        # User-provided (examples)
        aspects["Format"] = ["Hardcover"]  # From user
        aspects["Language"] = ["English"]  # Default
        aspects["Features"] = ["Dust Jacket", "First Edition"]  # From user

        print("  {")
        print('    "aspects": {')
        for i, (key, values) in enumerate(aspects.items()):
            comma = "," if i < len(aspects) - 1 else ""
            values_str = ", ".join(f'"{v}"' for v in values)
            print(f'      "{key}": [{values_str}]{comma}')
        print("    },")
        print('    "ean": [...]')
        print("  }")
        print()
        print(f"  Total: {len(aspects)} Item Specifics from metadata + user inputs")

    # Show cache stats
    print("\n" + "-" * 80)
    print("ePID Cache Statistics:")
    print("-" * 80)

    stats = epid_cache.get_stats()
    print(f"  Total ePIDs cached: {stats['total_entries']}")
    print(f"  Total uses: {stats['total_uses']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    return {
        'isbn': isbn,
        'epid_found': epid is not None,
        'epid': epid,
        'keywords_found': len(keywords) if keywords else 0,
    }


def main():
    """Run the ePID discovery test."""

    # Default ISBN (Game of Thrones)
    default_isbn = "9780553381689"

    if len(sys.argv) > 1:
        isbn = sys.argv[1]
    else:
        isbn = default_isbn
        print(f"Using default ISBN: {isbn}")
        print(f"(Specify a different ISBN: python3 tests/test_epid_discovery.py <isbn>)")

    try:
        result = test_epid_discovery(isbn)

        # Exit with success
        if result['epid_found']:
            print("\n✓ SUCCESS: ePID discovered and cached!")
            print(f"  Future listings for this ISBN will use auto-populated Item Specifics")
        else:
            print("\n⚠️  No ePID found (book may be rare or not in eBay catalog)")
            print(f"  Listings will use comprehensive manual Item Specifics instead")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
