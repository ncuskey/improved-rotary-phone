"""
viaLibri scraper for fetching book pricing data using Selenium.

Provides access to aggregated used book marketplace data from viaLibri with:
- Multiple seller prices from various marketplaces (AbeBooks, Biblio, etc.)
- Book metadata and descriptions
- Condition and seller information
- Market depth indicators

Uses Selenium for JavaScript rendering since viaLibri is a React-based SPA.
"""

import os
import time
from typing import Optional, Any, Dict
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from shared.vialibri_parser import parse_vialibri_html, extract_ml_features


# Base URL for viaLibri search
VIALIBRI_BASE_URL = "https://www.vialibri.net/searches?all_text={isbn}"

# Selenium configuration
HEADLESS = os.getenv('VIALIBRI_HEADLESS', 'true').lower() == 'true'
WAIT_TIME = int(os.getenv('VIALIBRI_WAIT_TIME', '5'))  # Seconds to wait for React to render


def _get_driver(headless: bool = HEADLESS) -> webdriver.Chrome:
    """
    Create and configure a Chrome WebDriver instance.

    Args:
        headless: Whether to run Chrome in headless mode (default: True)

    Returns:
        Configured Chrome WebDriver instance
    """
    chrome_options = Options()

    if headless:
        chrome_options.add_argument('--headless')

    # Standard options for stability
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # Suppress logging
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    return driver


def fetch_vialibri_data(isbn: str, timeout: int = 20) -> Dict[str, Any]:
    """
    Fetch and parse viaLibri data for an ISBN using Selenium.

    Args:
        isbn: The ISBN (10 or 13 digits) to look up
        timeout: Maximum seconds to wait for content to load (default: 20)

    Returns:
        Dict with structure:
        {
            "listings": [
                {
                    "author": str,
                    "title": str,
                    "description": str,
                    "seller": str,
                    "seller_location": str,
                    "prices": [
                        {
                            "marketplace": str,
                            "price": float,
                            "price_display": str
                        },
                        ...
                    ]
                },
                ...
            ],
            "stats": {
                "total_listings": int,
                "total_price_points": int,
                "min_price": float,
                "max_price": float,
                "median_price": float,
                "mean_price": float
            },
            "ml_features": {
                "vialibri_count": int,
                "vialibri_price_points": int,
                "vialibri_min": float,
                "vialibri_max": float,
                "vialibri_median": float,
                "vialibri_mean": float,
                "vialibri_has_data": bool
            },
            "fetched_at": str (ISO datetime)
        }

    Raises:
        Exception: If unable to fetch or parse the data
    """
    url = VIALIBRI_BASE_URL.format(isbn=isbn)
    driver = None

    try:
        # Initialize driver
        driver = _get_driver()

        # Load page
        driver.get(url)

        # Wait for React to render book listings (or timeout if no results)
        try:
            wait = WebDriverWait(driver, timeout)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "book--search-result")))
        except:
            # If no listings found within timeout, continue anyway (might be no results for ISBN)
            pass

        # Get rendered HTML
        html = driver.page_source

        # Parse the HTML
        data = parse_vialibri_html(html)

        # Add ML features
        data['ml_features'] = extract_ml_features(data)

        # Add metadata
        data['fetched_at'] = datetime.now().isoformat()
        data['isbn'] = isbn
        data['url'] = url

        return data

    except Exception as e:
        raise Exception(f"Failed to fetch viaLibri data for ISBN {isbn}: {str(e)}")

    finally:
        if driver:
            driver.quit()


def main():
    """Test the scraper with a sample ISBN."""
    import json

    # Test ISBN: White Hunters by Brian Herne
    test_isbn = "9780805059199"

    print(f"Fetching viaLibri data for ISBN {test_isbn}...")
    print(f"URL: {VIALIBRI_BASE_URL.format(isbn=test_isbn)}\n")

    try:
        data = fetch_vialibri_data(test_isbn)

        print(f"✓ Found {data['stats']['total_listings']} listings")
        print(f"✓ Found {data['stats']['total_price_points']} price points")

        if data['stats']['min_price']:
            print(f"\nPrice range: ${data['stats']['min_price']:.2f} - ${data['stats']['max_price']:.2f}")
            print(f"Median price: ${data['stats']['median_price']:.2f}")
            print(f"Mean price: ${data['stats']['mean_price']:.2f}")
        else:
            print("\nNo prices found")

        print(f"\nFirst 3 listings:")
        for i, listing in enumerate(data['listings'][:3], 1):
            print(f"\n{i}. {listing['author']} - {listing['title']}")
            print(f"   Seller: {listing['seller']} ({listing['seller_location']})")
            print(f"   Description: {listing['description'][:100]}...")
            if listing['prices']:
                prices_str = ', '.join([f"{p['marketplace']}: {p['price_display']}" for p in listing['prices']])
                print(f"   Prices: {prices_str}")

        print(f"\n\nFull JSON output:")
        print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    main()
