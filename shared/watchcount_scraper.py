"""
WatchCount.com scraper for fetching eBay sold item data via Decodo API.

Provides access to historical eBay sold listings data when eBay's
Marketplace Insights API is unavailable.

Features:
- Uses Decodo's Web target to bypass bot protection
- JavaScript rendering support
- Automatic lot detection (keeps lot data for bulk valuation analysis)
- Rate limiting via Decodo client
"""

import os
from typing import Optional, Any, Dict
from datetime import datetime

from shared.decodo import DecodoClient
from shared.watchcount_parser import parse_watchcount_html
from shared.timing import timed


# Base URL for WatchCount sold listings
WATCHCOUNT_BASE_URL = "https://www.watchcount.com/sold/{isbn}/books-magazines_267/all?site=EBAY_US"


@timed("WatchCount fetch", log=False)
def fetch_watchcount_data(isbn: str, decodo_client: Optional[DecodoClient] = None) -> Dict[str, Any]:
    """
    Fetch and parse WatchCount sold data for an ISBN using Decodo API.

    Args:
        isbn: The ISBN (10 or 13 digits) to look up
        decodo_client: Optional DecodoClient instance (creates new one if not provided)

    Returns:
        Dict with structure:
        {
            "individual_sales": {
                "count": int,           # Number of individual book sales
                "avg_price": float,     # Average price
                "median_price": float,  # Median price
                "min_price": float,     # Min price
                "max_price": float,     # Max price
                "items": [...]          # Individual sale details
            },
            "lot_sales": {
                "count": int,           # Number of lot listings
                "avg_price": float,     # Average lot price
                "avg_price_per_book": float,  # Estimated per-book price
                "items": [...]          # Lot details with lot_size
            },
            "total_items": int,         # Total items found
            "fetched_at": str,          # ISO timestamp
            "error": str,               # Error message if failed
        }

    Examples:
        >>> client = DecodoClient(username="...", password="...")
        >>> data = fetch_watchcount_data("9780553381702", client)
        >>> print(f"Found {data['individual_sales']['count']} individual sales")
        Found 15 individual sales
    """
    # Validate ISBN
    isbn_clean = isbn.strip().replace("-", "")
    if not isbn_clean.isdigit() or len(isbn_clean) not in (10, 13):
        return _empty_result(f"Invalid ISBN: {isbn}")

    # Construct URL
    url = WATCHCOUNT_BASE_URL.format(isbn=isbn_clean)

    # Create Decodo client if not provided
    close_client = False
    if decodo_client is None:
        username = os.getenv("DECODO_AUTHENTICATION")
        password = os.getenv("DECODO_PASSWORD")

        if not username or not password:
            return _empty_result("Decodo credentials not found in environment")

        decodo_client = DecodoClient(username=username, password=password)
        close_client = True

    try:
        # Fetch HTML via Decodo (bypasses bot protection)
        # Note: render_js=True may help with CAPTCHA challenges
        response = decodo_client.scrape_url(url, render_js=True)

        # Handle errors
        if response.error:
            return _empty_result(response.error)

        if not response.body:
            return _empty_result("Empty response from Decodo")

        # Parse HTML (now includes lot data separately)
        result = parse_watchcount_html(response.body, isbn_clean)

        # Add timestamp
        result["fetched_at"] = datetime.now().isoformat()

        return result

    except Exception as e:
        return _empty_result(f"Scrape failed: {str(e)}")

    finally:
        if close_client:
            decodo_client.close()


def _empty_result(error: str = None) -> Dict[str, Any]:
    """Return empty result structure with optional error."""
    return {
        "individual_sales": {
            "count": 0,
            "avg_price": 0.0,
            "median_price": 0.0,
            "min_price": 0.0,
            "max_price": 0.0,
            "items": []
        },
        "lot_sales": {
            "count": 0,
            "avg_price": 0.0,
            "avg_price_per_book": 0.0,
            "items": []
        },
        "total_items": 0,
        "fetched_at": datetime.now().isoformat(),
        "error": error
    }


def fetch_watchcount_bulk(isbns: list[str], progress_callback=None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch WatchCount data for multiple ISBNs using Decodo API.

    Args:
        isbns: List of ISBNs to fetch
        progress_callback: Optional callback(current, total) for progress updates

    Returns:
        Dict mapping ISBN -> watchcount data dict

    Example:
        >>> results = fetch_watchcount_bulk(["9780553381702", "9780439708180"])
        >>> print(f"Fetched data for {len(results)} ISBNs")
    """
    results = {}

    # Create single Decodo client for all requests
    username = os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_PASSWORD")

    if not username or not password:
        print("❌ Error: Decodo credentials not found in environment")
        return results

    client = DecodoClient(username=username, password=password)

    try:
        total = len(isbns)
        for i, isbn in enumerate(isbns, 1):
            result = fetch_watchcount_data(isbn, client)
            results[isbn] = result

            if progress_callback:
                progress_callback(i, total)
            elif i % 10 == 0:
                print(f"  Progress: {i}/{total} ISBNs fetched")

    finally:
        client.close()

    return results


if __name__ == "__main__":
    # Test with a known ISBN
    import os
    from pathlib import Path

    # Load .env file if present
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

    print("Testing WatchCount Scraper (via Decodo)")
    print("-" * 80)

    test_isbn = "9780553381702"  # A Game of Thrones
    print(f"Fetching data for ISBN: {test_isbn}")
    print()

    # Check for Decodo credentials
    if not os.getenv("DECODO_AUTHENTICATION") or not os.getenv("DECODO_PASSWORD"):
        print("❌ Error: DECODO_AUTHENTICATION and DECODO_PASSWORD environment variables required")
        print("Set them in your .env file or environment")
        exit(1)

    data = fetch_watchcount_data(test_isbn)

    print(f"Results:")
    print(f"  Total items: {data['total_items']}")
    print(f"  Individual sales: {data['individual_sales']['count']}")
    print(f"  Lot sales: {data['lot_sales']['count']}")
    print(f"  Fetched at: {data['fetched_at']}")
    if data.get("error"):
        print(f"  Error: {data['error']}")
    print()

    if data['individual_sales']['count'] > 0:
        ind = data['individual_sales']
        print(f"Individual Sales Stats:")
        print(f"  Avg price: ${ind['avg_price']:.2f}")
        print(f"  Median price: ${ind['median_price']:.2f}")
        print(f"  Price range: ${ind['min_price']:.2f} - ${ind['max_price']:.2f}")
        print()

        print(f"Sample individual items (first 3):")
        for item in ind['items'][:3]:
            print(f"  - {item.get('title', 'N/A')[:60]}")
            print(f"    Price: ${item.get('price', 0):.2f} | Condition: {item.get('condition', 'N/A')}")
        print()

    if data['lot_sales']['count'] > 0:
        lots = data['lot_sales']
        print(f"Lot Sales Stats:")
        print(f"  Avg lot price: ${lots['avg_price']:.2f}")
        print(f"  Avg price per book: ${lots['avg_price_per_book']:.2f}")
        print()

        print(f"Sample lot items (first 3):")
        for item in lots['items'][:3]:
            print(f"  - {item.get('title', 'N/A')[:60]}")
            print(f"    Price: ${item.get('price', 0):.2f} | Size: {item.get('lot_size', '?')}")
