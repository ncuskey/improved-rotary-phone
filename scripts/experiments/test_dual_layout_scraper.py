#!/usr/bin/env python3
"""
Test dual-layout scraper that handles both:
1. React version (data-csa-c-* attributes)
2. Traditional HTML table version (fallback)
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))


async def extract_react_offers(page):
    """Extract offers from React version (data-csa-c-* attributes)."""
    offers = []

    try:
        offer_divs = await page.query_selector_all('[data-csa-c-item-type="search-offer"]')
        print(f"  React layout: Found {len(offer_divs)} offer elements")

        for div in offer_divs:
            vendor = await div.get_attribute('data-csa-c-affiliate') or 'Unknown'
            price_str = await div.get_attribute('data-csa-c-usdprice') or '0'

            try:
                price = float(price_str)
                if price > 0 and vendor != 'Unknown':
                    offers.append({
                        'vendor': vendor,
                        'price': price,
                        'layout': 'react'
                    })
            except:
                continue

        return offers
    except Exception as e:
        print(f"  React extraction error: {e}")
        return []


async def extract_table_offers(page):
    """Extract offers from traditional HTML table layout."""
    offers = []

    try:
        # Look for table rows - BookFinder uses tables with class names
        # Try multiple selectors
        rows = []

        # Try finding rows in tables
        tables = await page.query_selector_all('table')
        print(f"  Table layout: Found {len(tables)} tables")

        for table in tables:
            table_rows = await table.query_selector_all('tr')
            rows.extend(table_rows)

        print(f"  Table layout: Found {len(rows)} rows total")

        for row in rows:
            try:
                # Look for price cells
                price_cells = await row.query_selector_all('td')

                for cell in price_cells:
                    text = await cell.inner_text()

                    # Look for prices starting with $
                    if '$' in text and len(text) < 50:
                        # Try to extract price
                        import re
                        price_match = re.search(r'\$(\d+\.?\d*)', text)
                        if price_match:
                            price = float(price_match.group(1))
                            if price > 0:
                                offers.append({
                                    'vendor': 'Unknown',
                                    'price': price,
                                    'layout': 'table'
                                })
            except:
                continue

        return offers
    except Exception as e:
        print(f"  Table extraction error: {e}")
        return []


async def test_isbn(isbn: str):
    """Test scraping a single ISBN with both methods."""
    url = f"https://www.bookfinder.com/search/?isbn={isbn}"

    print(f"\nTesting ISBN: {isbn}")
    print(f"URL: {url}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = await context.new_page()

        print("  Loading page...")
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        # Wait for network idle
        try:
            await page.wait_for_load_state('networkidle', timeout=20000)
            print("  ✓ Network idle")
        except:
            print("  ⚠ Network idle timeout, continuing...")
            await asyncio.sleep(5)

        # Try React layout first
        print("\n  Trying React layout extraction...")
        react_offers = await extract_react_offers(page)

        # If React fails, try table layout
        print("\n  Trying table layout extraction...")
        table_offers = await extract_table_offers(page)

        # Save screenshot for inspection
        screenshot_path = f"/tmp/bookfinder_dual_test_{isbn}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n  Screenshot saved: {screenshot_path}")

        # Save HTML
        html = await page.content()
        html_path = f"/tmp/bookfinder_dual_test_{isbn}.html"
        with open(html_path, 'w') as f:
            f.write(html)
        print(f"  HTML saved: {html_path}")

        await browser.close()

        # Report results
        print("\n  Results:")
        print(f"    React offers: {len(react_offers)}")
        if react_offers:
            print(f"      Sample: ${react_offers[0]['price']:.2f} from {react_offers[0]['vendor']}")

        print(f"    Table offers: {len(table_offers)}")
        if table_offers:
            print(f"      Sample: ${table_offers[0]['price']:.2f}")

        return react_offers, table_offers


async def main():
    """Test with a few ISBNs."""
    test_isbns = [
        '9780307263162',  # From failed test
        '9780001006898',  # Recently successful
    ]

    for isbn in test_isbns:
        react_offers, table_offers = await test_isbn(isbn)

        print("\n" + "="*70)
        if react_offers:
            print(f"✓ SUCCESS: React layout works for {isbn}")
        elif table_offers:
            print(f"⚠ FALLBACK: Table layout works for {isbn}")
        else:
            print(f"✗ FAILED: Neither layout works for {isbn}")
        print("="*70 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
