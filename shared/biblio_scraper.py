"""
Biblio scraper for fetching book pricing data via Decodo API.

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
from shared.biblio_parser import parse_biblio_html, extract_ml_features
from shared.timing import timed


# Base URL for Biblio search
BIBLIO_BASE_URL = "https://www.biblio.com/search.php?isbn={isbn}&sort=price_asc"


@timed("Biblio fetch", log=False)
def fetch_biblio_data(isbn: str, decodo_client: Optional[DecodoClient] = None) -> Dict[str, Any]:
    """
    Fetch and parse Biblio data for an ISBN using Decodo API.

    Args:
        isbn: The ISBN (10 or 13 digits) to look up
        decodo_client: Optional DecodoClient instance (creates new one if not provided)

    Returns:
        Dict with structure:
        {
            "offers": [...],
            "stats": {...},
            "ml_features": {...},
            "total_results": int,
            "fetched_at": str,
            "error": str
        }
    """
    # Validate ISBN
    isbn_clean = isbn.strip().replace("-", "")
    if not isbn_clean.isdigit() or len(isbn_clean) not in (10, 13):
        return _empty_result(f"Invalid ISBN: {isbn}")

    # Construct URL
    url = BIBLIO_BASE_URL.format(isbn=isbn_clean)

    # Create Decodo client if not provided
    close_client = False
    if decodo_client is None:
        username = os.getenv("DECODO_CORE_USERNAME") or os.getenv("DECODO_AUTHENTICATION")
        password = os.getenv("DECODO_CORE_PASSWORD") or os.getenv("DECODO_PASSWORD")

        if not username or not password:
            return _empty_result("Decodo credentials not found in environment")

        decodo_client = DecodoClient(
            username=username,
            password=password,
            plan="core"
        )
        close_client = True

    try:
        response = decodo_client.scrape_url(url, render_js=True)

        if response.error:
            return _empty_result(response.error)

        if not response.body:
            return _empty_result("Empty response from Decodo")

        # Parse HTML
        result = parse_biblio_html(response.body, isbn_clean)

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
            "biblio_min_price": None,
            "biblio_avg_price": None,
            "biblio_seller_count": 0,
            "biblio_condition_spread": None,
            "biblio_has_new": False,
            "biblio_has_used": False,
            "biblio_hardcover_premium": None
        },
        "total_results": 0,
        "fetched_at": datetime.now().isoformat(),
        "error": error
    }


def fetch_biblio_bulk(isbns: list[str], progress_callback=None) -> Dict[str, Dict[str, Any]]:
    """Fetch Biblio data for multiple ISBNs using Decodo API."""
    results = {}

    username = os.getenv("DECODO_CORE_USERNAME") or os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_CORE_PASSWORD") or os.getenv("DECODO_PASSWORD")

    if not username or not password:
        print("❌ Error: Decodo credentials not found in environment")
        return results

    client = DecodoClient(
        username=username,
        password=password,
        plan="core"
    )

    try:
        total = len(isbns)
        for i, isbn in enumerate(isbns, 1):
            result = fetch_biblio_data(isbn, client)
            results[isbn] = result

            if progress_callback:
                progress_callback(i, total)
            elif i % 10 == 0:
                print(f"  Progress: {i}/{total} ISBNs fetched")

    finally:
        client.close()

    return results
