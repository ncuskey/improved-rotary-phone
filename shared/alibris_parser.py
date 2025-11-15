"""
Alibris HTML parser for extracting book pricing and availability data.

Parses search results from Alibris to extract:
- Multiple seller prices and conditions
- Price distribution statistics
- Seller count and market depth
- Condition-based pricing analysis
"""

import re
import statistics
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


def _extract_price(price_text: str) -> Optional[float]:
    """
    Extract numeric price from text like "US$ 12.99", "$12.99", etc.

    Args:
        price_text: Raw price text

    Returns:
        Float price or None if unable to parse
    """
    if not price_text:
        return None

    # Remove currency symbols, whitespace, and "US$"
    cleaned = re.sub(r'[^\d.]', '', price_text.strip())

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_condition(text: str) -> Optional[str]:
    """
    Extract and standardize book condition from text.

    Args:
        text: Text containing condition keywords

    Returns:
        Standardized condition string or None
    """
    if not text:
        return None

    text_lower = text.lower()

    # Alibris condition mapping
    conditions = {
        "brand new": "New",
        "new": "New",
        "like new": "Like New",
        "fine": "Fine",
        "very good": "Very Good",
        "good": "Good",
        "fair": "Fair",
        "poor": "Poor",
        "acceptable": "Acceptable",
    }

    # Match longest pattern first
    for keyword in sorted(conditions.keys(), key=len, reverse=True):
        if keyword in text_lower:
            return conditions[keyword]

    return None


def _extract_binding(text: str) -> Optional[str]:
    """
    Extract binding type (Hardcover, Softcover, etc).

    Args:
        text: Text containing binding information

    Returns:
        Binding type or None
    """
    if not text:
        return None

    text_lower = text.lower()

    bindings = {
        "hardcover": "Hardcover",
        "softcover": "Softcover",
        "paperback": "Paperback",
        "mass market": "Mass Market",
        "trade paperback": "Trade Paperback",
        "library binding": "Library Binding",
    }

    for keyword, standard in bindings.items():
        if keyword in text_lower:
            return standard

    return None


def parse_alibris_html(html: str, isbn: str) -> Dict[str, Any]:
    """
    Parse Alibris search results HTML and extract book pricing data.

    Args:
        html: Raw HTML from Alibris search results page
        isbn: ISBN being searched (for context)

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
                "by_condition": {
                    "New": {"count": int, "avg_price": float},
                    "Very Good": {"count": int, "avg_price": float},
                    ...
                },
                "by_binding": {
                    "Hardcover": {"count": int, "avg_price": float},
                    "Softcover": {"count": int, "avg_price": float},
                    ...
                }
            },
            "total_results": int,
            "error": Optional[str]
        }
    """
    soup = BeautifulSoup(html, 'html.parser')

    offers = []

    # Strategy 1: Find result items
    # Alibris typically uses classes like "result-item", "search-result", or similar
    result_items = soup.find_all(['div', 'li'], class_=re.compile(r'result|item|listing', re.I))

    # Strategy 2: If no results, try alternate structure
    if not result_items:
        # Try finding by common attributes
        result_items = soup.find_all(['div', 'article'], attrs={'data-cy': re.compile(r'listing|result')})

    # Strategy 3: Find by price elements (last resort)
    if not result_items:
        price_elements = soup.find_all(text=re.compile(r'US\$\s*\d+|\$\s*\d+'))
        # Group by parent containers
        result_items = list(set([elem.find_parent(['div', 'li']) for elem in price_elements if elem.find_parent(['div', 'li'])]))

    for item in result_items:
        try:
            # Extract price
            price_text = ""
            price_elem = item.find(string=re.compile(r'US\$\s*\d+|\$\s*\d+'))
            if not price_elem:
                price_elem = item.find(class_=re.compile(r'price', re.I))
            if price_elem:
                price_text = price_elem.get_text() if hasattr(price_elem, 'get_text') else str(price_elem)

            price = _extract_price(price_text)
            if not price or price <= 0:
                continue  # Skip items without valid prices

            # Extract condition and binding
            # Look for text like "Used - Softcover" or "New - Hardcover"
            condition_text = ""
            binding_text = ""

            condition_elem = item.find(string=re.compile(r'(New|Used|Fine|Very Good|Good|Fair).*?(Hardcover|Softcover|Paperback)', re.I))
            if condition_elem:
                condition_text = str(condition_elem)
                binding_text = condition_text
            else:
                # Try separate elements
                condition_elem = item.find(string=re.compile(r'New|Used|Fine|Very Good|Good|Fair', re.I))
                if condition_elem:
                    condition_text = str(condition_elem)

                binding_elem = item.find(string=re.compile(r'Hardcover|Softcover|Paperback', re.I))
                if binding_elem:
                    binding_text = str(binding_elem)

            condition = _extract_condition(condition_text)
            binding = _extract_binding(binding_text)

            # Extract seller name
            seller = None
            seller_elem = item.find('a', href=re.compile(r'/shop/|/seller/'))
            if seller_elem:
                seller = seller_elem.get_text(strip=True)

            # Extract location
            location = None
            location_elem = item.find(string=re.compile(r',\s*[A-Z]{2},\s*[A-Z]{3}'))  # "City, ST, USA"
            if location_elem:
                location = str(location_elem).strip()

            # Extract quantity
            quantity = 1  # Default
            qty_elem = item.find(string=re.compile(r'Quantity:\s*(\d+)'))
            if qty_elem:
                match = re.search(r'(\d+)', str(qty_elem))
                if match:
                    quantity = int(match.group(1))

            # Build offer dict
            offer = {
                "price": price,
                "condition": condition,
                "binding": binding,
                "seller": seller,
                "location": location,
                "quantity": quantity
            }

            offers.append(offer)

        except Exception as e:
            # Skip items that fail to parse
            continue

    # Calculate statistics
    if offers:
        prices = [o["price"] for o in offers]

        stats = {
            "count": len(offers),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "avg_price": round(statistics.mean(prices), 2),
            "median_price": round(statistics.median(prices), 2),
            "by_condition": {},
            "by_binding": {}
        }

        # Group by condition
        for condition in ["New", "Like New", "Fine", "Very Good", "Good", "Fair", "Acceptable"]:
            condition_offers = [o for o in offers if o.get("condition") == condition]
            if condition_offers:
                condition_prices = [o["price"] for o in condition_offers]
                stats["by_condition"][condition] = {
                    "count": len(condition_offers),
                    "avg_price": round(statistics.mean(condition_prices), 2),
                    "min_price": round(min(condition_prices), 2),
                    "max_price": round(max(condition_prices), 2)
                }

        # Group by binding
        for binding in ["Hardcover", "Softcover", "Paperback", "Trade Paperback", "Mass Market"]:
            binding_offers = [o for o in offers if o.get("binding") == binding]
            if binding_offers:
                binding_prices = [o["price"] for o in binding_offers]
                stats["by_binding"][binding] = {
                    "count": len(binding_offers),
                    "avg_price": round(statistics.mean(binding_prices), 2),
                    "min_price": round(min(binding_prices), 2),
                    "max_price": round(max(binding_prices), 2)
                }
    else:
        stats = {
            "count": 0,
            "min_price": 0.0,
            "max_price": 0.0,
            "avg_price": 0.0,
            "median_price": 0.0,
            "by_condition": {},
            "by_binding": {}
        }

    # Try to extract total results count
    total_results = len(offers)
    results_text = soup.find(string=re.compile(r'(\d+)\s*results?', re.I))
    if results_text:
        match = re.search(r'(\d+)', str(results_text))
        if match:
            total_results = int(match.group(1))

    return {
        "offers": offers,
        "stats": stats,
        "total_results": total_results,
        "error": None if offers else "No offers found"
    }


def extract_ml_features(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract ML-ready features from parsed Alibris data.

    Args:
        parsed_data: Output from parse_alibris_html()

    Returns:
        Dict with ML features:
        {
            "alibris_min_price": float,
            "alibris_avg_price": float,
            "alibris_seller_count": int,
            "alibris_condition_spread": float,  # Max - Min price
            "alibris_has_new": bool,
            "alibris_has_used": bool,
            "alibris_hardcover_premium": float  # HC avg - SC avg (if both exist)
        }
    """
    stats = parsed_data.get("stats", {})

    features = {
        "alibris_min_price": stats.get("min_price", None),
        "alibris_avg_price": stats.get("avg_price", None),
        "alibris_seller_count": stats.get("count", 0),
        "alibris_condition_spread": None,
        "alibris_has_new": False,
        "alibris_has_used": False,
        "alibris_hardcover_premium": None
    }

    # Condition spread
    if stats.get("min_price") and stats.get("max_price"):
        features["alibris_condition_spread"] = round(
            stats["max_price"] - stats["min_price"], 2
        )

    # Has new/used
    by_condition = stats.get("by_condition", {})
    features["alibris_has_new"] = "New" in by_condition
    features["alibris_has_used"] = any(
        cond in by_condition for cond in ["Very Good", "Good", "Fair", "Like New", "Fine"]
    )

    # Hardcover premium
    by_binding = stats.get("by_binding", {})
    if "Hardcover" in by_binding and ("Softcover" in by_binding or "Paperback" in by_binding):
        hc_price = by_binding["Hardcover"]["avg_price"]
        sc_price = by_binding.get("Softcover", by_binding.get("Paperback", {})).get("avg_price")
        if sc_price:
            features["alibris_hardcover_premium"] = round(hc_price - sc_price, 2)

    return features


if __name__ == "__main__":
    # Test with sample HTML
    sample_html = """
    <html>
    <body>
    <div class="result-item">
        <a href="/book/123">A Game of Thrones</a>
        <span>Used - Softcover</span>
        <span>Very Good</span>
        <span class="price">US$ 12.99</span>
        <a href="/shop/seller1">BookStore USA</a>
        <span>Seattle, WA, USA</span>
        <span>Quantity: 2 available</span>
    </div>
    <div class="result-item">
        <a href="/book/456">A Game of Thrones</a>
        <span>New - Hardcover</span>
        <span class="price">US$ 25.50</span>
        <a href="/shop/seller2">Rare Books Inc</a>
        <span>New York, NY, USA</span>
    </div>
    <div class="result-item">
        <a href="/book/789">A Game of Thrones</a>
        <span>Used - Softcover</span>
        <span>Good</span>
        <span class="price">US$ 8.75</span>
        <a href="/shop/seller3">Thrift Shop</a>
    </div>
    </body>
    </html>
    """

    print("Testing Alibris Parser")
    print("=" * 80)

    result = parse_alibris_html(sample_html, "9780553381702")

    print(f"Total offers found: {result['stats']['count']}")
    print(f"Price range: ${result['stats']['min_price']:.2f} - ${result['stats']['max_price']:.2f}")
    print(f"Average price: ${result['stats']['avg_price']:.2f}")
    print(f"Median price: ${result['stats']['median_price']:.2f}")
    print()

    print("By Condition:")
    for condition, data in result['stats']['by_condition'].items():
        print(f"  {condition}: {data['count']} offers, avg ${data['avg_price']:.2f}")
    print()

    print("By Binding:")
    for binding, data in result['stats']['by_binding'].items():
        print(f"  {binding}: {data['count']} offers, avg ${data['avg_price']:.2f}")
    print()

    print("ML Features:")
    features = extract_ml_features(result)
    for key, value in features.items():
        print(f"  {key}: {value}")
    print()

    print("Sample offers:")
    for offer in result['offers'][:3]:
        print(f"  ${offer['price']:.2f} - {offer['condition']} {offer['binding']} - {offer.get('seller', 'Unknown')}")
