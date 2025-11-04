"""
eBay sold listing parser for individual completed/sold item pages.

Parses eBay sold listing HTML to extract price, condition, sold date, and other
key attributes. Works with URLs from eBay's completed listings search.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from shared.lot_detector import is_lot


def _extract_price(html: str) -> Optional[float]:
    """
    Extract sold price from eBay listing HTML.

    eBay shows sold prices in various places:
    - "Sold for $X.XX" text
    - Price display element with sold indicator
    - Item specifics section

    Args:
        html: Raw HTML from eBay sold listing

    Returns:
        Float price or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Look for "Sold for" text
    sold_text = soup.find(string=re.compile(r'[Ss]old\s+for\s*\$?[\d,]+\.?\d*', re.IGNORECASE))
    if sold_text:
        match = re.search(r'\$?([\d,]+\.?\d*)', sold_text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    # Strategy 2: Look for price with "sold" nearby
    price_elem = soup.find('span', class_=re.compile(r'price|notranslate', re.IGNORECASE))
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    # Strategy 3: Look for converted price (international listings)
    converted_elem = soup.find(string=re.compile(r'US\s*\$[\d,]+\.?\d*', re.IGNORECASE))
    if converted_elem:
        match = re.search(r'US\s*\$\s*([\d,]+\.?\d*)', converted_elem, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    return None


def _extract_condition(html: str) -> Optional[str]:
    """
    Extract condition from eBay listing.

    Args:
        html: Raw HTML from eBay listing

    Returns:
        Standardized condition string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # eBay condition mapping
    condition_map = {
        "brand new": "New",
        "new": "New",
        "like new": "Like New",
        "very good": "Very Good",
        "good": "Good",
        "acceptable": "Acceptable",
        "poor": "Poor",
    }

    # Look in item specifics section
    condition_elem = soup.find('div', class_=re.compile(r'condition', re.IGNORECASE))
    if condition_elem:
        text = condition_elem.get_text(strip=True).lower()
        for keyword, standard in condition_map.items():
            if keyword in text:
                return standard

    # Look for condition label
    condition_label = soup.find(string=re.compile(r'[Cc]ondition\s*:', re.IGNORECASE))
    if condition_label:
        parent = condition_label.find_parent()
        if parent:
            text = parent.get_text(strip=True).lower()
            for keyword, standard in condition_map.items():
                if keyword in text:
                    return standard

    return None


def _extract_sold_date(html: str) -> Optional[str]:
    """
    Extract sold date from eBay listing.

    eBay shows: "Sold on Jan 15, 2025" or similar

    Args:
        html: Raw HTML from eBay listing

    Returns:
        Date string in ISO format (YYYY-MM-DD) or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Look for "Sold" date text
    sold_date_text = soup.find(string=re.compile(r'[Ss]old\s+(?:on\s+)?[A-Za-z]{3}\s+\d{1,2},?\s+\d{4}', re.IGNORECASE))
    if sold_date_text:
        # Parse date like "Jan 15, 2025"
        match = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', sold_date_text, re.IGNORECASE)
        if match:
            month_str, day_str, year_str = match.groups()
            try:
                date_obj = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Look for relative time "Sold X days ago"
    relative_text = soup.find(string=re.compile(r'[Ss]old\s+(\d+)\s+(day|hour|week)s?\s+ago', re.IGNORECASE))
    if relative_text:
        match = re.search(r'(\d+)\s+(day|hour|week)s?\s+ago', relative_text, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()

            if unit == 'hour':
                delta = timedelta(hours=amount)
            elif unit == 'day':
                delta = timedelta(days=amount)
            elif unit == 'week':
                delta = timedelta(weeks=amount)
            else:
                return None

            sold_date = datetime.now() - delta
            return sold_date.strftime("%Y-%m-%d")

    return None


def _extract_listing_id(url: str) -> Optional[str]:
    """
    Extract eBay item ID from URL.

    eBay URLs: https://www.ebay.com/itm/123456789012

    Args:
        url: eBay listing URL

    Returns:
        Item ID or None
    """
    match = re.search(r'/itm/(\d+)', url)
    if match:
        return match.group(1)

    # Alternative format: ?item=123456
    match = re.search(r'[?&]item=(\d+)', url)
    if match:
        return match.group(1)

    return None


def _extract_title(html: str) -> Optional[str]:
    """
    Extract listing title from eBay HTML.

    Args:
        html: Raw HTML from eBay listing

    Returns:
        Title string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Look for h1 title
    title_elem = soup.find('h1', class_=re.compile(r'title|product', re.IGNORECASE))
    if title_elem:
        return title_elem.get_text(strip=True)

    # Strategy 2: Look in meta tags
    meta_title = soup.find('meta', property='og:title')
    if meta_title and meta_title.get('content'):
        return meta_title['content']

    # Strategy 3: Page title
    page_title = soup.find('title')
    if page_title:
        title_text = page_title.get_text(strip=True)
        # Remove "| eBay" suffix
        title_text = re.sub(r'\s*\|\s*eBay\s*$', '', title_text, flags=re.IGNORECASE)
        return title_text

    return None


def parse_ebay_sold_listing(url: str, html: str, snippet: str = "") -> Dict[str, Any]:
    """
    Parse an eBay sold listing page.

    Args:
        url: eBay listing URL
        html: Raw HTML from eBay sold listing page
        snippet: Optional search result snippet (fallback for data extraction)

    Returns:
        Dict with structure:
        {
            "platform": "ebay",
            "url": str,
            "listing_id": str,
            "title": str,
            "price": float,
            "condition": str,
            "sold_date": str (ISO format),
            "is_lot": bool,
            "success": bool,  # Whether parsing succeeded
            "raw_snippet": str
        }
    """
    result = {
        "platform": "ebay",
        "url": url,
        "listing_id": _extract_listing_id(url),
        "title": None,
        "price": None,
        "condition": None,
        "sold_date": None,
        "is_lot": False,
        "success": False,
        "snippet": snippet,
    }

    # Extract data from HTML
    result["title"] = _extract_title(html)
    result["price"] = _extract_price(html)
    result["condition"] = _extract_condition(html)
    result["sold_date"] = _extract_sold_date(html)

    # Detect if it's a lot
    if result["title"]:
        result["is_lot"] = is_lot(result["title"])

    # Mark as successful if we got at least price and title
    if result["price"] is not None and result["title"]:
        result["success"] = True

    return result


if __name__ == "__main__":
    # Test with sample eBay sold listing HTML
    sample_html = """
    <html>
    <head>
        <title>A Game of Thrones Hardcover 1st Edition | eBay</title>
        <meta property="og:title" content="A Game of Thrones Hardcover 1st Edition">
    </head>
    <body>
        <h1 class="product-title">A Game of Thrones Hardcover 1st Edition</h1>
        <div class="price-section">
            <span class="price notranslate">Sold for $24.99</span>
        </div>
        <div class="item-condition">
            <span>Condition: Very Good</span>
        </div>
        <div class="sold-info">
            Sold on Jan 15, 2025
        </div>
    </body>
    </html>
    """

    test_url = "https://www.ebay.com/itm/123456789012"

    print("Testing eBay Sold Listing Parser")
    print("=" * 80)
    print()

    result = parse_ebay_sold_listing(test_url, sample_html)

    print(f"Parsing result:")
    print(f"  Success: {result['success']}")
    print(f"  Listing ID: {result['listing_id']}")
    print(f"  Title: {result['title']}")
    print(f"  Price: ${result['price']:.2f}" if result['price'] else "  Price: None")
    print(f"  Condition: {result['condition']}")
    print(f"  Sold Date: {result['sold_date']}")
    print(f"  Is Lot: {result['is_lot']}")
    print()
