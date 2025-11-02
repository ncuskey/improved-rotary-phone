#!/usr/bin/env python3
"""
Test BookFinder.com scraping using Playwright (real browser).

This script tests if we can bypass AWS WAF CAPTCHA using a real browser
instead of Decodo's API approach.

Key differences from Decodo approach:
1. Real browser (Chromium) with full JavaScript execution
2. Realistic user agent and browser fingerprint
3. Can handle dynamic content and AWS WAF challenges
4. Free (no API costs)
"""

import asyncio
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright, Page, Browser

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def extract_bookfinder_data(page: Page) -> List[Dict]:
    """
    Extract book offers from BookFinder page using data attributes.

    BookFinder uses React and stores all offer data in data-csa-c-* attributes:
    - data-csa-c-affiliate: Vendor (EBAY, AMAZON, ABEBOOKS, etc.)
    - data-csa-c-usdprice: Price in USD
    - data-csa-c-usdshipping: Shipping cost in USD
    - data-csa-c-condition: NEW or USED
    - data-csa-c-seller: Seller name
    - data-csa-c-binding: SOFTCOVER or HARDCOVER

    Args:
        page: Playwright page object

    Returns:
        List of offer dictionaries
    """
    offers = []

    try:
        # Find all offer divs - they have data-csa-c-item-type="search-offer"
        offer_divs = await page.query_selector_all('[data-csa-c-item-type="search-offer"]')

        print(f"   🔍 Found {len(offer_divs)} offer elements")

        for div in offer_divs:
            try:
                # Extract all data attributes
                vendor_raw = await div.get_attribute('data-csa-c-affiliate') or 'Unknown'
                price_str = await div.get_attribute('data-csa-c-usdprice') or '0'
                shipping_str = await div.get_attribute('data-csa-c-usdshipping') or '0'
                condition_raw = await div.get_attribute('data-csa-c-condition') or ''
                seller = await div.get_attribute('data-csa-c-seller') or ''
                binding_raw = await div.get_attribute('data-csa-c-binding') or ''

                # Normalize vendor name
                vendor_map = {
                    'EBAY': 'eBay',
                    'AMAZON': 'Amazon',
                    'ABEBOOKS': 'AbeBooks',
                    'BIBLIO': 'Biblio',
                    'THRIFT_BOOKS': 'ThriftBooks',
                    'ALIBRIS': 'Alibris',
                    'BETTER_WORLD_BOOKS': 'Better World Books',
                }
                vendor = vendor_map.get(vendor_raw.upper(), vendor_raw.title())

                # Parse numeric values
                try:
                    price = float(price_str)
                    shipping = float(shipping_str)
                except ValueError:
                    continue  # Skip if price is invalid

                # Normalize condition
                condition_map = {
                    'NEW': 'New',
                    'USED': 'Used',
                }
                condition = condition_map.get(condition_raw.upper(), condition_raw.title())

                # Normalize binding
                binding_map = {
                    'SOFTCOVER': 'Softcover',
                    'HARDCOVER': 'Hardcover',
                    'MASSMARKET': 'Mass Market',
                }
                binding = binding_map.get(binding_raw.upper(), binding_raw.title())

                # Only add valid offers
                if price > 0 and vendor != 'Unknown':
                    offers.append({
                        'vendor': vendor,
                        'seller': seller,
                        'price': price,
                        'condition': condition,
                        'binding': binding,
                        'shipping': shipping,
                        'url': '',  # Would need to extract from link element
                        'location': 'United States',  # BookFinder default
                    })

            except Exception as e:
                # Skip malformed offers
                print(f"   ⚠️  Error parsing offer: {e}")
                continue

        return offers

    except Exception as e:
        print(f"  ⚠️  Error extracting data: {e}")
        return []


def normalize_offer(offer: Dict) -> Dict:
    """
    Normalize an offer dictionary from BookFinder.

    Args:
        offer: Raw offer from BookFinder

    Returns:
        Normalized offer dictionary
    """
    return {
        'vendor': offer.get('affiliate', offer.get('vendor', 'Unknown')),
        'seller': offer.get('seller', offer.get('sellerName', '')),
        'price': offer.get('priceInUsd', offer.get('price', 0)),
        'condition': offer.get('conditionText', offer.get('condition', '')),
        'binding': offer.get('bindingText', offer.get('binding', '')),
        'url': offer.get('clickoutUrl', offer.get('url', '')),
        'shipping': offer.get('shippingPriceInUsd', offer.get('shippingPrice', 0)),
        'location': offer.get('sellerLocationText', offer.get('location', '')),
    }


async def scrape_bookfinder_isbn(isbn: str, browser: Browser) -> Optional[List[Dict]]:
    """
    Scrape a single ISBN from BookFinder using Playwright.

    BookFinder loads offers via AJAX: /buyback/affiliate/{isbn}.mhtml
    We'll intercept this network request to get the JSON data directly.

    Args:
        isbn: ISBN to scrape
        browser: Playwright browser instance

    Returns:
        List of offer dictionaries, or None if scraping failed
    """
    url = f"https://www.bookfinder.com/search/?isbn={isbn}"

    print(f"\n📖 Scraping ISBN: {isbn}")
    print(f"   URL: {url}")

    try:
        # Create new page
        page = await browser.new_page()

        # Set realistic viewport
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Navigate to URL
        print(f"   🌐 Loading page...")
        response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        if not response:
            print(f"   ❌ No response from server")
            await page.close()
            return None

        print(f"   ✅ Page loaded (HTTP {response.status})")

        # Check if we hit a CAPTCHA
        page_content = await page.content()

        if 'captcha' in page_content.lower() or 'human verification' in page_content.lower():
            print(f"   ❌ CAPTCHA detected")
            # Save screenshot for debugging
            screenshot_path = f"/tmp/bookfinder_captcha_{isbn}.png"
            await page.screenshot(path=screenshot_path)
            print(f"   📸 Saved screenshot to {screenshot_path}")

            # Save HTML
            debug_path = f"/tmp/bookfinder_playwright_{isbn}.html"
            with open(debug_path, 'w') as f:
                f.write(page_content)
            print(f"   💾 Saved HTML to {debug_path}")

            await page.close()
            return None

        # Wait for offer elements to appear (React renders them dynamically)
        print(f"   ⏳ Waiting for offers to render...")
        try:
            await page.wait_for_selector('[data-csa-c-item-type="search-offer"]', timeout=10000)
            print(f"   ✅ Offers rendered")
        except Exception as e:
            print(f"   ⚠️  Timeout waiting for offers: {e}")

        # Extract offers from rendered HTML
        print(f"   🔍 Extracting offers from data attributes...")
        offers = await extract_bookfinder_data(page)

        if offers:
            print(f"   ✅ Extracted {len(offers)} offers")
            # Offers are already normalized from extract_bookfinder_data
            await page.close()
            return offers
        else:
            print(f"   ❌ No offers found")

            # Save HTML for debugging
            page_content = await page.content()
            debug_path = f"/tmp/bookfinder_playwright_{isbn}.html"
            with open(debug_path, 'w') as f:
                f.write(page_content)
            print(f"   💾 Saved HTML to {debug_path} for debugging")

            # Save screenshot
            screenshot_path = f"/tmp/bookfinder_screenshot_{isbn}.png"
            await page.screenshot(path=screenshot_path)
            print(f"   📸 Saved screenshot to {screenshot_path}")

            await page.close()
            return None

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


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


async def main():
    """Main test function."""
    print("=" * 80)
    print("BOOKFINDER.COM SCRAPING TEST (Playwright)")
    print("=" * 80)

    # Test ISBNs
    test_isbns = [
        '9780061120084',  # To Kill a Mockingbird (popular classic)
        '9780451524935',  # 1984 by George Orwell (popular)
        '9780316769174',  # The Catcher in the Rye (classic)
    ]

    print(f"\n🎯 Testing with {len(test_isbns)} ISBNs:")
    for isbn in test_isbns:
        print(f"   - {isbn}")

    # Launch browser
    print(f"\n🚀 Launching Chromium browser...")

    async with async_playwright() as p:
        # Launch browser with realistic settings
        browser = await p.chromium.launch(
            headless=True,  # Run without GUI
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # Set realistic context (looks like real Chrome)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Override navigator.webdriver flag (anti-detection)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        print(f"   ✅ Browser ready")

        # Scrape each ISBN
        results = []
        successful = 0
        failed = 0
        total_offers = 0

        for i, isbn in enumerate(test_isbns, 1):
            print(f"\n{'=' * 80}")
            print(f"Test {i}/{len(test_isbns)}")
            print(f"{'=' * 80}")

            offers = await scrape_bookfinder_isbn(isbn, context)

            if offers:
                successful += 1
                total_offers += len(offers)
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

            # Be respectful - wait between requests
            if i < len(test_isbns):
                print(f"\n   ⏸️  Waiting 3 seconds before next request...")
                await asyncio.sleep(3)

        await context.close()
        await browser.close()

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

    if successful >= 2:
        print(f"\n✅ FEASIBLE - Playwright can scrape BookFinder!")
        print(f"\n   Key Findings:")
        print(f"   • Real browser bypasses AWS WAF CAPTCHA")
        print(f"   • JavaScript rendering works correctly")
        print(f"   • Data extraction successful")
        print(f"   • 100% FREE (no API costs)")

        print(f"\n   Next Steps:")
        print(f"   1. Build full scraper for 760 catalog ISBNs")
        print(f"   2. Add 2-3 second delays between requests (respectful)")
        print(f"   3. Integrate 3 ML features (lowest_price, source_count, new_vs_used_spread)")
        print(f"   4. Consider running during off-peak hours")

        print(f"\n   💰 Cost Analysis:")
        print(f"   • Playwright: FREE")
        print(f"   • 760 ISBNs × 3 seconds = 38 minutes runtime")
        print(f"   • No CAPTCHA solving needed (browser bypasses it)")
        print(f"   • Total cost: $0")
    else:
        print(f"\n❌ NOT FEASIBLE - Too many failures")
        print(f"\n   Issues:")
        print(f"   • AWS WAF may still block headless browsers")
        print(f"   • May need stealth plugins (playwright-stealth)")
        print(f"   • Consider CAPTCHA solving service ($3/1K solves)")
        print(f"   • Alternative: Focus on direct sources")

    print(f"\n{'=' * 80}")
    print(f"Debug files saved to /tmp/bookfinder_*")
    print(f"{'=' * 80}\n")

    return 0 if successful >= 2 else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
