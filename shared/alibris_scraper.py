"""
Alibris scraper for fetching book pricing data via Decodo API.

Provides access to used book marketplace data with:
- Multiple seller prices and conditions
- Market depth indicators
- Condition-based pricing analysis
- Binding type price differentials

Uses Decodo Core plan with "universal" target.
"""

import os
from typing import Optional, Any, Dict
from datetime import datetime

from shared.decodo import DecodoClient
from shared.alibris_parser import parse_alibris_html, extract_ml_features
from shared.timing import timed


# Base URL for Alibris search
ALIBRIS_BASE_URL = "https://www.alibris.com/booksearch?isbn={isbn}&mtype=B&hs.x=0&hs.y=0"


@timed("Alibris fetch", log=False)
def fetch_alibris_data(isbn: str, decodo_client: Optional[DecodoClient] = None) -> Dict[str, Any]:
    """
    Fetch and parse Alibris data for an ISBN using Decodo API.

    Args:
        isbn: The ISBN (10 or 13 digits) to look up
        decodo_client: Optional DecodoClient instance (creates new one if not provided)

    Returns:
        Dict with structure:
        {
            "offers": [
                {
                    "price": float,
                    "condition": str,
                    "binding": str,
                    "seller": str,
                    "location": str,
                    "quantity": int
                },
                ...
            ],
            "stats": {
                "count": int,
                "min_price": float,
                "max_price": float,
                "avg_price": float,
                "median_price": float,
                "by_condition": {...},
                "by_binding": {...}
            },
            "ml_features": {
                "alibris_min_price": float,
                "alibris_avg_price": float,
                "alibris_seller_count": int,
                ...
            },
            "total_results": int,
            "fetched_at": str,
            "error": str
        }

    Examples:
        >>> client = DecodoClient(username="...", password="...")
        >>> data = fetch_alibris_data("9780553381702", client)
        >>> print(f"Found {data['stats']['count']} offers")
        Found 23 offers
    """
    # Validate ISBN
    isbn_clean = isbn.strip().replace("-", "")
    if not isbn_clean.isdigit() or len(isbn_clean) not in (10, 13):
        return _empty_result(f"Invalid ISBN: {isbn}")

    # Construct URL
    url = ALIBRIS_BASE_URL.format(isbn=isbn_clean)

    # Create Decodo client if not provided
    close_client = False
    if decodo_client is None:
        # Use Core plan credentials (90K credits available!)
        username = os.getenv("DECODO_CORE_USERNAME") or os.getenv("DECODO_AUTHENTICATION")
        password = os.getenv("DECODO_CORE_PASSWORD") or os.getenv("DECODO_PASSWORD")

        if not username or not password:
            return _empty_result("Decodo credentials not found in environment")

        decodo_client = DecodoClient(
            username=username,
            password=password,
            plan="core"  # Use Core plan for Alibris
        )
        close_client = True

    try:
        # Fetch HTML via Decodo (using Core plan "universal" target)
        # render_js=True helps with dynamic content
        response = decodo_client.scrape_url(url, render_js=True)

        # Handle errors
        if response.error:
            return _empty_result(response.error)

        if not response.body:
            return _empty_result("Empty response from Decodo")

        # Parse HTML
        result = parse_alibris_html(response.body, isbn_clean)

        # Extract ML features
        ml_features = extract_ml_features(result)
        result["ml_features"] = ml_features

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
        "offers": [],
        "stats": {
            "count": 0,
            "min_price": 0.0,
            "max_price": 0.0,
            "avg_price": 0.0,
            "median_price": 0.0,
            "by_condition": {},
            "by_binding": {}
        },
        "ml_features": {
            "alibris_min_price": None,
            "alibris_avg_price": None,
            "alibris_seller_count": 0,
            "alibris_condition_spread": None,
            "alibris_has_new": False,
            "alibris_has_used": False,
            "alibris_hardcover_premium": None
        },
        "total_results": 0,
        "fetched_at": datetime.now().isoformat(),
        "error": error
    }


def fetch_alibris_bulk(isbns: list[str], progress_callback=None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch Alibris data for multiple ISBNs using Decodo API.

    Args:
        isbns: List of ISBNs to fetch
        progress_callback: Optional callback(current, total) for progress updates

    Returns:
        Dict mapping ISBN -> alibris data dict

    Example:
        >>> results = fetch_alibris_bulk(["9780553381702", "9780439708180"])
        >>> print(f"Fetched data for {len(results)} ISBNs")
    """
    results = {}

    # Create single Decodo client for all requests (Core plan)
    username = os.getenv("DECODO_CORE_USERNAME") or os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_CORE_PASSWORD") or os.getenv("DECODO_PASSWORD")

    if not username or not password:
        print("❌ Error: Decodo credentials not found in environment")
        return results

    client = DecodoClient(
        username=username,
        password=password,
        plan="core"  # Use Core plan (90K credits!)
    )

    try:
        total = len(isbns)
        for i, isbn in enumerate(isbns, 1):
            result = fetch_alibris_data(isbn, client)
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

    print("Testing Alibris Scraper (via Decodo Core Plan)")
    print("-" * 80)

    test_isbn = "9780553381702"  # A Game of Thrones
    print(f"Fetching data for ISBN: {test_isbn}")
    print()

    # Check for Decodo credentials
    if not os.getenv("DECODO_AUTHENTICATION") or not os.getenv("DECODO_PASSWORD"):
        print("❌ Error: DECODO_AUTHENTICATION and DECODO_PASSWORD environment variables required")
        print("Set them in your .env file or environment")
        exit(1)

    data = fetch_alibris_data(test_isbn)

    print(f"Results:")
    print(f"  Total results: {data['total_results']}")
    print(f"  Offers parsed: {data['stats']['count']}")
    print(f"  Fetched at: {data['fetched_at']}")
    if data.get("error"):
        print(f"  Error: {data['error']}")
    print()

    if data['stats']['count'] > 0:
        stats = data['stats']
        print(f"Pricing Statistics:")
        print(f"  Min price: ${stats['min_price']:.2f}")
        print(f"  Max price: ${stats['max_price']:.2f}")
        print(f"  Avg price: ${stats['avg_price']:.2f}")
        print(f"  Median price: ${stats['median_price']:.2f}")
        print()

        if stats['by_condition']:
            print(f"By Condition:")
            for condition, cond_data in stats['by_condition'].items():
                print(f"  {condition}: {cond_data['count']} offers, avg ${cond_data['avg_price']:.2f}")
            print()

        if stats['by_binding']:
            print(f"By Binding:")
            for binding, bind_data in stats['by_binding'].items():
                print(f"  {binding}: {bind_data['count']} offers, avg ${bind_data['avg_price']:.2f}")
            print()

        print(f"ML Features:")
        for key, value in data['ml_features'].items():
            print(f"  {key}: {value}")
        print()

        print(f"Sample offers (first 5):")
        for offer in data['offers'][:5]:
            condition = offer.get('condition', 'Unknown')
            binding = offer.get('binding', 'Unknown')
            seller = offer.get('seller', 'Unknown')
            print(f"  ${offer['price']:.2f} - {condition} {binding} - {seller}")
