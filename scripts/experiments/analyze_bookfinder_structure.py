"""
Analyze BookFinder HTML structure to find all available data fields.
"""

import asyncio
from playwright.async_api import async_playwright

async def analyze_offer_structure():
    """Thoroughly analyze the structure of BookFinder offers."""

    isbn = "9780061231421"
    url = f"https://www.bookfinder.com/search/?isbn={isbn}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Hide automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = await context.new_page()

        print(f"Loading {url}...\n")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(7000)  # Give it time to load

        offer_divs = await page.query_selector_all('[data-csa-c-item-type="search-offer"]')
        print(f"Found {len(offer_divs)} offers\n")

        # Analyze first offer in detail
        div = offer_divs[0]

        print("="*70)
        print("COMPREHENSIVE DATA EXTRACTION FROM FIRST OFFER")
        print("="*70)

        # Get ALL data-csa-c-* attributes
        all_attrs = await div.evaluate("""
            (element) => {
                const attrs = {};
                for (const attr of element.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            }
        """)

        print("\n1. ALL ATTRIBUTES (data-csa-c-* and others):")
        print("-" * 70)
        for key in sorted(all_attrs.keys()):
            value = all_attrs[key]
            if len(str(value)) > 80:
                print(f"  {key}: {value[:77]}...")
            else:
                print(f"  {key}: {value}")

        # Get the inner HTML to see structure
        print("\n2. INNER HTML STRUCTURE:")
        print("-" * 70)
        html = await div.evaluate("(el) => el.innerHTML")
        # Show first 1000 chars
        print(html[:1000])
        print("\n... (truncated)\n")

        # Try to find description via specific selectors
        print("\n3. LOOKING FOR DESCRIPTION ELEMENT:")
        print("-" * 70)

        # Common selectors for descriptions
        desc_selectors = [
            '.description',
            '.item-description',
            '[class*="description"]',
            '[class*="comment"]',
            '[class*="notes"]',
            '.condition-description',
            '[data-csa-c-description]',
        ]

        for selector in desc_selectors:
            elem = await div.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                print(f"  Found via '{selector}': {text[:200]}")

        # Also try getting all <p> tags, <span> tags within the div
        print("\n4. ALL TEXT ELEMENTS:")
        print("-" * 70)

        paragraphs = await div.query_selector_all('p, span, div')
        for i, p in enumerate(paragraphs[:10]):  # First 10 elements
            text = await p.inner_text()
            text = text.strip()
            if text and len(text) > 20:  # Only show substantial text
                class_name = await p.get_attribute('class') or ''
                tag = await p.evaluate("(el) => el.tagName")
                print(f"  [{i}] <{tag.lower()} class='{class_name[:30]}'> {text[:150]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(analyze_offer_structure())
