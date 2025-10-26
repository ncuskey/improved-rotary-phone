#!/usr/bin/env python3
"""Diagnostic test to capture ePIDs from eBay Browse API responses.

This script makes direct Browse API calls and inspects the raw response
to validate that ePIDs are being returned and can be extracted.

Usage:
    python3 tests/test_epid_raw_api.py [isbn]
"""

import json
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

import requests
from shared.market import get_app_token


def test_browse_api_epid(isbn: str):
    """Test Browse API and extract ePID from raw response."""

    print("\n" + "=" * 80)
    print(f"eBay BROWSE API - ePID EXTRACTION DIAGNOSTIC")
    print("=" * 80)
    print(f"\nISBN: {isbn}")

    # Get OAuth token
    print("\n" + "-" * 80)
    print("[1/4] Getting OAuth token...")
    print("-" * 80)

    try:
        token = get_app_token()
        print(f"✓ Token obtained: {token[:20]}...")
    except Exception as e:
        print(f"✗ Failed to get token: {e}")
        return

    # Make Browse API call
    print("\n" + "-" * 80)
    print("[2/4] Calling eBay Browse API...")
    print("-" * 80)

    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    params = {
        "gtin": isbn,
        "limit": "50"
    }

    print(f"  URL: {url}")
    print(f"  GTIN: {isbn}")
    print(f"  Limit: 50 items")

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        print(f"  Status: {response.status_code}")

        if response.status_code != 200:
            print(f"✗ API Error: {response.status_code}")
            print(f"  Response: {response.text}")
            return

        data = response.json()
        print(f"✓ API call successful")

    except Exception as e:
        print(f"✗ Request failed: {e}")
        return

    # Analyze response
    print("\n" + "-" * 80)
    print("[3/4] Analyzing response...")
    print("-" * 80)

    item_summaries = data.get("itemSummaries", [])
    total_items = len(item_summaries)

    print(f"  Total items found: {total_items}")

    if total_items == 0:
        print("✗ No items found for this ISBN")
        print("\nThis could mean:")
        print("  - No active listings with this ISBN")
        print("  - ISBN not recognized by eBay")
        print("  - Book not available in US marketplace")
        return

    # Look for ePIDs
    print("\n" + "-" * 80)
    print("[4/4] Searching for ePIDs in items...")
    print("-" * 80)

    epids_found = []
    items_with_product = 0

    for idx, item in enumerate(item_summaries, 1):
        title = item.get("title", "Unknown")
        item_id = item.get("itemId", "Unknown")

        # Check for product field
        if "product" in item:
            items_with_product += 1
            product = item["product"]

            print(f"\n  Item #{idx}: {title[:60]}")
            print(f"    Item ID: {item_id}")
            print(f"    ✓ Has 'product' field")

            # Check for ePID
            if "epid" in product:
                epid = product["epid"]
                epids_found.append({
                    "epid": epid,
                    "title": title,
                    "item_id": item_id,
                    "product_url": f"https://www.ebay.com/p/{epid}"
                })
                print(f"    ✓✓ ePID FOUND: {epid}")
                print(f"       Product URL: https://www.ebay.com/p/{epid}")

                # Show full product data
                print(f"\n    Full product data:")
                for key, value in product.items():
                    print(f"      - {key}: {value}")
            else:
                print(f"    ✗ No 'epid' in product field")
                print(f"    Product keys: {list(product.keys())}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"\nTotal items found: {total_items}")
    print(f"Items with 'product' field: {items_with_product}")
    print(f"Items with ePID: {len(epids_found)}")

    if epids_found:
        print(f"\n✓✓ SUCCESS: Found {len(epids_found)} ePID(s)!")
        print("\nePIDs discovered:")
        for idx, epid_data in enumerate(epids_found, 1):
            print(f"\n  {idx}. ePID: {epid_data['epid']}")
            print(f"     Title: {epid_data['title'][:70]}")
            print(f"     URL: {epid_data['product_url']}")

        # Test caching
        print("\n" + "-" * 80)
        print("Testing cache storage...")
        print("-" * 80)

        from isbn_lot_optimizer.ebay_product_cache import EbayProductCache

        db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        cache = EbayProductCache(db_path)

        # Store first ePID found
        first_epid = epids_found[0]
        cache.store_epid(
            isbn=isbn,
            epid=first_epid["epid"],
            product_title=first_epid["title"],
            product_url=first_epid["product_url"],
        )

        print(f"✓ Cached ePID {first_epid['epid']} for ISBN {isbn}")

        # Verify retrieval
        retrieved_epid = cache.get_epid(isbn)
        if retrieved_epid == first_epid["epid"]:
            print(f"✓ Successfully retrieved ePID from cache: {retrieved_epid}")
        else:
            print(f"✗ Cache retrieval failed")

        return True

    else:
        print(f"\n⚠️  No ePIDs found in {total_items} items")
        print("\nPossible reasons:")
        print("  - These are manual seller listings (not product-based)")
        print("  - Book not in eBay catalog")
        print("  - Older edition without catalog entry")

        # Show sample item for debugging
        if item_summaries:
            print("\n" + "-" * 80)
            print("Sample item (first result):")
            print("-" * 80)
            sample = item_summaries[0]
            print(json.dumps(sample, indent=2)[:2000])  # First 2000 chars
            print("\n...")

        return False


def main():
    """Run the diagnostic test with multiple popular ISBNs."""

    # Test with multiple popular books known to have eBay listings
    test_isbns = [
        ("9780545010221", "Harry Potter and the Deathly Hallows"),
        ("9780439023481", "The Hunger Games (Book 1)"),
        ("9780439064873", "Harry Potter and the Chamber of Secrets"),
        ("9781338635171", "Harry Potter Box Set"),
        ("9780345339683", "The Hobbit"),
        ("9780439136365", "Harry Potter and the Prisoner of Azkaban"),
    ]

    if len(sys.argv) > 1:
        # User provided ISBN
        isbn = sys.argv[1]
        print(f"Testing with user-provided ISBN: {isbn}")
        test_browse_api_epid(isbn)
    else:
        # Test multiple popular ISBNs
        print("Testing with popular books to find ePIDs...")
        print("\nWill test:")
        for isbn, title in test_isbns:
            print(f"  - {title} ({isbn})")

        success_count = 0
        for isbn, title in test_isbns:
            print(f"\n\n{'#' * 80}")
            print(f"Testing: {title}")
            print(f"ISBN: {isbn}")
            print(f"{'#' * 80}")

            try:
                result = test_browse_api_epid(isbn)
                if result:
                    success_count += 1
                    print(f"\n✓✓ SUCCESS for {title}")

                    # Stop after first success
                    print("\n" + "=" * 80)
                    print("STOPPING AFTER FIRST SUCCESS")
                    print("=" * 80)
                    break
                else:
                    print(f"\n⚠️  No ePID for {title}")
            except Exception as e:
                print(f"\n✗ Error testing {title}: {e}")
                import traceback
                traceback.print_exc()

            # Brief pause between requests
            import time
            time.sleep(1)

        print("\n" + "=" * 80)
        print(f"FINAL RESULTS: {success_count}/{len(test_isbns)} books had ePIDs")
        print("=" * 80)


if __name__ == '__main__':
    main()
