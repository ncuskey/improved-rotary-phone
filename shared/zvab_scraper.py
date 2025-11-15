"""
Zvab scraper for fetching book pricing data via Decodo API.
Zvab is the German-language version of AbeBooks (owned by Amazon).
"""

import os
from typing import Optional, Any, Dict
from datetime import datetime

from shared.decodo import DecodoClient
from shared.zvab_parser import parse_zvab_html, extract_ml_features
from shared.timing import timed


# Base URL for Zvab search
ZVAB_BASE_URL = "https://www.zvab.com/servlet/SearchResults?isbn={isbn}&sortby=17"


@timed("Zvab fetch", log=False)
def fetch_zvab_data(isbn: str, decodo_client: Optional[DecodoClient] = None) -> Dict[str, Any]:
    """Fetch and parse Zvab data for an ISBN using Decodo API."""
    isbn_clean = isbn.strip().replace("-", "")
    if not isbn_clean.isdigit() or len(isbn_clean) not in (10, 13):
        return _empty_result(f"Invalid ISBN: {isbn}")

    url = ZVAB_BASE_URL.format(isbn=isbn_clean)

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

        result = parse_zvab_html(response.body, isbn_clean)
        ml_features = extract_ml_features(result)
        result["ml_features"] = ml_features
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
            "zvab_min_price": None,
            "zvab_avg_price": None,
            "zvab_seller_count": 0,
            "zvab_condition_spread": None,
            "zvab_has_new": False,
            "zvab_has_used": False,
            "zvab_hardcover_premium": None
        },
        "total_results": 0,
        "fetched_at": datetime.now().isoformat(),
        "error": error
    }


def fetch_zvab_bulk(isbns: list[str], progress_callback=None) -> Dict[str, Dict[str, Any]]:
    """Fetch Zvab data for multiple ISBNs using Decodo API."""
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
            result = fetch_zvab_data(isbn, client)
            results[isbn] = result

            if progress_callback:
                progress_callback(i, total)
            elif i % 10 == 0:
                print(f"  Progress: {i}/{total} ISBNs fetched")

    finally:
        client.close()

    return results
