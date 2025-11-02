"""
Test script to investigate BookFinder description field availability.
"""

import asyncio
from playwright.async_api import async_playwright

async def investigate_description_fields():
    """Check what description data is available in BookFinder offers."""

    # Use an ISBN we know has data
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

        # Hide automation flags (critical for bypassing AWS WAF)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = await context.new_page()

        print(f"Loading {url}...")
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print(f"Page loaded with status: {response.status}")

        # Check page content
        page_content = await page.content()
        if 'captcha' in page_content.lower() or 'challenge' in page_content.lower():
            print("⚠️  CAPTCHA or challenge detected!")

        # Wait for offers to load (they're loaded via JS)
        print("Waiting for offers to load...")
        try:
            await page.wait_for_selector('[data-csa-c-item-type="search-offer"]', timeout=15000)
        except Exception as e:
            print(f"Timeout waiting for selector: {e}")

        # Find first offer div
        offer_divs = await page.query_selector_all('[data-csa-c-item-type="search-offer"]')

        if not offer_divs:
            print(f"No offers found with selector [data-csa-c-item-type='search-offer']")
            print(f"Page title: {await page.title()}")

            # Try alternative selectors
            print("\nTrying alternative selectors...")
            alt_offers = await page.query_selector_all('.offer, .result-item, [class*="offer"]')
            print(f"Found {len(alt_offers)} elements with alternative selectors")

            await browser.close()
            return

        print(f"\nFound {len(offer_divs)} offers. Examining first 3...\n")

        for i, div in enumerate(offer_divs[:3]):
            print(f"{'='*70}")
            print(f"Offer #{i+1}")
            print(f"{'='*70}")

            # Get all data-csa-c attributes
            all_attrs = await div.evaluate("""
                (element) => {
                    const attrs = {};
                    for (const attr of element.attributes) {
                        if (attr.name.startsWith('data-csa-c-')) {
                            attrs[attr.name] = attr.value;
                        }
                    }
                    return attrs;
                }
            """)

            print("\nAll data-csa-c-* attributes:")
            for key, value in sorted(all_attrs.items()):
                print(f"  {key}: {value[:100]}..." if len(str(value)) > 100 else f"  {key}: {value}")

            # Look for description in text content
            print("\nSearching for description text...")

            # Get the full HTML of this div to inspect structure
            div_html = await div.evaluate("(el) => el.innerHTML")

            # Look for text content that might be description
            # (descriptions are usually longer paragraphs)
            text_content = await div.inner_text()

            # Split into lines and find long text blocks
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            long_lines = [line for line in lines if len(line) > 50]  # Descriptions are usually longer

            if long_lines:
                print(f"\n  Found {len(long_lines)} potential description line(s):")
                for line in long_lines[:2]:  # Show first 2 long lines
                    print(f"    Full line ({len(line)} chars): {line[:300]}")

                # Try to extract description by looking for common patterns
                for line in long_lines:
                    # Descriptions often start after "Condition:" or price
                    if "$" in line and ("condition" in line.lower() or "item" in line.lower()):
                        # Try to extract just the description part
                        # Split on price patterns
                        parts = line.split("$")
                        for part in parts:
                            if len(part) > 30 and ("item" in part.lower() or "copy" in part.lower() or "book" in part.lower()):
                                print(f"\n  Extracted description:")
                                print(f"    {part.strip()[:250]}")
                                break
                        break
            else:
                print("  No description text found in this offer")

            # Also try to find specific data attribute for description
            desc_attr = await div.get_attribute('data-csa-c-description')
            if desc_attr:
                print(f"\n  Found data-csa-c-description attribute:")
                print(f"    {desc_attr[:200]}...")

            print("\n")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(investigate_description_fields())
