#!/usr/bin/env python3
"""
Test BookFinder.com scraping using Decodo Core.

This script tests our ability to scrape BookFinder with Decodo Core by:
1. Scraping 5-10 sample ISBNs
2. Extracting offer data from Next.js embedded JSON
3. Validating data quality
4. Reporting results and feasibility
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient, DecodoAPIError


def parse_bookfinder_json(html: str) -> List[Dict]:
    """
    Extract book offers from Next.js JSON embedded in script tags.

    BookFinder uses React/Next.js with data embedded as JSON in <script> tags.
    We need to extract the `allOffers` array from the script content.

    Args:
        html: Raw HTML response from BookFinder

    Returns:
        List of offer dictionaries
    """
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')

    # Look for script tags containing the data
    for script in scripts:
        if not script.string:
            continue

        # Check if this script contains offer data
        if '"allOffers"' in script.string or '"searchResults"' in script.string:
            # Try multiple patterns to extract the JSON

            # Pattern 1: Direct allOffers array
            match = re.search(r'"allOffers"\s*:\s*(\[.*?\])', script.string, re.DOTALL)
            if match:
                try:
                    offers = json.loads(match.group(1))
                    return offers
                except json.JSONDecodeError as e:
                    print(f"  ⚠️  JSON decode error (pattern 1): {e}")
                    continue

            # Pattern 2: searchResults object containing allOffers
            match = re.search(r'"searchResults"\s*:\s*\{[^}]*"allOffers"\s*:\s*(\[.*?\])',
                            script.string, re.DOTALL)
            if match:
                try:
                    offers = json.loads(match.group(1))
                    return offers
                except json.JSONDecodeError as e:
                    print(f"  ⚠️  JSON decode error (pattern 2): {e}")
                    continue

    return []


def parse_bookfinder_html_fallback(html: str) -> List[Dict]:
    """
    Fallback: Try to parse rendered HTML if JSON extraction fails.

    This is less reliable as CSS classes can change, but provides a backup.

    Args:
        html: Raw HTML response

    Returns:
        List of offer dictionaries (best effort)
    """
    soup = BeautifulSoup(html, 'html.parser')
    offers = []

    # Look for common patterns in BookFinder's rendered HTML
    # These are speculative and may not work - adjust based on actual HTML

    # Try to find offer containers
    offer_divs = soup.find_all('div', class_=lambda c: c and 'offer' in c.lower())

    if not offer_divs:
        # Try alternative selectors
        offer_divs = soup.find_all('div', attrs={'data-testid': lambda t: t and 'offer' in t.lower()})

    for div in offer_divs:
        offer = {}

        # Extract price (usually bold, blue text)
        price_elem = div.find(class_=lambda c: c and ('price' in c.lower() or 'bold' in c.lower()))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Extract numeric value
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
            if price_match:
                offer['price'] = float(price_match.group(1).replace(',', ''))

        # Extract other fields (speculative)
        # Note: This is just a template - adjust based on actual HTML structure

        if offer:
            offers.append(offer)

    return offers


def extract_offer_data(offer: Dict) -> Dict:
    """
    Extract and normalize relevant fields from a BookFinder offer.

    Args:
        offer: Raw offer dictionary from JSON

    Returns:
        Normalized offer dictionary
    """
    return {
        'vendor': offer.get('affiliate', 'Unknown'),
        'seller': offer.get('seller', ''),
        'price': offer.get('priceInUsd', offer.get('price', 0)),
        'condition': offer.get('conditionText', offer.get('condition', '')),
        'binding': offer.get('bindingText', offer.get('binding', '')),
        'url': offer.get('clickoutUrl', ''),
        'shipping': offer.get('shippingPriceInUsd', offer.get('shippingPrice', 0)),
        'location': offer.get('sellerLocationText', ''),
    }


def scrape_bookfinder_isbn(isbn: str, decodo: DecodoClient) -> Optional[List[Dict]]:
    """
    Scrape a single ISBN from BookFinder.

    Args:
        isbn: ISBN to scrape
        decodo: Decodo client instance

    Returns:
        List of offer dictionaries, or None if scraping failed
    """
    url = f"https://www.bookfinder.com/search/?isbn={isbn}"

    print(f"\n📖 Scraping ISBN: {isbn}")
    print(f"   URL: {url}")

    try:
        response = decodo.scrape_url(url, render_js=True)

        if response.status_code != 200:
            print(f"   ❌ HTTP {response.status_code}: {response.error}")
            return None

        if not response.body:
            print(f"   ❌ Empty response body")
            return None

        print(f"   ✅ Fetched HTML ({len(response.body):,} bytes)")

        # Try JSON extraction first (primary method)
        offers = parse_bookfinder_json(response.body)

        if offers:
            print(f"   ✅ Extracted {len(offers)} offers from JSON")
        else:
            print(f"   ⚠️  JSON extraction failed, trying HTML fallback...")
            offers = parse_bookfinder_html_fallback(response.body)

            if offers:
                print(f"   ⚠️  Extracted {len(offers)} offers from HTML (less reliable)")
            else:
                print(f"   ❌ No offers found")
                # Save HTML for debugging
                debug_path = f"/tmp/bookfinder_debug_{isbn}.html"
                with open(debug_path, 'w') as f:
                    f.write(response.body)
                print(f"   💾 Saved HTML to {debug_path} for debugging")
                return None

        # Normalize offer data
        normalized_offers = [extract_offer_data(offer) for offer in offers]

        return normalized_offers

    except DecodoAPIError as e:
        print(f"   ❌ Decodo API error: {e}")
        return None
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return None


def save_test_results(isbn: str, offers: List[Dict], db_path: str):
    """
    Save test results to SQLite database.

    Args:
        isbn: ISBN that was scraped
        offers: List of offer dictionaries
        db_path: Path to database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookfinder_test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            vendor TEXT,
            seller TEXT,
            price REAL,
            condition TEXT,
            binding TEXT,
            shipping REAL,
            url TEXT,
            location TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert offers
    for offer in offers:
        cursor.execute("""
            INSERT INTO bookfinder_test_results
            (isbn, vendor, seller, price, condition, binding, shipping, url, location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            isbn,
            offer.get('vendor', ''),
            offer.get('seller', ''),
            offer.get('price', 0),
            offer.get('condition', ''),
            offer.get('binding', ''),
            offer.get('shipping', 0),
            offer.get('url', ''),
            offer.get('location', '')
        ))

    conn.commit()
    conn.close()


def print_offer_summary(offers: List[Dict]):
    """Print a summary of offers for inspection."""
    if not offers:
        return

    print(f"\n   📊 Offer Summary:")
    print(f"   {'Vendor':<15} {'Price':>8} {'Condition':<20} {'Binding':<12}")
    print(f"   {'-' * 60}")

    for offer in offers[:10]:  # Show first 10
        vendor = offer.get('vendor', 'Unknown')[:15]
        price = f"${offer.get('price', 0):.2f}"
        condition = offer.get('condition', '')[:20]
        binding = offer.get('binding', '')[:12]
        print(f"   {vendor:<15} {price:>8} {condition:<20} {binding:<12}")

    if len(offers) > 10:
        print(f"   ... and {len(offers) - 10} more offers")

    # Statistics
    prices = [o.get('price', 0) for o in offers if o.get('price', 0) > 0]
    if prices:
        print(f"\n   💰 Price Range: ${min(prices):.2f} - ${max(prices):.2f}")
        print(f"   💰 Average Price: ${sum(prices) / len(prices):.2f}")


def main():
    """Main test function."""
    print("=" * 80)
    print("BOOKFINDER.COM SCRAPING TEST (Decodo Core)")
    print("=" * 80)

    # Get Decodo Core credentials from environment
    username = os.environ.get('DECODO_CORE_AUTHENTICATION')
    password = os.environ.get('DECODO_CORE_PASSWORD')

    if not username or not password:
        print("\n❌ Error: DECODO_CORE_AUTHENTICATION and DECODO_CORE_PASSWORD environment variables not set")
        print("   Please set them in your .env file and try again.")
        return 1

    # Initialize Decodo client
    print(f"\n🔧 Initializing Decodo client (Core plan)...")
    decodo = DecodoClient(
        username=username,
        password=password,
        plan='core'
    )

    # Test ISBNs (diverse sample from catalog)
    test_isbns = [
        '9780061120084',  # To Kill a Mockingbird (popular classic)
        '9780451524935',  # 1984 by George Orwell (popular)
        '9780316769174',  # The Catcher in the Rye (classic)
        '9780062315007',  # The Alchemist (bestseller)
        '9780143127550',  # Fahrenheit 451 (science fiction)
    ]

    # Load a few ISBNs from catalog for real testing
    try:
        catalog_db = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        if catalog_db.exists():
            conn = sqlite3.connect(catalog_db)
            cursor = conn.cursor()
            cursor.execute("SELECT isbn FROM books WHERE isbn IS NOT NULL LIMIT 3")
            catalog_isbns = [row[0] for row in cursor.fetchall()]
            conn.close()

            if catalog_isbns:
                print(f"\n📚 Found {len(catalog_isbns)} ISBNs from catalog")
                test_isbns = catalog_isbns + test_isbns
    except Exception as e:
        print(f"\n⚠️  Could not load catalog ISBNs: {e}")

    # Limit to first 5 for testing
    test_isbns = test_isbns[:5]

    print(f"\n🎯 Testing with {len(test_isbns)} ISBNs:")
    for isbn in test_isbns:
        print(f"   - {isbn}")

    # Create test database
    db_path = '/tmp/bookfinder_test.db'
    print(f"\n💾 Results will be saved to: {db_path}")

    # Scrape each ISBN
    results = []
    successful = 0
    failed = 0
    total_offers = 0

    for i, isbn in enumerate(test_isbns, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}/{len(test_isbns)}")
        print(f"{'=' * 80}")

        offers = scrape_bookfinder_isbn(isbn, decodo)

        if offers:
            successful += 1
            total_offers += len(offers)
            save_test_results(isbn, offers, db_path)
            print_offer_summary(offers)
            results.append({
                'isbn': isbn,
                'offers': offers,
                'success': True
            })
        else:
            failed += 1
            results.append({
                'isbn': isbn,
                'offers': [],
                'success': False
            })

    # Final summary
    print(f"\n{'=' * 80}")
    print(f"TEST RESULTS SUMMARY")
    print(f"{'=' * 80}")

    print(f"\n📊 Overall Statistics:")
    print(f"   Total ISBNs tested: {len(test_isbns)}")
    print(f"   ✅ Successful: {successful} ({successful / len(test_isbns) * 100:.1f}%)")
    print(f"   ❌ Failed: {failed} ({failed / len(test_isbns) * 100:.1f}%)")
    print(f"   📦 Total offers extracted: {total_offers}")

    if successful > 0:
        print(f"   📈 Average offers per ISBN: {total_offers / successful:.1f}")

    # Feasibility assessment
    print(f"\n{'=' * 80}")
    print(f"FEASIBILITY ASSESSMENT")
    print(f"{'=' * 80}")

    if successful >= 3:
        print(f"\n✅ FEASIBLE - BookFinder scraping works with Decodo Core!")
        print(f"\n   Next Steps:")
        print(f"   1. Review HTML debug files in /tmp/ if any extraction failed")
        print(f"   2. Adjust JSON extraction patterns if needed")
        print(f"   3. Build full scraper for 760 catalog ISBNs")
        print(f"   4. Integrate 3 ML features (lowest_price, source_count, new_vs_used_spread)")

        # Estimated cost
        print(f"\n   💰 Cost Estimate:")
        print(f"   - Catalog ISBNs: 760")
        print(f"   - Credits per ISBN: ~1")
        print(f"   - Total credits: ~760 (0.8% of 90K budget)")
        print(f"   - Runtime: ~38 minutes (760 × 3 seconds)")
    else:
        print(f"\n❌ NOT FEASIBLE - Too many failures")
        print(f"\n   Issues to investigate:")
        print(f"   1. Check HTML debug files in /tmp/")
        print(f"   2. BookFinder may have changed data structure")
        print(f"   3. Decodo Core may not render JavaScript properly")
        print(f"   4. Consider alternative sources (Alibris, DealOz)")

    print(f"\n{'=' * 80}")
    print(f"Database: {db_path}")
    print(f"Query results with: sqlite3 {db_path} 'SELECT * FROM bookfinder_test_results;'")
    print(f"{'=' * 80}\n")

    return 0 if successful >= 3 else 1


if __name__ == '__main__':
    sys.exit(main())
