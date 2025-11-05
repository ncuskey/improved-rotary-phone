#!/usr/bin/env python3
"""
Debug script to inspect BookFinder HTML structure.
"""
import asyncio
from playwright.async_api import async_playwright

async def inspect_page(isbn: str):
    """Inspect BookFinder page structure."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        url = f"https://www.bookfinder.com/search/?isbn={isbn}"
        print(f"Loading: {url}")
        await page.goto(url, wait_until='networkidle')

        # Test wait_for_selector
        print("\nTesting wait_for_selector...")
        import time
        start = time.time()

        try:
            await page.wait_for_selector(
                '[data-csa-c-item-type="search-offer"]',
                timeout=15000,
                state='attached'
            )
            elapsed = time.time() - start
            print(f"  ✅ Selector found in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ Timeout after {elapsed:.2f}s: {e}")

        # Try various selectors
        selectors = [
            '[data-csa-c-item-type="search-offer"]',
            'div.bf-search-result',
            'div[data-csa-c-type]',
            'tr[data-offer-id]',
            'div.results-table-row',
            '.results-table tbody tr',
        ]

        print("\nTrying selectors after wait:")
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                print(f"  {selector:50} -> {len(elements)} elements")
            except Exception as e:
                print(f"  {selector:50} -> ERROR: {e}")

        # Get page HTML sample
        print("\n\nPage title:")
        title = await page.title()
        print(f"  {title}")

        # Check for "no results"
        body_text = await page.text_content('body')
        if 'Sorry, we found no matching results' in body_text:
            print("\n⚠️  NO RESULTS PAGE")
        else:
            print("\n✓ Has results")

        # Get HTML snippet around offers
        html = await page.content()

        # Look for table structures
        if 'results-table' in html:
            print("\n✓ Found 'results-table' class")
        if 'New books:' in body_text:
            print("✓ Found 'New books:' text")
        if 'Used books:' in body_text:
            print("✓ Found 'Used books:' text")

        # Save full HTML for manual inspection
        with open(f'/tmp/bookfinder_{isbn}.html', 'w') as f:
            f.write(html)
        print(f"\n📄 Full HTML saved to: /tmp/bookfinder_{isbn}.html")

        await browser.close()

if __name__ == "__main__":
    # Test with ISBN that has offers
    isbn = "9780307393876"
    asyncio.run(inspect_page(isbn))
