#!/usr/bin/env python3
"""
Check viaLibri for price data on a given ISBN.

Usage:
    python3 scripts/check_vialibri.py 9780805059199

Uses Decodo Advanced (1 credit per ISBN) to scrape viaLibri with JavaScript rendering.
"""

import sys
import os
import base64

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.decodo import DecodoClient
from shared.vialibri_parser import parse_vialibri_html


def check_vialibri(isbn: str) -> dict:
    """
    Check viaLibri for an ISBN and return parsed results.

    Args:
        isbn: ISBN to look up

    Returns:
        Dict with 'stats', 'listings', and 'found' keys
    """
    # Get credentials from DECODO_AUTH_TOKEN (Advanced plan account)
    auth_token = os.getenv('DECODO_AUTH_TOKEN')
    if not auth_token:
        print("ERROR: DECODO_AUTH_TOKEN not found in environment")
        print("This contains the credentials for the Advanced plan account.")
        return {'found': False, 'error': 'No credentials'}

    # Decode credentials
    decoded = base64.b64decode(auth_token).decode('utf-8')
    username, password = decoded.split(':', 1)

    # Build viaLibri URL
    url = f'https://www.vialibri.net/searches?all_text={isbn}'

    try:
        # Scrape with Decodo Advanced
        client = DecodoClient(
            username=username,
            password=password,
            plan='advanced',
            rate_limit=1
        )

        response = client.scrape_url(url, render_js=True)
        client.close()

        if response.status_code != 200:
            return {
                'found': False,
                'error': f'HTTP {response.status_code}: {response.error or "Unknown error"}'
            }

        # Parse results
        data = parse_vialibri_html(response.body)
        data['found'] = data['stats']['total_listings'] > 0

        return data

    except Exception as e:
        return {'found': False, 'error': str(e)}


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/check_vialibri.py <ISBN>")
        print()
        print("Example: python3 scripts/check_vialibri.py 9780805059199")
        sys.exit(1)

    isbn = sys.argv[1].strip()

    print(f"=== VIALIBRI CHECK FOR ISBN {isbn} ===")
    print(f"Cost: 1 Decodo Advanced credit")
    print()
    print("Fetching...")

    result = check_vialibri(isbn)

    if 'error' in result:
        print(f"❌ Error: {result['error']}")
        sys.exit(1)

    if not result['found']:
        print("❌ No listings found on viaLibri")
        print()
        print("This book is either:")
        print("  - Very specialized/rare with limited availability")
        print("  - Not currently listed on viaLibri's aggregated marketplaces")
        print("  - Your manual valuation is the best available signal")
        sys.exit(0)

    # Display results
    stats = result['stats']

    print(f"✓ Found {stats['total_listings']} listings ({stats['total_price_points']} price points)")
    print()

    print("PRICE STATISTICS:")
    print(f"  Lowest:  ${stats['min_price']:.2f}")
    print(f"  Median:  ${stats['median_price']:.2f}")
    print(f"  Mean:    ${stats['mean_price']:.2f}")
    print(f"  Highest: ${stats['max_price']:.2f}")
    print()

    # Check for signed/first edition copies
    signed_count = 0
    first_ed_count = 0
    for listing in result['listings']:
        desc = listing.get('description', '').lower()
        title = listing.get('title', '').lower()
        if 'signed' in desc or 'signed' in title:
            signed_count += 1
        if 'first' in desc or 'first edition' in title:
            first_ed_count += 1

    if signed_count > 0 or first_ed_count > 0:
        print(f"Special editions: {signed_count} signed, {first_ed_count} first edition")
        print()

    # Show sample listings
    print("SAMPLE LISTINGS:")
    for i, listing in enumerate(result['listings'][:3], 1):
        print(f"{i}. {listing.get('author', 'Unknown')} - {listing.get('title', 'Unknown')}")
        print(f"   Seller: {listing.get('seller', 'Unknown')} ({listing.get('seller_location', 'Unknown')})")
        desc = listing.get('description', '')
        if desc:
            print(f"   {desc[:100]}..." if len(desc) > 100 else f"   {desc}")
        if listing.get('prices'):
            for p in listing['prices']:
                print(f"   → {p['marketplace']}: {p['price_display']}")
        print()


if __name__ == '__main__':
    main()
