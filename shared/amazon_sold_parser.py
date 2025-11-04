"""
Amazon sold/unavailable listing parser.

Amazon doesn't have public sold listings like eBay, but we can extract data from
"currently unavailable" or "out of stock" listings that indicate previous availability.
This provides market presence data even if not explicit sold prices.
"""

import re
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

from shared.lot_detector import is_lot


def _extract_price(html: str) -> Optional[float]:
    """
    Extract price from Amazon listing (if available).

    For unavailable items, Amazon may still show historical or list price.

    Args:
        html: Raw HTML from Amazon listing

    Returns:
        Float price or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Look for list price or strikethrough price
    price_elem = soup.find('span', class_=re.compile(r'a-price|price', re.IGNORECASE))
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    # Strategy 2: Look in schema.org markup
    meta_price = soup.find('meta', attrs={'itemprop': 'price'})
    if meta_price and meta_price.get('content'):
        try:
            return float(meta_price['content'])
        except ValueError:
            pass

    # Strategy 3: Look for price in text
    price_text = soup.find(string=re.compile(r'\$[\d,]+\.?\d*', re.IGNORECASE))
    if price_text:
        match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    return None


def _extract_condition(html: str) -> Optional[str]:
    """
    Extract condition from Amazon listing.

    Args:
        html: Raw HTML from Amazon listing

    Returns:
        Standardized condition string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    condition_map = {
        "new": "New",
        "used - like new": "Like New",
        "used - very good": "Very Good",
        "used - good": "Good",
        "used - acceptable": "Acceptable",
    }

    # Look for condition text
    condition_elem = soup.find(string=re.compile(r'[Cc]ondition\s*:', re.IGNORECASE))
    if condition_elem:
        parent = condition_elem.find_parent()
        if parent:
            text = parent.get_text(strip=True).lower()
            for keyword, standard in condition_map.items():
                if keyword in text:
                    return standard

    # Check for "New" in title or features (most Amazon listings are new)
    title = soup.find('span', id='productTitle')
    if title:
        title_text = title.get_text(strip=True).lower()
        if 'new' in title_text:
            return "New"

    return "New"  # Default assumption for Amazon


def _extract_asin(url: str) -> Optional[str]:
    """
    Extract ASIN from Amazon URL.

    Amazon URLs: https://www.amazon.com/dp/B0123456789 or /gp/product/B0123456789

    Args:
        url: Amazon listing URL

    Returns:
        ASIN or None
    """
    match = re.search(r'/(?:dp|product|gp/product)/([A-Z0-9]{10})', url, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _extract_title(html: str) -> Optional[str]:
    """
    Extract listing title from Amazon HTML.

    Args:
        html: Raw HTML from Amazon listing

    Returns:
        Title string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Product title element
    title_elem = soup.find('span', id='productTitle')
    if title_elem:
        return title_elem.get_text(strip=True)

    # Strategy 2: Meta tags
    meta_title = soup.find('meta', property='og:title')
    if meta_title and meta_title.get('content'):
        title_text = meta_title['content']
        # Remove "Amazon.com: " prefix
        title_text = re.sub(r'^Amazon\.com:\s*', '', title_text, flags=re.IGNORECASE)
        return title_text

    # Strategy 3: Page title
    page_title = soup.find('title')
    if page_title:
        title_text = page_title.get_text(strip=True)
        # Remove "Amazon.com: " prefix
        title_text = re.sub(r'^Amazon\.com:\s*', '', title_text, flags=re.IGNORECASE)
        return title_text

    return None


def _is_unavailable(html: str) -> bool:
    """
    Check if listing shows as unavailable/out of stock.

    Args:
        html: Raw HTML from Amazon listing

    Returns:
        True if unavailable
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Look for unavailability indicators
    unavailable_patterns = [
        r'currently\s+unavailable',
        r'out\s+of\s+stock',
        r'temporarily\s+out',
        r'we\s+don\'t\s+know\s+when',
        r'item\s+is\s+no\s+longer\s+available',
    ]

    for pattern in unavailable_patterns:
        if soup.find(string=re.compile(pattern, re.IGNORECASE)):
            return True

    return False


def parse_amazon_sold_listing(url: str, html: str, snippet: str = "") -> Dict[str, Any]:
    """
    Parse an Amazon unavailable/out-of-stock listing page.

    Note: Amazon doesn't expose sold listings publicly. This parser extracts
    data from unavailable listings, which provides market presence information
    but may not have explicit sold prices.

    Args:
        url: Amazon listing URL
        html: Raw HTML from Amazon listing page
        snippet: Optional search result snippet

    Returns:
        Dict with structure:
        {
            "platform": "amazon",
            "url": str,
            "listing_id": str (ASIN),
            "title": str,
            "price": float (may be None for unavailable items),
            "condition": str,
            "sold_date": None (not available on Amazon),
            "is_lot": bool,
            "is_unavailable": bool,
            "success": bool,
            "snippet": str
        }
    """
    result = {
        "platform": "amazon",
        "url": url,
        "listing_id": _extract_asin(url),
        "title": None,
        "price": None,
        "condition": "New",  # Default
        "sold_date": None,  # Amazon doesn't show sold dates
        "is_lot": False,
        "is_unavailable": False,
        "success": False,
        "snippet": snippet,
    }

    # Extract data from HTML
    result["title"] = _extract_title(html)
    result["price"] = _extract_price(html)
    result["condition"] = _extract_condition(html)
    result["is_unavailable"] = _is_unavailable(html)

    # Detect if it's a lot
    if result["title"]:
        result["is_lot"] = is_lot(result["title"])

    # Mark as successful if we got title and confirmed unavailability
    # (Price may not be available for unavailable items)
    if result["title"] and result["is_unavailable"]:
        result["success"] = True

    return result


if __name__ == "__main__":
    # Test with sample Amazon out-of-stock listing HTML
    sample_html = """
    <html>
    <head>
        <title>Amazon.com: A Game of Thrones (A Song of Ice and Fire, Book 1): George R. R. Martin: Books</title>
        <meta property="og:title" content="A Game of Thrones (A Song of Ice and Fire, Book 1)">
    </head>
    <body>
        <span id="productTitle">A Game of Thrones (A Song of Ice and Fire, Book 1)</span>
        <div class="availability">
            <span>Currently unavailable.</span>
            <br>
            We don't know when or if this item will be back in stock.
        </div>
        <span class="a-price">
            <span class="a-offscreen">$15.99</span>
        </span>
    </body>
    </html>
    """

    test_url = "https://www.amazon.com/dp/B001234567"

    print("Testing Amazon Sold/Unavailable Listing Parser")
    print("=" * 80)
    print()

    result = parse_amazon_sold_listing(test_url, sample_html)

    print(f"Parsing result:")
    print(f"  Success: {result['success']}")
    print(f"  Listing ID (ASIN): {result['listing_id']}")
    print(f"  Title: {result['title']}")
    print(f"  Price: ${result['price']:.2f}" if result['price'] else "  Price: None")
    print(f"  Condition: {result['condition']}")
    print(f"  Is Unavailable: {result['is_unavailable']}")
    print(f"  Is Lot: {result['is_lot']}")
    print()
