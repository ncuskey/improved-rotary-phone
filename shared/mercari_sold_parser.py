"""
Mercari sold listing parser for individual sold item pages.

Parses Mercari sold listing HTML to extract price, condition, sold date.
Works with URLs from Mercari's sold items search.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from shared.lot_detector import is_lot


def _extract_price(html: str) -> Optional[float]:
    """
    Extract sold price from Mercari listing HTML.

    Args:
        html: Raw HTML from Mercari sold listing

    Returns:
        Float price or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Look for price in meta tags (most reliable)
    meta_price = soup.find('meta', property='product:price:amount')
    if meta_price and meta_price.get('content'):
        try:
            return float(meta_price['content'])
        except ValueError:
            pass

    # Strategy 2: Look for price display element
    price_elem = soup.find('span', class_=re.compile(r'price', re.IGNORECASE))
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                pass

    # Strategy 3: Search for "$X.XX" pattern in text
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
    Extract condition from Mercari listing.

    Mercari uses: New, Like New, Good, Fair, Poor

    Args:
        html: Raw HTML from Mercari listing

    Returns:
        Standardized condition string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    condition_map = {
        "new": "New",
        "like new": "Like New",
        "good": "Good",
        "fair": "Fair",
        "poor": "Poor",
    }

    # Look for condition in item details
    condition_elem = soup.find(string=re.compile(r'[Cc]ondition\s*:', re.IGNORECASE))
    if condition_elem:
        parent = condition_elem.find_parent()
        if parent:
            text = parent.get_text(strip=True).lower()
            for keyword, standard in condition_map.items():
                if keyword in text:
                    return standard

    # Look in meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        text = meta_desc['content'].lower()
        for keyword, standard in condition_map.items():
            if keyword in text:
                return standard

    return None


def _extract_sold_date(html: str) -> Optional[str]:
    """
    Extract sold date from Mercari listing.

    Args:
        html: Raw HTML from Mercari listing

    Returns:
        Date string in ISO format (YYYY-MM-DD) or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Look for "Sold on" or similar text
    sold_text = soup.find(string=re.compile(r'[Ss]old\s+(?:on\s+)?[A-Za-z]{3}\s+\d{1,2},?\s+\d{4}', re.IGNORECASE))
    if sold_text:
        match = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', sold_text, re.IGNORECASE)
        if match:
            month_str, day_str, year_str = match.groups()
            try:
                date_obj = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Look for relative time
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
    Extract Mercari item ID from URL.

    Mercari URLs: https://www.mercari.com/us/item/m12345678901/

    Args:
        url: Mercari listing URL

    Returns:
        Item ID or None
    """
    match = re.search(r'/item/(m\d+)', url)
    if match:
        return match.group(1)

    return None


def _extract_title(html: str) -> Optional[str]:
    """
    Extract listing title from Mercari HTML.

    Args:
        html: Raw HTML from Mercari listing

    Returns:
        Title string or None
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: Look for h1 title
    title_elem = soup.find('h1')
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
        # Remove "| Mercari" suffix
        title_text = re.sub(r'\s*\|\s*Mercari\s*$', '', title_text, flags=re.IGNORECASE)
        return title_text

    return None


def parse_mercari_sold_listing(url: str, html: str, snippet: str = "") -> Dict[str, Any]:
    """
    Parse a Mercari sold listing page.

    Args:
        url: Mercari listing URL
        html: Raw HTML from Mercari sold listing page
        snippet: Optional search result snippet

    Returns:
        Dict with structure:
        {
            "platform": "mercari",
            "url": str,
            "listing_id": str,
            "title": str,
            "price": float,
            "condition": str,
            "sold_date": str (ISO format),
            "is_lot": bool,
            "success": bool,
            "snippet": str
        }
    """
    result = {
        "platform": "mercari",
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
    # Test with sample Mercari sold listing HTML
    sample_html = """
    <html>
    <head>
        <title>A Game of Thrones Paperback Book | Mercari</title>
        <meta property="og:title" content="A Game of Thrones Paperback Book">
        <meta property="product:price:amount" content="12.99">
    </head>
    <body>
        <h1>A Game of Thrones Paperback Book</h1>
        <span class="price">$12.99</span>
        <div>Condition: Good</div>
        <div>Sold 3 days ago</div>
    </body>
    </html>
    """

    test_url = "https://www.mercari.com/us/item/m12345678901/"

    print("Testing Mercari Sold Listing Parser")
    print("=" * 80)
    print()

    result = parse_mercari_sold_listing(test_url, sample_html)

    print(f"Parsing result:")
    print(f"  Success: {result['success']}")
    print(f"  Listing ID: {result['listing_id']}")
    print(f"  Title: {result['title']}")
    print(f"  Price: ${result['price']:.2f}" if result['price'] else "  Price: None")
    print(f"  Condition: {result['condition']}")
    print(f"  Sold Date: {result['sold_date']}")
    print(f"  Is Lot: {result['is_lot']}")
    print()
